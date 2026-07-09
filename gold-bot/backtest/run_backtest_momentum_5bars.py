"""
Этап 3, модификация 3: Momentum Continuation с подтверждением 5 барами подряд
(вместо 3), TP остаётся 1.5R - тот вариант, что дал лучший edge из всех.

Идея: ужесточить вход - требовать более длинную серию баров в одну сторону
перед входом, чтобы отсечь короткие рывки, которые быстро выдыхаются, и
поймать только по-настоящему устойчивый моментум. Сделок будет меньше -
проверяем, вырастет ли edge на сделку, или качество не компенсирует потерю
количества (честно, без подгонки).

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

CONSECUTIVE_BARS = 5


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
        return strategies.momentum_continuation(day_bars, consecutive_bars=CONSECUTIVE_BARS)

    trades, equity_df = run_backtest(df, config.STARTING_BALANCE_USD, signal_fn)

    title = (
        f"Результаты бэктеста Momentum Continuation, {config.SYMBOL}, "
        f"окно {config.TRADING_WINDOW_START}-{config.TRADING_WINDOW_END}, "
        f"{CONSECUTIVE_BARS} баров подряд, TP = {strategies.MOMENTUM_RR}R"
    )
    print_report(trades, equity_df, config.STARTING_BALANCE_USD, title)

    out_dir = Path(__file__).resolve().parent
    save_outputs(trades, equity_df, out_dir, title, file_prefix="momentum_5bars")


if __name__ == "__main__":
    main()
