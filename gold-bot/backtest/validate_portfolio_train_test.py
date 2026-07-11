"""
Train/test валидация ЛУЧШЕГО найденного кандидата (Mean-reversion + ADX
ranging, Боллинджер 20/2.0, ADX<20) на ВСЁМ портфеле из 8 монет - до сих пор
train/test проверяли только на одной ETH, а не на всём портфеле. Единственный
цельный тест на полном общем периоде показал 60.9% покрытия costов - нужно
знать, устойчиво ли это, или это отчасти шум конкретного периода.

Делим общий пересекающийся период всех монет на train (первые 70% по
времени) и test (последние 30%, НЕ ВИДЕННЫЕ при выборе стратегии). Параметры
стратегии уже зафиксированы по прошлым тестам - здесь их НЕ подгоняем.

Не требует API-ключей - работает с уже скачанными data/*.parquet.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
import risk_gate
from backtest.engine import run_portfolio_backtest
from backtest import strategies
from backtest.run_backtest import load_symbol_list, load_raw_data

TRAIN_FRACTION = 0.7


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
    symbols = load_symbol_list()
    raw = load_raw_data(symbols)

    prepared = {symbol: strategies.add_adx_filtered_bollinger_signals(df) for symbol, df in raw.items()}

    common_start = max(df["time_utc"].min() for df in prepared.values())
    common_end = min(df["time_utc"].max() for df in prepared.values())
    split_point = common_start + (common_end - common_start) * TRAIN_FRACTION

    print("=" * 70)
    print("Train/test валидация портфеля: Mean-reversion + ADX ranging")
    print("=" * 70)
    print(f"Общий период: {common_start} -> {common_end}")
    print(f"Train (70%): {common_start} -> {split_point}")
    print(f"Test  (30%, НЕ ВИДЕЛИ при выборе стратегии): {split_point} -> {common_end}")
    print()

    results = {}
    for label, (lo, hi) in [("TRAIN", (common_start, split_point)), ("TEST", (split_point, common_end))]:
        part_dfs = {}
        for symbol, df in prepared.items():
            part = df[(df["time_utc"] >= lo) & (df["time_utc"] < hi)].reset_index(drop=True)
            if not part.empty:
                part_dfs[symbol] = part

        trades, equity_df = run_portfolio_backtest(
            part_dfs,
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
        print("   одного периода, более надёжный сигнал реального преимущества.")
        print("   Есть смысл дожимать именно эту идею дальше.")
    elif train_gross > 0 and test_gross <= 0:
        print("-> Train в плюсе, но TEST (отложенные данные) - в минусе.")
        print("   Симптом переподгонки/шума за счёт конкретного периода - результат")
        print("   60.9% costов покрыто на полном периоде был отчасти удачей, не устойчивым edge.")
    else:
        print("-> Сырой сигнал уже отрицателен на train - результат на полном периоде")
        print("   был обеспечен в основном test-частью, доверять ему не стоит.")


if __name__ == "__main__":
    main()
