"""
Этап 3, модификация 1: Momentum Continuation + фильтр тренда H1.

Из всех протестированных идей momentum_continuation показал лучший сырой edge
на сделку ($0.235, покрывает ~37% costов - остальные меньше 16%), но всё ещё
убыточен после спреда. Пробуем усилить его тем же фильтром тренда, что
проверяли на ORB: подтверждённый моментум (3 бара подряд) принимаем только по
направлению тренда H1 (EMA{H1_TREND_EMA_SPAN}, см. strategies.py).

Не требует MT5 - работает с data/{SYMBOL}_M15.parquet и data/{SYMBOL}_H1.parquet
(Этап 1). Честно печатает результат, включая отрицательный.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from backtest.engine import run_backtest
from backtest import strategies
from backtest.report import print_report, save_outputs


def load_parquet(timeframe: str) -> pd.DataFrame:
    path = Path(config.DATA_DIR) / f"{config.SYMBOL}_{timeframe}.parquet"
    if not path.exists():
        print(f"Не найден файл {path}.")
        print("Сначала запустите bot/fetch_history.py (Этап 1), чтобы скачать историю.")
        sys.exit(1)
    return pd.read_parquet(path)


def main():
    m15_df = load_parquet("M15")
    h1_df = load_parquet("H1")

    trend_by_date = strategies.build_trend_lookup(m15_df, h1_df)

    def signal_fn(day_bars, date):
        return strategies.trend_filtered_momentum(day_bars, trend_by_date.get(date))

    trades, equity_df = run_backtest(m15_df, config.STARTING_BALANCE_USD, signal_fn)

    title = (
        f"Результаты бэктеста Momentum Continuation + фильтр тренда H1, {config.SYMBOL}, "
        f"окно {config.TRADING_WINDOW_START}-{config.TRADING_WINDOW_END}, "
        f"{strategies.MOMENTUM_CONSECUTIVE_BARS} бара подряд, TP = {strategies.MOMENTUM_RR}R"
    )
    print_report(trades, equity_df, config.STARTING_BALANCE_USD, title)

    out_dir = Path(__file__).resolve().parent
    save_outputs(trades, equity_df, out_dir, title, file_prefix="momentum_trend")


if __name__ == "__main__":
    main()
