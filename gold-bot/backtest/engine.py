"""
Движок бэктеста для BTCUSDT на Bybit. В отличие от MT5-версии (окно 17:00-21:00,
максимум 1 сделка в день, лоты) здесь позиции держатся, пока не сработает стоп
или сигнал стратегии на выход - крипта торгуется 24/7, EMA trend-following по
своей природе держит позицию, пока не развернётся тренд.

Размер позиции, проверка стопа и дневные лимиты - ВСЕГДА через risk_gate.py,
движок сам ничего не считает по риску напрямую (см. risk_gate.py - там
объяснено, почему это отдельный модуль, который стратегия не может обойти).

Комиссия (taker) и funding считаются через risk_gate.compute_costs_usdt -
funding начисляется, если позиция была открыта в момент 00:00/08:00/16:00 UTC
(стандартное время начисления funding для большинства USDT-перпов на Bybit).
"""

import sys
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import risk_gate
from backtest import strategies

FUNDING_HOURS_UTC = {0, 8, 16}  # часы UTC начисления funding на Bybit (стандарт для большинства USDT-перпов)


@dataclass
class Trade:
    direction: str
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    stop_price: float
    qty: float
    gross_pnl_usdt: float
    cost_usdt: float
    pnl_usdt: float
    exit_reason: str  # "stop" или "signal_exit"
    funding_periods: int


def count_funding_periods(entry_time: pd.Timestamp, exit_time: pd.Timestamp) -> int:
    """Сколько раз позиция была открыта в момент начисления funding (00:00/08:00/16:00 UTC)."""
    if exit_time <= entry_time:
        return 0
    hours = pd.date_range(entry_time.ceil("h"), exit_time, freq="1h")
    return sum(1 for h in hours if h.hour in FUNDING_HOURS_UTC)


def run_backtest(df: pd.DataFrame, starting_equity: float):
    """df должен уже содержать колонки ema_fast/ema_slow/atr/cross
    (см. strategies.add_ema_signals) и time_utc, отсортирован по времени.

    Возвращает (список Trade, DataFrame кривой капитала).
    """

    trades: list[Trade] = []
    equity = starting_equity
    equity_curve = [{"time": df["time_utc"].iloc[0] if len(df) else None, "equity": equity}]

    daily_state = risk_gate.DailyState()
    position = None  # None или dict с текущей открытой позицией

    for _, bar in df.iterrows():
        day = bar["time_utc"].date()
        if daily_state.day != day:
            daily_state.reset(day, equity)

        if position is not None:
            hit_stop = (
                position["direction"] == "long" and bar["low"] <= position["stop_price"]
            ) or (
                position["direction"] == "short" and bar["high"] >= position["stop_price"]
            )
            exit_by_signal = strategies.should_exit_by_signal(bar, position["direction"])

            if hit_stop or exit_by_signal:
                exit_price = position["stop_price"] if hit_stop else bar["close"]
                exit_reason = "stop" if hit_stop else "signal_exit"

                funding_periods = count_funding_periods(position["entry_time"], bar["time_utc"])
                direction_sign = 1 if position["direction"] == "long" else -1
                gross_pnl = (exit_price - position["entry_price"]) * direction_sign * position["qty"]
                costs = risk_gate.compute_costs_usdt(
                    position["qty"], position["entry_price"], exit_price, funding_periods
                )
                pnl = gross_pnl - costs["total_cost_usdt"]

                trades.append(
                    Trade(
                        direction=position["direction"],
                        entry_time=position["entry_time"],
                        entry_price=position["entry_price"],
                        exit_time=bar["time_utc"],
                        exit_price=exit_price,
                        stop_price=position["stop_price"],
                        qty=position["qty"],
                        gross_pnl_usdt=gross_pnl,
                        cost_usdt=costs["total_cost_usdt"],
                        pnl_usdt=pnl,
                        exit_reason=exit_reason,
                        funding_periods=funding_periods,
                    )
                )

                equity += pnl
                daily_state.register_trade_result(pnl)
                equity_curve.append({"time": bar["time_utc"], "equity": equity})
                position = None

        # Проверяем вход даже сразу после закрытия на этом же баре - если EMA
        # развернулись, trend-following логично сразу переворачивает позицию,
        # а не ждёт следующего бара.
        if position is None and risk_gate.can_trade_today(daily_state):
            signal = strategies.entry_signal(bar)
            if signal is not None:
                try:
                    qty = risk_gate.validate_order(equity, signal.entry_price, signal.stop_price, daily_state)
                except risk_gate.OrderRejected:
                    qty = None

                if qty:
                    position = {
                        "direction": signal.direction,
                        "entry_time": bar["time_utc"],
                        "entry_price": signal.entry_price,
                        "stop_price": signal.stop_price,
                        "qty": qty,
                    }

    return trades, pd.DataFrame(equity_curve)
