"""
Этап 3, вариант 1 (ORB без фильтра): бэктест пробоя диапазона на исторических
M15-данных золота. РЕЗУЛЬТАТ УЖЕ ПОЛУЧЕН И ОТРИЦАТЕЛЬНЫЙ (-54.7%, сырой сигнал
в минусе ещё до спреда) - см. README. Скрипт оставлен как зафиксированный
базовый прогон для сравнения с другими стратегиями, а не для дальнейшей
подгонки параметров.

Не требует MT5 - работает с data/{SYMBOL}_M15.parquet (Этап 1).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from backtest.engine import run_backtest
from backtest import strategies
from backtest.report import print_report, save_outputs


def load_data() -> pd.DataFrame:
    path = Path(config.DATA_DIR) / f"{config.SYMBOL}_M15.parquet"
    if not path.exists():
        print(f"Не найден файл {path}.")
        print("Сначала запустите bot/fetch_history.py (Этап 1), чтобы скачать историю.")
        sys.exit(1)
    return pd.read_parquet(path)


def main():
    df = load_data()

    def signal_fn(day_bars, date):
        return strategies.opening_range_breakout(day_bars)

    trades, equity_df = run_backtest(df, config.STARTING_BALANCE_USD, signal_fn)

    title = (
        f"Результаты бэктеста ORB (без фильтра), {config.SYMBOL}, "
        f"окно {config.TRADING_WINDOW_START}-{config.TRADING_WINDOW_END}, "
        f"диапазон {strategies.ORB_MINUTES} мин, TP = {strategies.ORB_RR}R"
    )
    print_report(trades, equity_df, config.STARTING_BALANCE_USD, title)

    out_dir = Path(__file__).resolve().parent
    save_outputs(trades, equity_df, out_dir, title, file_prefix="orb")


if __name__ == "__main__":
    main()
