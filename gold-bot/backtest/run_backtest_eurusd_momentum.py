"""
Проверка той же лучшей стратегии (Momentum Continuation, 3 бара, TP=1.5R) на
EURUSD вместо золота - гипотеза: у форекс-мажоров спред намного уже
относительно движения цены, тот же сырой edge может реально перекрыть costы.

ВАЖНО про EURUSD_SPREAD_POINTS ниже: это ПРИБЛИЖЕНИЕ (типичный спред у
форекс-брокеров на стандартных счетах), а НЕ измеренный факт для этого XM-счёта.
Перед тем как доверять результату, замерьте реальный спред:
    python bot\\check_connection.py EURUSD
и поправьте константу ниже.

Перед запуском нужно скачать историю EURUSD (отдельно от золота):
    python bot\\fetch_history.py EURUSD

Также используем то же торговое окно 17:00-21:00 (config.py), что и для
золота - оно подобрано по волатильности ЗОЛОТА (этап 2), для EURUSD отдельно
не проверялось. Лондон+Нью-Йорк пересекаются в это же время и для форекс-
мажоров это тоже обычно активное окно, но это допущение, а не факт.

Не требует MT5 для самого бэктеста - работает с data/EURUSD_M15.parquet.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from backtest.engine import run_backtest, Instrument
from backtest import strategies
from backtest.report import print_report, save_outputs

SYMBOL = "EURUSD"

# Приближение, НЕ измеренный факт - см. предупреждение в шапке файла.
EURUSD_POINT = 0.00001        # 5-значная котировка (1 пипс = 10 points) - большинство брокеров, включая XM
EURUSD_CONTRACT_SIZE = 100_000  # единиц EUR на 1 стандартный лот
EURUSD_SPREAD_POINTS = 15     # ПРИБЛИЖЕНИЕ: типичный спред форекс-мажора на стандартном счёте (~1.5 пипса)

# Евро как валюта появился только 01.01.1999 - всё, что раньше в истории брокера,
# синтетика/реконструкция для графиков, а не реальные торги. Отрезаем эти годы,
# иначе бэктест частично проверяется на не-настоящих данных.
MIN_DATE = "1999-01-01"


def load_data() -> pd.DataFrame:
    path = Path(config.DATA_DIR) / f"{SYMBOL}_M15.parquet"
    if not path.exists():
        print(f"Не найден файл {path}.")
        print(f"Сначала запустите: python bot\\fetch_history.py {SYMBOL}")
        sys.exit(1)

    df = pd.read_parquet(path)
    before = len(df)
    df = df[df["time_local"] >= MIN_DATE].reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        print(f"Отброшено {dropped} свечей до {MIN_DATE} (синтетическая до-euro история брокера).")
    return df


def main():
    df = load_data()

    eurusd = Instrument(
        point=EURUSD_POINT,
        contract_size=EURUSD_CONTRACT_SIZE,
        spread_points=EURUSD_SPREAD_POINTS,
        commission_per_lot_usd=0.0,
    )

    def signal_fn(day_bars, date):
        return strategies.momentum_continuation(day_bars)

    trades, equity_df = run_backtest(df, config.STARTING_BALANCE_USD, signal_fn, instrument=eurusd)

    title = (
        f"Результаты бэктеста Momentum Continuation, {SYMBOL} (спред - ПРИБЛИЖЕНИЕ, не измерено), "
        f"окно {config.TRADING_WINDOW_START}-{config.TRADING_WINDOW_END}, "
        f"{strategies.MOMENTUM_CONSECUTIVE_BARS} бара подряд, TP = {strategies.MOMENTUM_RR}R"
    )
    spread_note = (
        f"ВАЖНО: спред EURUSD ({EURUSD_SPREAD_POINTS} пунктов) - ПРИБЛИЖЕНИЕ, НЕ измерено\n"
        f"на этом счёте. Замерьте реальный: python bot\\check_connection.py EURUSD"
    )
    print_report(trades, equity_df, config.STARTING_BALANCE_USD, title, spread_note=spread_note)

    out_dir = Path(__file__).resolve().parent
    save_outputs(trades, equity_df, out_dir, title, file_prefix="eurusd_momentum")


if __name__ == "__main__":
    main()
