"""
Этап 1: выгрузка исторических данных по золоту из MT5 и сохранение в parquet.

Что делает скрипт:
1. Подключается к уже запущенному терминалу MT5 (как check_connection.py).
2. Для таймфреймов M5, M15, H1 (или только части из них, см. ниже) запрашивает
   у брокера ВСЮ доступную историю по символу (по умолчанию - config.SYMBOL, но
   можно передать другой символ первым аргументом: `python bot\\fetch_history.py
   EURUSD`, например, чтобы проверить ту же стратегию на другом инструменте, не
   трогая настройки золота в config.py). Вторым аргументом можно ограничить
   таймфреймы через запятую без пробелов: `python bot\\fetch_history.py EURUSD M15`
   - полезно, если нужен только один таймфрейм и не хочется ждать M5 (самый
   "тяжёлый" по числу свечей, особенно если у терминала ещё не докачана глубокая
   история этого символа - см. предупреждение про 'Max bars in history' в конце).
   MT5 отдаёт максимум около 100 000 свечей за один запрос и молча обрезает
   остальное - поэтому тянем историю порциями (пагинацией) через
   copy_rates_from_pos, пока брокер не перестанет отдавать новые данные.
   Каждая порция печатается в консоль - если скрипт "молчит" дольше минуты,
   значит терминал ещё докачивает историю с сервера, это не зависание.
3. Добавляет к каждой свече три варианта времени:
     time_server - как прислал брокер (числа "по часам сервера", это НЕ настоящий UTC)
     time_utc    - настоящее UTC (server - SERVER_UTC_OFFSET_HOURS)
     time_local  - твоё время, UTC+5 (time_utc + MY_TIMEZONE_OFFSET_HOURS)
4. Сохраняет каждый таймфрейм в отдельный parquet-файл в data/.

Запускать на Windows с открытым и залогиненным терминалом MT5.
Перед запуском: bot/check_connection.py уже должен был отработать и подтвердить
SERVER_UTC_OFFSET_HOURS в config.py - без него время будет посчитано неверно.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import MetaTrader5 as mt5
except ImportError:
    print("Библиотека MetaTrader5 не установлена.")
    print("Установите её командой:  pip install MetaTrader5")
    sys.exit(1)

import numpy as np
import pandas as pd
import config

# Таймфреймы, которые выгружаем. Названия слева пойдут в имена файлов.
TIMEFRAMES = {
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
}

# Сколько свечей просить за один запрос. Держим с запасом ниже наблюдаемого
# потолка API (~100 000), чтобы точно не попасть в скрытую обрезку.
CHUNK_SIZE = 90_000
# Защита от бесконечного цикла, если API вдруг начнёт бесконечно отдавать данные.
MAX_CHUNKS = 200


def fetch_one_timeframe(symbol: str, tf_name: str, tf_value: int) -> pd.DataFrame | None:
    """Тянет всю доступную историю по одному таймфрейму порциями и возвращает DataFrame с временем в 3 видах."""

    # copy_rates_from_pos(symbol, tf, start_pos, count): start_pos=0 - самая свежая свеча,
    # чем больше start_pos, тем дальше в прошлое. Каждый чанк возвращается в хронологическом
    # порядке (старые -> новые), поэтому чанки нужно собрать в обратном порядке, чтобы
    # получить единую хронологию от самой старой свечи к самой новой.
    chunks = []
    start_pos = 0
    for chunk_num in range(1, MAX_CHUNKS + 1):
        batch = mt5.copy_rates_from_pos(symbol, tf_value, start_pos, CHUNK_SIZE)
        if batch is None or len(batch) == 0:
            break
        chunks.append(batch)
        print(f"    ...порция {chunk_num}: получено {len(batch)} свечей (всего пока {start_pos + len(batch)})")
        if len(batch) < CHUNK_SIZE:
            break  # брокер отдал меньше, чем просили - значит история закончилась
        start_pos += len(batch)

    if not chunks:
        print(f"  {tf_name}: данных нет ({mt5.last_error()})")
        return None

    rates = np.concatenate(chunks[::-1])
    df = pd.DataFrame(rates).drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)

    # "time" от MT5 - unix-время, но с цифрами часов сервера брокера (не настоящий UTC!).
    # Тот же нюанс мы уже видели в check_connection.py при сравнении тика с реальным UTC.
    df["time_server"] = pd.to_datetime(df["time"], unit="s")
    df["time_utc"] = df["time_server"] - pd.Timedelta(hours=config.SERVER_UTC_OFFSET_HOURS)
    df["time_local"] = df["time_utc"] + pd.Timedelta(hours=config.MY_TIMEZONE_OFFSET_HOURS)
    df = df.drop(columns=["time"])

    return df


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else config.SYMBOL

    if len(sys.argv) > 2:
        requested = sys.argv[2].split(",")
        unknown = [tf for tf in requested if tf not in TIMEFRAMES]
        if unknown:
            print(f"Неизвестные таймфреймы: {unknown}. Доступны: {list(TIMEFRAMES)}")
            sys.exit(1)
        timeframes = {tf: TIMEFRAMES[tf] for tf in requested}
    else:
        timeframes = TIMEFRAMES

    if config.SERVER_UTC_OFFSET_HOURS is None:
        print("В config.py не заполнено SERVER_UTC_OFFSET_HOURS.")
        print("Сначала запустите bot/check_connection.py и впишите смещение сервера от UTC.")
        sys.exit(1)

    if not mt5.initialize():
        print("Не удалось подключиться к терминалу MT5.")
        print("Код ошибки:", mt5.last_error())
        print("Терминал должен быть запущен и залогинен в демо-счёт XM.")
        sys.exit(1)

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"Символ {symbol} не найден у брокера.")
        print("Проверьте точное название в Market Watch терминала.")
        mt5.shutdown()
        sys.exit(1)

    if not symbol_info.visible:
        mt5.symbol_select(symbol, True)

    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"Выгрузка истории {symbol} с сервера {mt5.account_info().server}")
    print("=" * 60)

    for tf_name, tf_value in timeframes.items():
        print(f"\n{tf_name}: запрашиваю у брокера...")
        df = fetch_one_timeframe(symbol, tf_name, tf_value)
        if df is None:
            continue

        out_path = data_dir / f"{symbol}_{tf_name}.parquet"
        df.to_parquet(out_path, index=False)

        first_candle = df["time_local"].min()
        last_candle = df["time_local"].max()
        print(f"  Свечей:        {len(df)}")
        print(f"  Период (ваше время UTC+{config.MY_TIMEZONE_OFFSET_HOURS}): {first_candle} -> {last_candle}")
        print(f"  Сохранено в:   {out_path}")

    mt5.shutdown()

    print()
    print("=" * 60)
    print("Готово. Если период по какому-то таймфрейму кажется коротким -")
    print("проверьте в терминале Tools -> Options -> Charts -> 'Max bars in history'")
    print("(должно быть выставлено максимальное значение), и запустите скрипт заново.")
    print("=" * 60)


if __name__ == "__main__":
    main()
