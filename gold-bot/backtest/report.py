"""Общая печать отчёта и сохранение результатов - переиспользуется разными
скриптами запуска бэктеста (run_backtest.py, run_backtest_trend.py и т.д.),
чтобы не дублировать одинаковую логику отчёта под каждую стратегию."""

from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


DEFAULT_SPREAD_NOTE = (
    "ВАЖНО: спред взят из ОДНОГО вечернего замера ($0.52 на лот 0.01) - это\n"
    "приближение, а не факт на каждый час торгового окна (config.py -> ASSUMED_SPREAD_POINTS)."
)


def print_report(
    trades, equity_df: pd.DataFrame, starting_equity: float, title: str, spread_note: str = DEFAULT_SPREAD_NOTE
):
    print("=" * 60)
    print(title)
    print("=" * 60)
    print(f"Стартовый капитал: ${starting_equity:.2f}")

    if not trades:
        print("\nНи одной сделки не было открыто за весь период.")
        print("Возможные причины: сигнал ни разу не появился (например, пробой всегда")
        print("шёл против тренда), слишком мало баров в окне, либо риск на минимальном")
        print("лоте всегда превышал 1%.")
        return

    pnl = pd.Series([t.pnl_usd for t in trades])
    gross_pnl = pd.Series([t.gross_pnl_usd for t in trades])
    cost = pd.Series([t.cost_usd for t in trades])
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
    print(f"Всего сделок:        {len(pnl)}")
    print(f"  из них прибыльных: {len(wins)} ({win_rate:.1f}%)")
    print(f"  из них убыточных:  {len(losses)}")
    pf_str = f"{profit_factor:.2f}" if profit_factor != float("inf") else "inf (убыточных сделок не было)"
    print(f"Profit factor:       {pf_str}")
    print(f"Средний P&L сделки:  ${pnl.mean():.2f}")

    print()
    print("Разбивка на сырой сигнал и costs (чтобы понять, ЧТО убивает результат):")
    print(f"  P&L ДО спреда/комиссии (сырой сигнал): ${gross_pnl.sum():+.2f}")
    print(f"  Спред + комиссия за весь период:       ${-cost.sum():+.2f}")
    print(f"  P&L ПОСЛЕ costов (итог выше):           ${pnl.sum():+.2f}")
    if gross_pnl.sum() > 0:
        print("  -> Сырой сигнал в плюсе - costы съедают прибыль. Стоит смотреть в сторону")
        print("     меньшего числа/более качественных сделок, а не выбрасывать идею.")
    else:
        print("  -> Сырой сигнал УЖЕ в минусе, до всяких costов. Дело не в спреде -")
        print("     у сигнала нет edge на этом инструменте/окне в таком виде.")

    print(f"Макс. просадка:      {max_drawdown_pct:.1f}%")

    by_reason = pd.Series([t.exit_reason for t in trades]).value_counts()
    print(f"\nПричины закрытия сделок: {dict(by_reason)}")

    print()
    print(spread_note)
    print("Исторические новости (NFP/ФРС/CPI) сейчас НЕ исключены - config.py -> NEWS_DATES_UTC пуст.")


def save_outputs(trades, equity_df: pd.DataFrame, out_dir: Path, plot_title: str, file_prefix: str):
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
    plt.ylabel("Капитал, $")
    plt.tight_layout()
    out_path = plots_dir / f"{file_prefix}_equity_curve.png"
    plt.savefig(out_path, dpi=120)
    print(f"График капитала сохранён: {out_path}")
