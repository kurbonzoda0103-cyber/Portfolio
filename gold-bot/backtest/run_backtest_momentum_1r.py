"""
Этап 3, модификация 2: Momentum Continuation с TP = 1R (вместо 1.5R).

В чистом Momentum Continuation (1.5R) только 116-148 из ~1200-700 сделок
доходили до цели, а 40-50% упирались в край окна, не успев дойти ни до стопа,
ни до тейка - похоже, 1.5R просто нереалистичен для оставшегося в окне времени.
Проверяем гипотезу: цель поближе (1R) должна закрываться чаще, пока движение
ещё живо, за счёт чего сырой edge на сделку может вырасти (или не вырасти -
честно проверяем, не подгоняя).

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

TP_RR = 1.0


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
        return strategies.momentum_continuation(day_bars, rr=TP_RR)

    trades, equity_df = run_backtest(df, config.STARTING_BALANCE_USD, signal_fn)

    title = (
        f"Результаты бэктеста Momentum Continuation, {config.SYMBOL}, "
        f"окно {config.TRADING_WINDOW_START}-{config.TRADING_WINDOW_END}, "
        f"{strategies.MOMENTUM_CONSECUTIVE_BARS} бара подряд, TP = {TP_RR}R"
    )
    print_report(trades, equity_df, config.STARTING_BALANCE_USD, title)

    out_dir = Path(__file__).resolve().parent
    save_outputs(trades, equity_df, out_dir, title, file_prefix="momentum_1r")


if __name__ == "__main__":
    main()
