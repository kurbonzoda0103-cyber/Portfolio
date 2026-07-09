"""
Этап 3, вариант 5: Momentum Breakout + фильтр объёма.

Тот же вход, что в ORB (пробой первых 30 минут окна), но принимается только
если пробойный бар показал всплеск tick_volume относительно объёма во время
формирования диапазона - отсекаем "тихие" ложные пробои (см.
strategies.volume_confirmed_breakout).

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
        return strategies.volume_confirmed_breakout(day_bars)

    trades, equity_df = run_backtest(df, config.STARTING_BALANCE_USD, signal_fn)

    title = (
        f"Результаты бэктеста Momentum Breakout + объём, {config.SYMBOL}, "
        f"окно {config.TRADING_WINDOW_START}-{config.TRADING_WINDOW_END}, "
        f"диапазон {strategies.VOLUME_ORB_MINUTES} мин, "
        f"объём >= {strategies.VOLUME_MULTIPLIER}x среднего, TP = {strategies.VOLUME_ORB_RR}R"
    )
    print_report(trades, equity_df, config.STARTING_BALANCE_USD, title)

    out_dir = Path(__file__).resolve().parent
    save_outputs(trades, equity_df, out_dir, title, file_prefix="volume_orb")


if __name__ == "__main__":
    main()
