"""Печать отчёта и сохранение результатов портфельного бэктеста (Bybit, топ-N монет)."""

from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


def print_report(trades, equity_df: pd.DataFrame, starting_equity: float, title: str):
    print("=" * 60)
    print(title)
    print("=" * 60)
    print(f"Стартовый капитал: ${starting_equity:.2f}")

    if not trades:
        print("\nНи одной сделки не было открыто за весь период.")
        print("Возможные причины: EMA ни разу не пересеклись (маловероятно на 6+")
        print("месяцах), либо риск на минимальном ордере всегда был меньше $5.")
        return

    pnl = pd.Series([t.pnl_usdt for t in trades])
    gross_pnl = pd.Series([t.gross_pnl_usdt for t in trades])
    cost = pd.Series([t.cost_usdt for t in trades])
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    final_equity = equity_df["equity"].iloc[-1]
    total_return_pct = (final_equity / starting_equity - 1) * 100
    win_rate = len(wins) / len(pnl) * 100
    profit_factor = (wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else float("inf")

    running_max = equity_df["equity"].cummax()
    drawdown_pct = (equity_df["equity"] - running_max) / running_max * 100
    max_drawdown_pct = drawdown_pct.min()

    print(f"Конечный капитал:    ${final_equity:.2f}")
    print(f"Итоговая доходность: {total_return_pct:+.1f}%")
    print(f"Всего сделок:        {len(pnl)} (по {pd.Series([t.symbol for t in trades]).nunique()} монетам)")
    print(f"  из них прибыльных: {len(wins)} ({win_rate:.1f}%)")
    print(f"  из них убыточных:  {len(losses)}")
    pf_str = f"{profit_factor:.2f}" if profit_factor != float("inf") else "inf (убыточных сделок не было)"
    print(f"Profit factor:       {pf_str}")
    print(f"Средний P&L сделки:  ${pnl.mean():.2f}")

    print()
    print("Разбивка на сырой сигнал и costs (чтобы понять, ЧТО убивает результат):")
    print(f"  P&L ДО комиссии/funding (сырой сигнал): ${gross_pnl.sum():+.2f}")
    print(f"  Комиссия + funding за весь период:       ${-cost.sum():+.2f}")
    print(f"  P&L ПОСЛЕ costов (итог выше):             ${pnl.sum():+.2f}")
    if gross_pnl.sum() > 0:
        print("  -> Сырой сигнал в плюсе - costы съедают прибыль.")
    else:
        print("  -> Сырой сигнал УЖЕ в минусе, до всяких costов - дело не в комиссии/funding.")

    print(f"Макс. просадка:      {max_drawdown_pct:.1f}%")

    by_reason = pd.Series([t.exit_reason for t in trades]).value_counts()
    print(f"\nПричины закрытия сделок: {dict(by_reason)}")

    avg_hold_hours = pd.Series([(t.exit_time - t.entry_time).total_seconds() / 3600 for t in trades]).mean()
    print(f"Среднее время удержания позиции: {avg_hold_hours:.1f} ч")

    print()
    print("Разбивка по монетам (сколько каждая внесла в итог, отсортировано по P&L):")
    by_symbol = pd.DataFrame(
        {"symbol": [t.symbol for t in trades], "pnl": [t.pnl_usdt for t in trades]}
    ).groupby("symbol")["pnl"].agg(["sum", "count"]).sort_values("sum", ascending=False)
    for symbol, row in by_symbol.iterrows():
        print(f"  {symbol:12s}  P&L ${row['sum']:+8.2f}   сделок: {int(row['count'])}")

    print()
    print("ВАЖНО: funding rate - ПРИБЛИЖЕНИЕ (см. risk_gate.ASSUMED_FUNDING_RATE_PER_8H),")
    print("не измеренный факт для реального счёта. Комиссия 0.09% (taker) - измерена на")
    print("реальном счету Али (со скидкой MNT 10%) - изменится, если скидка отключится.")


def save_outputs(trades, equity_df: pd.DataFrame, out_dir: Path, plot_title: str, file_prefix: str = "backtest"):
    out_dir = Path(out_dir)

    if trades:
        trades_df = pd.DataFrame([t.__dict__ for t in trades])
        trades_path = out_dir / f"{file_prefix}_trades.csv"
        trades_df.to_csv(trades_path, index=False)
        print(f"\nЛог сделок сохранён: {trades_path}")

    plots_dir = out_dir / "plots"
    plots_dir.mkdir(exist_ok=True)

    plt.figure(figsize=(11, 5))
    plt.plot(range(len(equity_df)), equity_df["equity"])
    plt.title(plot_title)
    plt.xlabel("Сделка №")
    plt.ylabel("Капитал, USDT")
    plt.tight_layout()
    out_path = plots_dir / f"{file_prefix}_equity_curve.png"
    plt.savefig(out_path, dpi=120)
    print(f"График капитала сохранён: {out_path}")
