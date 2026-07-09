"""
Этап 3: запуск бэктеста ORB-стратегии на исторических M15-данных золота.

Не требует MT5 - работает с data/{SYMBOL}_M15.parquet (Этап 1), можно запускать
где угодно, где стоит Python. Честно печатает результат, включая отрицательный -
подгонять параметры под красивую кривую доходности не будем (см. правила проекта:
это оверфиттинг, отрицательный результат - тоже результат).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import matplotlib.pyplot as plt

import config
from backtest.engine import run_backtest
from backtest import strategies


def load_data() -> pd.DataFrame:
    path = Path(config.DATA_DIR) / f"{config.SYMBOL}_M15.parquet"
    if not path.exists():
        print(f"Не найден файл {path}.")
        print("Сначала запустите bot/fetch_history.py (Этап 1), чтобы скачать историю.")
        sys.exit(1)
    return pd.read_parquet(path)


def print_report(trades, equity_df: pd.DataFrame, starting_equity: float):
    print("=" * 60)
    print(f"Результаты бэктеста ORB, {config.SYMBOL}, окно {config.TRADING_WINDOW_START}-{config.TRADING_WINDOW_END}")
    print("=" * 60)
    print(f"Параметры ORB: диапазон {strategies.ORB_MINUTES} мин, TP = {strategies.ORB_RR}R")
    print(f"Стартовый капитал: ${starting_equity:.2f}")

    if not trades:
        print("\nНи одной сделки не было открыто за весь период.")
        print("Возможные причины: диапазон открытия ни разу не пробивался, слишком")
        print("мало баров в окне, либо риск на минимальном лоте всегда превышал 1%.")
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

    print(f"Конечный капитал:   ${final_equity:.2f}")
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
        print("     меньшего числа/более качественных сделок, а не выбрасывать идею пробоя.")
    else:
        print("  -> Сырой сигнал УЖЕ в минусе, до всяких costов. Дело не в спреде -")
        print("     у самого пробоя диапазона нет edge на этом инструменте/окне в таком виде.")
    print(f"Макс. просадка:      {max_drawdown_pct:.1f}%")

    by_reason = pd.Series([t.exit_reason for t in trades]).value_counts()
    print(f"\nПричины закрытия сделок: {dict(by_reason)}")

    print()
    print("ВАЖНО: спред взят из ОДНОГО вечернего замера ($0.52 на лот 0.01) - это")
    print("приближение, а не факт на каждый час торгового окна. Перед тем как")
    print("доверять этим цифрам, нужно перемерить спред bot/check_connection.py")
    print("несколько раз в разное время внутри 17:00-21:00 и обновить")
    print("config.py -> ASSUMED_SPREAD_POINTS.")
    print()
    print("Исторические новости (NFP/ФРС/CPI) сейчас НЕ исключены из этого прогона -")
    print("config.py -> NEWS_DATES_UTC пуст (см. TODO там же). Результат может быть")
    print("оптимистичнее реального из-за нескольких дней с резкими новостными свечками.")


def main():
    df = load_data()
    trades, equity_df = run_backtest(df, config.STARTING_BALANCE_USD)
    print_report(trades, equity_df, config.STARTING_BALANCE_USD)

    out_dir = Path(__file__).resolve().parent
    if trades:
        trades_df = pd.DataFrame([t.__dict__ for t in trades])
        trades_df.to_csv(out_dir / "trades.csv", index=False)
        print(f"\nЛог сделок сохранён: {out_dir / 'trades.csv'}")

    plots_dir = out_dir / "plots"
    plots_dir.mkdir(exist_ok=True)

    plt.figure(figsize=(11, 5))
    plt.plot(range(len(equity_df)), equity_df["equity"])
    plt.title(f"Кривая капитала: ORB, {config.SYMBOL} ({config.TRADING_WINDOW_START}-{config.TRADING_WINDOW_END})")
    plt.xlabel("Сделка №")
    plt.ylabel("Капитал, $")
    plt.tight_layout()
    out_path = plots_dir / "equity_curve.png"
    plt.savefig(out_path, dpi=120)
    print(f"График капитала сохранён: {out_path}")


if __name__ == "__main__":
    main()
