"""
ДИАГНОСТИКА (не для реальной торговли): у всех 5 стратегий в run_backtest.py
доходность вышла на -98.0% - капитал упирается в механический пол, где риск
2% на сделку уже не дотягивает до минимального ордера Bybit ($5), и торговля
останавливается сама по себе, независимо от качества стратегии.

Mean-reversion (Боллинджер) была единственной с положительным сырым edge - но
тоже упёрлась в этот пол. Этот скрипт прогоняет её же с намного большим
стартовым капиталом (условным, только для диагностики - НЕ меняет
risk_gate.STARTING_BALANCE_USDT, реальный конфиг остаётся $50), чтобы
проверить: если бы капитала хватало пережить просадки по пути, компаундится
ли эта стратегия нормально, или она в любом случае в итоге безубыточна/убыточна.

Не требует API-ключей - работает с уже скачанными data/*.parquet.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from backtest.engine import run_portfolio_backtest
from backtest import strategies
from backtest.run_backtest import load_symbol_list, load_raw_data, align_to_common_window

DIAGNOSTIC_STARTING_EQUITY = 5000.0  # в 100 раз больше реального $50 - только чтобы обойти MIN_ORDER_USDT пол


def main():
    symbols = load_symbol_list()
    raw = load_raw_data(symbols)

    prepared = {symbol: strategies.add_bollinger_signals(df) for symbol, df in raw.items()}
    aligned, common_start, common_end = align_to_common_window(prepared)

    trades, equity_df = run_portfolio_backtest(
        aligned, DIAGNOSTIC_STARTING_EQUITY, strategies.bollinger_entry_signal, strategies.bollinger_should_exit
    )

    print("=" * 70)
    print(f"ДИАГНОСТИКА: Mean-reversion (Боллинджер), условный старт ${DIAGNOSTIC_STARTING_EQUITY:.0f}")
    print(f"(в {DIAGNOSTIC_STARTING_EQUITY / 50:.0f}x больше реального $50 - только чтобы увидеть,")
    print("компаундится ли стратегия нормально без упора в минимальный ордер)")
    print("=" * 70)

    if not trades:
        print("Сделок не было.")
        return

    pnl = pd.Series([t.pnl_usdt for t in trades])
    gross = pd.Series([t.gross_pnl_usdt for t in trades])
    final_equity = equity_df["equity"].iloc[-1]
    total_return_pct = (final_equity / DIAGNOSTIC_STARTING_EQUITY - 1) * 100

    running_max = equity_df["equity"].cummax()
    drawdown_pct = (equity_df["equity"] - running_max) / running_max * 100
    max_drawdown_pct = drawdown_pct.min()

    print(f"Сделок: {len(trades)}")
    print(f"Итоговая доходность: {total_return_pct:+.1f}%")
    print(f"Макс. просадка: {max_drawdown_pct:.1f}%")
    print(f"Сырой P&L: ${gross.sum():+.2f}   Чистый P&L: ${pnl.sum():+.2f}")
    print()

    if total_return_pct > 0:
        print("-> С запасом капитала стратегия компаундится в плюс. Проблема была именно")
        print("   в нехватке капитала относительно минимального ордера, а не в самой идее.")
        print("   Стоит подумать про меньше монет одновременно и/или больше стартовый капитал.")
    else:
        print("-> Даже с большим капиталом стратегия в итоге убыточна - дело не в")
        print("   минимальном ордере, идея сама по себе не работает на этих данных.")


if __name__ == "__main__":
    main()
