"""
Этап 3, вариант 3: Range Fade (mean-reversion от ложного пробоя диапазона).

Идея: первый импульс в начале окна часто оказывается ложным выносом (сессии
Лондон+Нью-Йорк ещё не набрали объём). Ждём пробоя диапазона первых 30 минут
окна, и если цена возвращается обратно внутрь - входим ПРОТИВ пробоя, на
возврат к противоположной границе диапазона (см. strategies.range_fade).

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
        return strategies.range_fade(day_bars)

    trades, equity_df = run_backtest(df, config.STARTING_BALANCE_USD, signal_fn)

    title = (
        f"Результаты бэктеста Range Fade, {config.SYMBOL}, "
        f"окно {config.TRADING_WINDOW_START}-{config.TRADING_WINDOW_END}, "
        f"диапазон {strategies.RANGE_FADE_MINUTES} мин, цель = противоположная граница"
    )
    print_report(trades, equity_df, config.STARTING_BALANCE_USD, title)

    out_dir = Path(__file__).resolve().parent
    save_outputs(trades, equity_df, out_dir, title, file_prefix="range_fade")


if __name__ == "__main__":
    main()
