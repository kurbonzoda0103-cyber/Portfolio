"""
Движок бэктеста для ПОРТФЕЛЯ монет на Bybit (топ-10 по объёму, независимые
позиции по каждой монете, общий баланс и общие дневные риск-лимиты).

Каждая монета торгуется своей собственной EMA trend-following стратегией
независимо, но:
- equity (баланс) один общий на весь портфель;
- дневные лимиты (2 убыточные сделки, -6% в день) считаются по ВСЕМ монетам
  вместе - одна плохая монета может остановить торговлю по всем остальным
  до конца дня;
- эффективное плечо (5x) ограничивает СУММАРНЫЙ номинал открытых позиций по
  всем монетам, а не каждую монету отдельно (см. risk_gate.py).

Позиции держатся, пока не сработает стоп или сигнал стратегии на выход - без
торгового окна, крипта торгуется 24/7.

Размер позиции, проверка стопа и дневные лимиты - ВСЕГДА через risk_gate.py.
"""

import sys
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import risk_gate

FUNDING_HOURS_UTC = {0, 8, 16}  # часы UTC начисления funding на Bybit (стандарт для большинства USDT-перпов)


@dataclass
class Trade:
    symbol: str
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


def _combine_symbols(symbol_dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Склеивает бары всех монет в один датафрейм, отсортированный по времени -
    чтобы события по разным монетам обрабатывались в правильном хронологическом
    порядке (это важно, т.к. equity и дневные лимиты общие на весь портфель)."""

    parts = []
    for symbol, df in symbol_dfs.items():
        part = df.copy()
        part["symbol"] = symbol
        parts.append(part)

    combined = pd.concat(parts, ignore_index=True)
    return combined.sort_values(["time_utc", "symbol"]).reset_index(drop=True)


def run_portfolio_backtest(
    symbol_dfs: dict[str, pd.DataFrame],
    starting_equity: float,
    entry_signal_fn,
    should_exit_fn,
):
    """symbol_dfs: {symbol: df}, каждый df уже должен содержать все колонки,
    нужные entry_signal_fn/should_exit_fn (см. strategies.py - там разные
    стратегии готовят разные колонки: ema_fast/ema_slow/atr/cross для
    EMA-тренда, donchian_high/low для пробоя и т.д.), и колонку time_utc.

    entry_signal_fn(bar) -> Signal | None
    should_exit_fn(bar, direction) -> bool

    Движок не привязан к конкретной стратегии - разные идеи (EMA-тренд,
    пробой диапазона, mean-reversion, ADX-фильтр) передаются как обычные
    функции, чтобы не плодить копию всего движка под каждую.

    Возвращает (список Trade, DataFrame кривой капитала).
    """

    combined = _combine_symbols(symbol_dfs)

    trades: list[Trade] = []
    equity = starting_equity
    equity_curve = [{"time": combined["time_utc"].iloc[0] if len(combined) else None, "equity": equity}]

    daily_state = risk_gate.DailyState()
    positions: dict[str, dict] = {}  # symbol -> открытая позиция (максимум одна на монету одновременно)

    for _, bar in combined.iterrows():
        symbol = bar["symbol"]
        day = bar["time_utc"].date()
        if daily_state.day != day:
            daily_state.reset(day, equity)

        position = positions.get(symbol)

        if position is not None:
            hit_stop = (
                position["direction"] == "long" and bar["low"] <= position["stop_price"]
            ) or (
                position["direction"] == "short" and bar["high"] >= position["stop_price"]
            )
            exit_by_signal = should_exit_fn(bar, position["direction"])

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
                        symbol=symbol,
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
                daily_state.open_notional_usdt -= position["notional_usdt"]
                daily_state.register_trade_result(pnl)
                equity_curve.append({"time": bar["time_utc"], "equity": equity})
                del positions[symbol]
                position = None

        # Проверяем вход даже сразу после закрытия на этом же баре - если EMA
        # развернулись, trend-following логично сразу переворачивает позицию.
        # has_reached_daily_trade_quota - это не риск-лимит, а осознанная
        # селективность (пара сделок в день по всему портфелю, не любой сигнал
        # по любой из монет) - см. risk_gate.MAX_NEW_POSITIONS_PER_DAY.
        if (
            position is None
            and risk_gate.can_trade_today(daily_state)
            and not risk_gate.has_reached_daily_trade_quota(daily_state)
        ):
            signal = entry_signal_fn(bar)
            if signal is not None:
                try:
                    qty = risk_gate.validate_order(equity, signal.entry_price, signal.stop_price, daily_state)
                except risk_gate.OrderRejected:
                    qty = None

                if qty:
                    daily_state.new_positions_today += 1
                    notional_usdt = qty * signal.entry_price
                    positions[symbol] = {
                        "direction": signal.direction,
                        "entry_time": bar["time_utc"],
                        "entry_price": signal.entry_price,
                        "stop_price": signal.stop_price,
                        "qty": qty,
                        "notional_usdt": notional_usdt,
                    }
                    daily_state.open_notional_usdt += notional_usdt

    return trades, pd.DataFrame(equity_curve)
