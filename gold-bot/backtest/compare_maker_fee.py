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
    scenarios = [
        (
            "taker (эталон, как в run_backtest.py)",
            strategies.adx_filtered_bollinger_entry_signal,
            strategies.bollinger_should_exit,
            risk_gate.compute_costs_usdt,
            None,
        ),
        (
            "maker на вход + taker на выход",
            strategies.adx_filtered_bollinger_entry_signal,
            strategies.bollinger_should_exit,
            risk_gate.compute_costs_usdt_maker_entry,
            None,
        ),
        (
            "maker на вход + maker на сигнальный выход (стоп - taker)",
            strategies.adx_filtered_bollinger_entry_signal,
            strategies.bollinger_should_exit,
            risk_gate.compute_costs_usdt_maker_entry_and_exit,
            None,
        ),
        (
            "то же + буфер проскальзывания (исполнение ПО ЦЕНЕ ОРДЕРА, не по close)",
            strategies.adx_filtered_bollinger_entry_signal_buffered,
            strategies.bollinger_should_exit_buffered,
            risk_gate.compute_costs_usdt_maker_entry_and_exit,
            strategies.bollinger_signal_exit_price,
        ),
    ]
    for label, entry_fn, exit_fn, cost_fn, signal_exit_price_fn in scenarios:
        trades, equity_df = run_portfolio_backtest(
            aligned,
            risk_gate.STARTING_BALANCE_USDT,
            entry_fn,
            exit_fn,
            cost_fn=cost_fn,
            signal_exit_price_fn=signal_exit_price_fn,
        )
        rows[label] = summarize(trades, equity_df, risk_gate.STARTING_BALANCE_USDT)

    table = pd.DataFrame(rows).T
    print(table.to_string())

    taker_cost = rows["taker (эталон, как в run_backtest.py)"]["costы_покрыты_%"]
    optimistic_cost = rows["maker на вход + maker на сигнальный выход (стоп - taker)"]["costы_покрыты_%"]
    buffered_label = "то же + буфер проскальзывания (исполнение ПО ЦЕНЕ ОРДЕРА, не по close)"
    buffered_cost = rows[buffered_label]["costы_покрыты_%"]

    print()
    print(f"Оптимистичный maker-сценарий (гарантированное исполнение): {optimistic_cost}% costов покрыто.")
    print(f"С буфером проскальзывания (более честная модель очереди): {buffered_cost}% costов покрыто.")
    print()
    if buffered_cost >= 100:
        print(f"-> Даже с более пессимистичным допущением про исполнение (буфер {strategies.LIMIT_FILL_BUFFER_PCT*100:.2f}%)")
        print(f"   результат остаётся прибыльным ({buffered_cost}%, было {taker_cost}% на taker) - устойчивее, чем")
        print("   казалось по оптимистичному сценарию. Но MAKER_FEE_PCT и глубина реальной очереди на уровне")
        print("   всё ещё не измерены на вашем счету - перед реальными деньгами стоит свериться с фактом.")
    else:
        print(f"-> С более пессимистичным допущением про исполнение результат падает ниже 100%")
        print(f"   ({buffered_cost}%, было {optimistic_cost}% в оптимистичном сценарии) - оптимистичная maker-модель")
        print("   переоценивала устойчивость edge. Разница показывает, насколько результат чувствителен")
        print("   к качеству реального исполнения, а не только к ставке комиссии.")


if __name__ == "__main__":
    main()
