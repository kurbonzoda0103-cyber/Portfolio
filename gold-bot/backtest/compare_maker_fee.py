"""
Проверка гипотезы: разрыв в costах у лучшей стратегии (Mean-reversion + ADX
ranging, 60.9% costов покрыто) закрывается не изменением сигнала, а сменой
исполнения - лимитный ордер на вход (maker-комиссия) вместо market (taker).

Идея обоснована структурой стратегии: вход - это ровно момент, когда цена
касается известной ЗАРАНЕЕ границы полосы Боллинджера - лимитку можно
поставить на этот уровень до входа, а не гнаться за ценой market-ордером.
Выход (и стоп, и возврат к средней) в этом сравнении ОСТАЁТСЯ taker -
консервативно, чтобы не предполагать оптимистично maker-исполнение сразу на
обеих ногах сделки.

Параметр MAKER_FEE_PCT в risk_gate.py - ПРИБЛИЖЕНИЕ (стандартная ставка
Bybit для не-VIP аккаунта), не измерено на реальном счету - если результат
здесь выглядит многообещающе, перед тем как доверять ему, стоит свериться с
реальной комиссией счёта.

Не меняет и не трогает risk_gate.compute_costs_usdt (используемую во всех
остальных сравнениях стратегий) - результат этого скрипта НЕ смешивается с
основной таблицей run_backtest.py.

Не требует API-ключей - работает с уже скачанными data/*.parquet.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import risk_gate
from backtest.engine import run_portfolio_backtest
from backtest import strategies
from backtest.run_backtest import load_symbol_list, load_raw_data, align_to_common_window


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
    aligned, common_start, common_end = align_to_common_window(prepared)

    print("=" * 70)
    print("Mean-reversion + ADX ranging: taker (эталон) vs maker-вход (гипотеза)")
    print(f"Период: {common_start} -> {common_end}")
    print("=" * 70)

    rows = {}
    for label, cost_fn in [
        ("taker (эталон, как в run_backtest.py)", risk_gate.compute_costs_usdt),
        ("maker на вход + taker на выход", risk_gate.compute_costs_usdt_maker_entry),
    ]:
        trades, equity_df = run_portfolio_backtest(
            aligned,
            risk_gate.STARTING_BALANCE_USDT,
            strategies.adx_filtered_bollinger_entry_signal,
            strategies.bollinger_should_exit,
            cost_fn=cost_fn,
        )
        rows[label] = summarize(trades, equity_df, risk_gate.STARTING_BALANCE_USDT)

    table = pd.DataFrame(rows).T
    print(table.to_string())

    taker_cost = rows["taker (эталон, как в run_backtest.py)"]["costы_покрыты_%"]
    maker_cost = rows["maker на вход + taker на выход"]["costы_покрыты_%"]

    print()
    if maker_cost >= 100:
        print(f"-> С maker-входом costы_покрыты_% = {maker_cost}% - при этом допущении стратегия становится")
        print("   прибыльной. НО: MAKER_FEE_PCT не измерен на реальном счету, а реальное исполнение лимитки")
        print("   не гарантировано (можно не успеть на уровне при быстром движении цены) - это гипотеза,")
        print("   а не подтверждённый результат.")
    else:
        print(f"-> Даже с maker-входом costы_покрыты_% = {maker_cost}% (было {taker_cost}%) - разрыв не закрыт")
        print("   полностью только сменой исполнения. Комиссия - не единственная причина отставания.")


if __name__ == "__main__":
    main()
