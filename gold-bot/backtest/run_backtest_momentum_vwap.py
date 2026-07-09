"""
Этап 3, модификация 4: Momentum Continuation + confluence с VWAP.

И momentum_continuation ($0.235/сделку), и vwap_cross ($0.09/сделку) по
отдельности показали положительный сырой сигнал - единственные два из всех
протестированных. Фильтр тренда H1 испортил моментум (см.
run_backtest_momentum_trend.py). Пробуем комбинацию из двух сигналов с уже
доказанным edge: сигнал momentum_continuation принимаем только если цена в
момент входа на той же стороне VWAP, что и направление сигнала (см.
strategies.momentum_vwap_confluence).

Не требует MT5 - работает с data/{SYMBOL}_M15.parquet (Этап 1). Честно печатает
результат, включая отрицательный.
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
        return strategies.momentum_vwap_confluence(day_bars)

    trades, equity_df = run_backtest(df, config.STARTING_BALANCE_USD, signal_fn)

    title = (
        f"Результаты бэктеста Momentum Continuation + confluence VWAP, {config.SYMBOL}, "
        f"окно {config.TRADING_WINDOW_START}-{config.TRADING_WINDOW_END}, "
        f"{strategies.MOMENTUM_CONSECUTIVE_BARS} бара подряд, TP = {strategies.MOMENTUM_RR}R"
    )
    print_report(trades, equity_df, config.STARTING_BALANCE_USD, title)

    out_dir = Path(__file__).resolve().parent
    save_outputs(trades, equity_df, out_dir, title, file_prefix="momentum_vwap")


if __name__ == "__main__":
    main()
