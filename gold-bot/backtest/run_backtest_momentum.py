"""
Этап 3, вариант 6: Momentum Continuation - вход после N баров подряд в одну сторону.

Идея: не входить на первом же импульсе (как ORB), а дождаться подтверждения -
несколько M15-баров подряд закрылись в одну сторону, и только потом входить по
направлению (см. strategies.momentum_continuation).

Не требует MT5 - работает с data/{SYMBOL}_M15.parquet (Этап 1). Честно печатает
результат, включая отрицательный - подгонять параметры под красивую кривую
доходности не будем.
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
        return strategies.momentum_continuation(day_bars)

    trades, equity_df = run_backtest(df, config.STARTING_BALANCE_USD, signal_fn)

    title = (
        f"Результаты бэктеста Momentum Continuation, {config.SYMBOL}, "
        f"окно {config.TRADING_WINDOW_START}-{config.TRADING_WINDOW_END}, "
        f"{strategies.MOMENTUM_CONSECUTIVE_BARS} бара подряд, TP = {strategies.MOMENTUM_RR}R"
    )
    print_report(trades, equity_df, config.STARTING_BALANCE_USD, title)

    out_dir = Path(__file__).resolve().parent
    save_outputs(trades, equity_df, out_dir, title, file_prefix="momentum")


if __name__ == "__main__":
    main()
