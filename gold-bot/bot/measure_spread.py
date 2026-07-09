"""
Замер РЕАЛЬНОГО спреда GOLD в течение торгового окна (config.TRADING_WINDOW_START-
TRADING_WINDOW_END). Один замер вечером (Этап 0) - не факт, а случайная точка;
Momentum Continuation (лучшая стратегия из Этапа 3) держится на честном спреде -
если он окажется у'же в начале окна (17:00-18:00, где моментум сильнее всего),
это может изменить итоговый результат.

Что делает скрипт:
1. Подключается к уже запущенному терминалу MT5.
2. Каждые SAMPLE_INTERVAL_MINUTES минут, пока не закончится сегодняшнее
   торговое окно, снимает bid/ask и считает спред (в пунктах и в $ на лот 0.01).
3. Дописывает каждый замер в data/spread_log.csv (не перезаписывает - копится
   история за много дней и разных запусков).
4. В конце печатает сводку за сегодня: мин/сред/макс спред.

Запускать один раз В НАЧАЛЕ или ДО начала окна - скрипт сам подождёт нужное
время и будет сэмплировать до конца окна, окно PowerShell можно свернуть.
Ctrl+C - остановить досрочно (то, что уже собрано, останется в логе).

Чем за больше дней накопится данных, тем честнее будет итоговая оценка спреда
для config.py -> ASSUMED_SPREAD_POINTS.
"""

import csv
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import MetaTrader5 as mt5
except ImportError:
    print("Библиотека MetaTrader5 не установлена.")
    print("Установите её командой:  pip install MetaTrader5")
    sys.exit(1)

import config

SAMPLE_INTERVAL_MINUTES = 5
LOG_PATH = Path(config.DATA_DIR) / "spread_log.csv"


def get_spread_sample():
    """Возвращает dict с текущей котировкой и спредом, либо None, если котировки нет."""
    tick = mt5.symbol_info_tick(config.SYMBOL)
    symbol_info = mt5.symbol_info(config.SYMBOL)
    if tick is None or symbol_info is None or tick.time == 0:
        return None

    point = symbol_info.point
    contract_size = symbol_info.trade_contract_size
    spread_points = (tick.ask - tick.bid) / point
    spread_usd_001_lot = (tick.ask - tick.bid) * contract_size * 0.01

    return {
        "bid": tick.bid,
        "ask": tick.ask,
        "spread_points": round(spread_points, 2),
        "spread_usd_001_lot": round(spread_usd_001_lot, 4),
    }


def append_log(row: dict):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = not LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def main():
    if not mt5.initialize():
        print("Не удалось подключиться к терминалу MT5.")
        print("Код ошибки:", mt5.last_error())
        print("Терминал должен быть запущен и залогинен в демо-счёт XM.")
        sys.exit(1)

    symbol_info = mt5.symbol_info(config.SYMBOL)
    if symbol_info is None:
        print(f"Символ {config.SYMBOL} не найден у брокера. Проверьте config.py -> SYMBOL.")
        mt5.shutdown()
        sys.exit(1)
    if not symbol_info.visible:
        mt5.symbol_select(config.SYMBOL, True)

    today = datetime.now().date()
    window_start = datetime.combine(today, datetime.strptime(config.TRADING_WINDOW_START, "%H:%M").time())
    window_end = datetime.combine(today, datetime.strptime(config.TRADING_WINDOW_END, "%H:%M").time())

    print("=" * 60)
    print(f"Замер спреда {config.SYMBOL}, окно {config.TRADING_WINDOW_START}-{config.TRADING_WINDOW_END} "
          f"(UTC+{config.MY_TIMEZONE_OFFSET_HOURS})")
    print(f"Интервал: каждые {SAMPLE_INTERVAL_MINUTES} мин. Лог: {LOG_PATH}")
    print("Окно PowerShell можно свернуть. Ctrl+C - остановить досрочно.")
    print("=" * 60)

    if datetime.now() > window_end:
        print("Торговое окно на сегодня уже закончилось.")
        print("Запустите скрипт завтра в течение 17:00-21:00 (или раньше - он сам подождёт начала).")
        mt5.shutdown()
        sys.exit(0)

    if datetime.now() < window_start:
        wait_seconds = (window_start - datetime.now()).total_seconds()
        print(f"До начала окна ещё {wait_seconds / 60:.0f} мин - жду...")
        time.sleep(wait_seconds)

    session_samples = []

    try:
        while datetime.now() < window_end:
            sample = get_spread_sample()
            now = datetime.now()
            if sample is not None:
                row = {"timestamp_local": now.strftime("%Y-%m-%d %H:%M:%S"), **sample}
                append_log(row)
                session_samples.append(sample["spread_usd_001_lot"])
                print(
                    f"{now.strftime('%H:%M:%S')}  bid={sample['bid']}  ask={sample['ask']}  "
                    f"спред={sample['spread_points']:.1f} пунктов "
                    f"(${sample['spread_usd_001_lot']:.2f} на лот 0.01)"
                )
            else:
                print(f"{now.strftime('%H:%M:%S')}  нет живой котировки, пропуск")

            time.sleep(SAMPLE_INTERVAL_MINUTES * 60)
    except KeyboardInterrupt:
        print("\nОстановлено вручную (Ctrl+C).")

    mt5.shutdown()

    if session_samples:
        print()
        print("=" * 60)
        print(f"Сводка за сегодня: {len(session_samples)} замеров")
        print(
            f"  мин: ${min(session_samples):.2f}   "
            f"среднее: ${sum(session_samples) / len(session_samples):.2f}   "
            f"макс: ${max(session_samples):.2f}"
        )
        print(f"Данные копятся в {LOG_PATH} - запускайте скрипт несколько дней подряд,")
        print("потом посчитаем честное среднее и обновим config.py -> ASSUMED_SPREAD_POINTS.")
        print("=" * 60)
    else:
        print("Замеров за сегодня не собрано.")


if __name__ == "__main__":
    main()
