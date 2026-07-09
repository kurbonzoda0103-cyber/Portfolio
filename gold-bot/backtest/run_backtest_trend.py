"""
Этап 3, вариант 2: пробой диапазона (ORB) с фильтром по тренду H1.

ORB без фильтра (run_backtest.py) дал -54.7% - сырой сигнал был в минусе ещё до
спреда, то есть у пробоя нет edge, и часть сделок наверняка открывались против
старшего тренда. Здесь тот же вход (пробой первых 30 минут окна), но сигнал
принимается ТОЛЬКО по направлению тренда H1 (EMA{H1_TREND_EMA_SPAN}, см.
strategies.py) - контр-трендовые пробои просто пропускаем, а не переворачиваем.

Тренд определяется по ПОСЛЕДНЕМУ УЖЕ ЗАКРЫТОМУ H1-бару на момент начала окна -
без заглядывания в будущее (см. compute_h1_trend_series в strategies.py).

Не требует MT5 - работает с data/{SYMBOL}_M15.parquet и data/{SYMBOL}_H1.parquet
(Этап 1). Честно печатает результат, включая отрицательный - если фильтр по
тренду не спасёт сигнал, так и скажем, а не будем подгонять параметры.
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


def build_trend_lookup(m15_df: pd.DataFrame, h1_df: pd.DataFrame) -> dict:
    """Для каждого торгового дня определяет тренд H1 на момент начала окна,
    используя только уже закрытые H1-бары (см. compute_h1_trend_series)."""

    h1_trend = strategies.compute_h1_trend_series(h1_df)

    dates = sorted(m15_df["time_local"].dt.date.unique())
    windows = pd.DataFrame({
        "date": dates,
        "window_start": [pd.Timestamp(f"{d} {config.TRADING_WINDOW_START}") for d in dates],
    }).sort_values("window_start")

    merged = pd.merge_asof(
        windows,
        h1_trend.sort_values("confirmed_time"),
        left_on="window_start",
        right_on="confirmed_time",
        direction="backward",
    )

    trend_by_date = {}
    for _, row in merged.iterrows():
        if pd.isna(row["ema"]) or row["close"] == row["ema"]:
            trend_by_date[row["date"]] = None
        elif row["close"] > row["ema"]:
            trend_by_date[row["date"]] = "long"
        else:
            trend_by_date[row["date"]] = "short"

    return trend_by_date


def main():
    m15_df = load_parquet("M15")
    h1_df = load_parquet("H1")

    trend_by_date = build_trend_lookup(m15_df, h1_df)

    trend_counts = pd.Series(list(trend_by_date.values())).value_counts(dropna=False)
    print(f"Дней с трендом long: {trend_counts.get('long', 0)}, "
          f"short: {trend_counts.get('short', 0)}, "
          f"не определён: {trend_counts.get(None, 0)}\n")

    def signal_fn(day_bars, date):
        return strategies.trend_filtered_orb(day_bars, trend_by_date.get(date))

    trades, equity_df = run_backtest(m15_df, config.STARTING_BALANCE_USD, signal_fn)

    title = (
        f"Результаты бэктеста ORB + фильтр тренда H1 (EMA{strategies.H1_TREND_EMA_SPAN}), "
        f"{config.SYMBOL}, окно {config.TRADING_WINDOW_START}-{config.TRADING_WINDOW_END}"
    )
    print_report(trades, equity_df, config.STARTING_BALANCE_USD, title)

    out_dir = Path(__file__).resolve().parent
    save_outputs(trades, equity_df, out_dir, title, file_prefix="trend_orb")


if __name__ == "__main__":
    main()
