"""
Этап 1: выгрузка исторических данных по золоту из MT5 и сохранение в parquet.

Что делает скрипт:
1. Подключается к уже запущенному терминалу MT5 (как check_connection.py).
2. Для таймфреймов M5, M15, H1 запрашивает у брокера ВСЮ доступную историю по
   символу из config.SYMBOL (сколько бы лет брокер ни хранил).
3. Добавляет к каждой свече три варианта времени:
     time_server - как прислал брокер (числа "по часам сервера", это НЕ настоящий UTC)
     time_utc    - настоящее UTC (server - SERVER_UTC_OFFSET_HOURS)
     time_local  - твоё время, UTC+5 (time_utc + MY_TIMEZONE_OFFSET_HOURS)
4. Сохраняет каждый таймфрейм в отдельный parquet-файл в data/.

Запускать на Windows с открытым и залогиненным терминалом MT5.
Перед запуском: bot/check_connection.py уже должен был отработать и подтвердить
SYMBOL и SERVER_UTC_OFFSET_HOURS в config.py - без них время будет посчитано неверно.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import MetaTrader5 as mt5
except ImportError:
    print("Библиотека MetaTrader5 не установлена.")
    print("Установите её командой:  pip install MetaTrader5")
    sys.exit(1)

import pandas as pd
import config

# Таймфреймы, которые выгружаем. Названия слева пойдут в имена файлов.
TIMEFRAMES = {
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
}


def fetch_one_timeframe(symbol: str, tf_name: str, tf_value: int) -> pd.DataFrame | None:
    """Тянет всю доступную историю по одному таймфрейму и возвращает DataFrame с временем в 3 видах."""

    # date_from нарочно очень ранняя - MT5 сам обрежет по реально доступной истории у брокера.
    date_from = datetime(2000, 1, 1, tzinfo=timezone.utc)
    date_to = datetime.now(timezone.utc)

    rates = mt5.copy_rates_range(symbol, tf_value, date_from, date_to)
    if rates is None or len(rates) == 0:
        print(f"  {tf_name}: данных нет ({mt5.last_error()})")
        return None

    df = pd.DataFrame(rates)

    # "time" от MT5 - unix-время, но с цифрами часов сервера брокера (не настоящий UTC!).
    # Тот же нюанс мы уже видели в check_connection.py при сравнении тика с реальным UTC.
    df["time_server"] = pd.to_datetime(df["time"], unit="s")
    df["time_utc"] = df["time_server"] - pd.Timedelta(hours=config.SERVER_UTC_OFFSET_HOURS)
    df["time_local"] = df["time_utc"] + pd.Timedelta(hours=config.MY_TIMEZONE_OFFSET_HOURS)
    df = df.drop(columns=["time"])

    return df


def main():
    if config.SERVER_UTC_OFFSET_HOURS is None:
        print("В config.py не заполнено SERVER_UTC_OFFSET_HOURS.")
        print("Сначала запустите bot/check_connection.py и впишите смещение сервера от UTC.")
        sys.exit(1)

    if not mt5.initialize():
        print("Не удалось подключиться к терминалу MT5.")
        print("Код ошибки:", mt5.last_error())
        print("Терминал должен быть запущен и залогинен в демо-счёт XM.")
        sys.exit(1)

    symbol_info = mt5.symbol_info(config.SYMBOL)
    if symbol_info is None:
        print(f"Символ {config.SYMBOL} не найден у брокера. Проверьте config.py -> SYMBOL")
        print("(запустите bot/check_connection.py - он подскажет правильное имя).")
        mt5.shutdown()
        sys.exit(1)

    if not symbol_info.visible:
        mt5.symbol_select(config.SYMBOL, True)

    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"Выгрузка истории {config.SYMBOL} с сервера {mt5.account_info().server}")
    print("=" * 60)

    for tf_name, tf_value in TIMEFRAMES.items():
        print(f"\n{tf_name}: запрашиваю у брокера...")
        df = fetch_one_timeframe(config.SYMBOL, tf_name, tf_value)
        if df is None:
            continue

        out_path = data_dir / f"{config.SYMBOL}_{tf_name}.parquet"
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
