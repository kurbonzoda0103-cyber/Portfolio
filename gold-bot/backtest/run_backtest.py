"""
Этап 3: бэктест EMA trend-following на BTCUSDT (Bybit), минимум 6 месяцев истории.

Не требует API-ключей и подключения к Bybit - работает с
data/{SYMBOL}_M{INTERVAL}.parquet, скачанной заранее через
bot/fetch_history_bybit.py (публичные данные, ключи не нужны).

Честно печатает результат, включая отрицательный - подгонять параметры под
красивую кривую доходности не будем (см. правила проекта: это оверфиттинг,
отрицательный результат - тоже результат).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
import risk_gate
from backtest.engine import run_backtest
from backtest import strategies
from backtest.report import print_report, save_outputs


def load_data() -> pd.DataFrame:
    tf_name = f"M{config.INTERVAL}" if config.INTERVAL.isdigit() else config.INTERVAL
    path = Path(config.DATA_DIR) / f"{config.SYMBOL}_{tf_name}.parquet"
    if not path.exists():
        print(f"Не найден файл {path}.")
        print("Сначала запустите bot/fetch_history_bybit.py (Этап 1), чтобы скачать историю:")
        print(f"  python bot\\fetch_history_bybit.py {config.SYMBOL} {config.INTERVAL}")
        sys.exit(1)
    return pd.read_parquet(path)


def main():
    df = load_data()

    history_days = (df["time_utc"].max() - df["time_utc"].min()).days
    print(f"Загружено {len(df)} свечей, история: {history_days} дней (~{history_days / 30:.1f} мес.)")
    if history_days < 180:
        print("ВНИМАНИЕ: истории меньше 6 месяцев - для честной проверки стратегии")
        print("рекомендуется минимум 180 дней. Продолжаю с тем, что есть.")
    print()

    df = strategies.add_ema_signals(df)

    trades, equity_df = run_backtest(df, risk_gate.STARTING_BALANCE_USDT)

    title = (
        f"Результаты бэктеста EMA trend-following, {config.SYMBOL} "
        f"({strategies.EMA_FAST}/{strategies.EMA_SLOW}, стоп {strategies.ATR_STOP_MULT}xATR{strategies.ATR_PERIOD})"
    )
    print_report(trades, equity_df, risk_gate.STARTING_BALANCE_USDT, title)

    out_dir = Path(__file__).resolve().parent
    save_outputs(trades, equity_df, out_dir, title, file_prefix="ema_trend")


if __name__ == "__main__":
    main()
