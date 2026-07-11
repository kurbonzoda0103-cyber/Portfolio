"""
Train/test валидация: прежде чем сузить портфель до ETH (единственная из
BTC/ETH/SOL, показавшая близкий к нулю результат в общем портфельном тесте),
проверяем честно на РАЗДЕЛЁННЫХ по времени данных - не выбираем монету
постфактум по одному куску истории, который уже видели.

Делим всю доступную историю ETH на train (первые 70% по времени) и test
(последние 30%, НЕ ВИДЕННЫЕ при принятии решения о выборе монеты). Параметры
стратегии (Mean-reversion + ADX ranging, Боллинджер 20/2.0, ADX<20) уже
зафиксированы по прошлым тестам на портфеле из 8 монет - здесь их НЕ
подгоняем, просто проверяем, держится ли edge по ETH в обеих половинах
времени, а не только в одной удачной.

Индикаторы (Боллинджер/ATR/ADX) считаются на ПОЛНОЙ истории ДО разбиения на
train/test, чтобы в начале test-периода они были уже "разогреты", а не
стартовали заново с NaN.

Не требует API-ключей - работает с уже скачанным data/ETHUSDT_M15.parquet.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
import risk_gate
from backtest.engine import run_portfolio_backtest
from backtest import strategies

SYMBOL = "ETHUSDT"
TRAIN_FRACTION = 0.7


def load_data() -> pd.DataFrame:
    tf_name = f"M{config.INTERVAL}" if config.INTERVAL.isdigit() else config.INTERVAL
    path = Path(config.DATA_DIR) / f"{SYMBOL}_{tf_name}.parquet"
    if not path.exists():
        print(f"Не найден {path}.")
        print(f"Сначала запустите: python bot\\fetch_history_bybit.py {SYMBOL}")
        sys.exit(1)
    return pd.read_parquet(path)


def summarize(trades, equity_df, starting_equity: float) -> dict:
    if not trades:
        return {"сделок": 0, "gross_$": 0.0, "cost_$": 0.0, "gross/сделку_$": 0.0, "costы_покрыты_%": 0.0, "доходность_%": 0.0}

    gross = sum(t.gross_pnl_usdt for t in trades)
    cost = sum(t.cost_usdt for t in trades)
    final_equity = equity_df["equity"].iloc[-1]

    return {
        "сделок": len(trades),
        "gross_$": round(gross, 2),
        "cost_$": round(cost, 2),
        "gross/сделку_$": round(gross / len(trades), 4),
        "costы_покрыты_%": round(gross / cost * 100, 1) if cost else 0.0,
        "доходность_%": round((final_equity / starting_equity - 1) * 100, 1),
    }


def main():
    df = load_data()
    df = strategies.add_adx_filtered_bollinger_signals(df)

    start, end = df["time_utc"].min(), df["time_utc"].max()
    split_point = start + (end - start) * TRAIN_FRACTION

    train_df = df[df["time_utc"] < split_point].reset_index(drop=True)
    test_df = df[df["time_utc"] >= split_point].reset_index(drop=True)

    print("=" * 70)
    print(f"Train/test валидация: {SYMBOL}, Mean-reversion + ADX ranging")
    print("=" * 70)
    print(f"Вся история: {start} -> {end} ({len(df)} свечей)")
    print(f"Train (70%): {train_df['time_utc'].min()} -> {train_df['time_utc'].max()} ({len(train_df)} свечей)")
    print(f"Test  (30%, НЕ ВИДЕЛИ при выборе монеты): "
          f"{test_df['time_utc'].min()} -> {test_df['time_utc'].max()} ({len(test_df)} свечей)")
    print()

    results = {}
    for label, part_df in [("TRAIN", train_df), ("TEST", test_df)]:
        trades, equity_df = run_portfolio_backtest(
            {SYMBOL: part_df},
            risk_gate.STARTING_BALANCE_USDT,
            strategies.adx_filtered_bollinger_entry_signal,
            strategies.bollinger_should_exit,
        )
        stats = summarize(trades, equity_df, risk_gate.STARTING_BALANCE_USDT)
        results[label] = stats

        print(f"{label}:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        print()

    print("-" * 70)
    train_gross = results["TRAIN"]["gross/сделку_$"]
    test_gross = results["TEST"]["gross/сделку_$"]

    if train_gross > 0 and test_gross > 0:
        print("-> Edge положителен И на train, И на отложенном test - уже не совпадение")
        print("   одного периода, более надёжный сигнал реального преимущества по ETH.")
    elif train_gross > 0 and test_gross <= 0:
        print("-> Train был в плюсе, но TEST (отложенные данные) - в минусе.")
        print("   Это симптом переподгонки/шума, а не устойчивого edge - НЕ сужаться до ETH")
        print("   на основании этого результата.")
    else:
        print("-> Сырой сигнал уже отрицателен на train - на ETH отдельно едва ли стоит")
        print("   сужаться, независимо от результата на test.")


if __name__ == "__main__":
    main()
