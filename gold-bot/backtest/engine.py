"""
Движок бэктеста: берёт исторические M15-свечи, для каждого торгового дня
прогоняет стратегию внутри торгового окна (config.TRADING_WINDOW_START-
TRADING_WINDOW_END), честно считает P&L с учётом спреда и комиссии, размер
позиции - по риску 1% на сделку, с проверкой жёстких лимитов риск-менеджмента
из config.py.

Все сделки закрываются до конца торгового окна - переносов через ночь нет,
поэтому своп (плата за перенос позиции) в расчётах не участвует - это
соответствует правилу проекта "все позиции закрываются до конца окна".
"""

import sys
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from backtest.strategies import opening_range_breakout, Signal

POINT = 0.01  # шаг цены золота у этого брокера (см. bot/check_connection.py)


@dataclass
class Trade:
    date: object
    direction: str
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    stop_price: float
    take_profit_price: float
    lot: float
    pnl_usd: float
    exit_reason: str  # "stop", "take_profit" или "window_close"


def is_news_blackout(ts_local: pd.Timestamp) -> bool:
    """ts_local - локальное время (UTC+MY_TIMEZONE_OFFSET_HOURS). Список новостей в config.py - в UTC.

    Список сейчас пуст (см. TODO в config.py) - функция готова к работе, но
    реального эффекта на бэктест пока не даёт, пока список не заполнен.
    """
    if not config.NEWS_DATES_UTC:
        return False
    ts_utc = ts_local - pd.Timedelta(hours=config.MY_TIMEZONE_OFFSET_HOURS)
    blackout = pd.Timedelta(minutes=config.NEWS_BLACKOUT_MINUTES)
    for news_str in config.NEWS_DATES_UTC:
        if abs(ts_utc - pd.Timestamp(news_str)) <= blackout:
            return True
    return False


def size_position(equity: float, entry_price: float, stop_price: float) -> float:
    """Лот от риска на сделку (config.RISK_PER_TRADE_PCT), с ограничением по
    эффективному плечу (config.MAX_EFFECTIVE_LEVERAGE) и минимальному лоту.

    Округляем ВНИЗ до шага MIN_LOT - округлять вверх нельзя, это превысит
    разрешённый риск 1% на сделку.
    """
    risk_amount = equity * config.RISK_PER_TRADE_PCT / 100
    stop_distance = abs(entry_price - stop_price)
    if stop_distance <= 0:
        return 0.0

    lot = risk_amount / (stop_distance * config.CONTRACT_SIZE)

    max_lot_by_leverage = (config.MAX_EFFECTIVE_LEVERAGE * equity) / (entry_price * config.CONTRACT_SIZE)
    lot = min(lot, max_lot_by_leverage)

    lot = (lot // config.MIN_LOT) * config.MIN_LOT
    return max(0.0, round(lot, 2))


def simulate_trade(signal: Signal, day_bars: pd.DataFrame, equity: float, effective_end: pd.Timestamp) -> Trade | None:
    lot = size_position(equity, signal.entry_price, signal.stop_price)
    if lot < config.MIN_LOT:
        return None  # риск на минимальном лоте уже больше 1% - сделку не открываем

    bars_after_entry = day_bars[day_bars["time_local"] > signal.entry_time]

    exit_price = None
    exit_time = None
    exit_reason = None

    for _, bar in bars_after_entry.iterrows():
        if bar["time_local"] >= effective_end:
            break

        if signal.direction == "long":
            if bar["low"] <= signal.stop_price:
                exit_price, exit_reason = signal.stop_price, "stop"
            elif bar["high"] >= signal.take_profit_price:
                exit_price, exit_reason = signal.take_profit_price, "take_profit"
        else:
            if bar["high"] >= signal.stop_price:
                exit_price, exit_reason = signal.stop_price, "stop"
            elif bar["low"] <= signal.take_profit_price:
                exit_price, exit_reason = signal.take_profit_price, "take_profit"

        if exit_price is not None:
            exit_time = bar["time_local"]
            break

    if exit_price is None:
        # Не задело ни стоп, ни тейк - принудительно закрываем по правилу проекта
        # "все позиции закрываются до конца окна".
        before_end = day_bars[day_bars["time_local"] < effective_end]
        if before_end.empty:
            return None
        last_bar = before_end.iloc[-1]
        exit_price, exit_time, exit_reason = last_bar["close"], last_bar["time_local"], "window_close"

    direction_sign = 1 if signal.direction == "long" else -1
    gross_pnl = (exit_price - signal.entry_price) * direction_sign * config.CONTRACT_SIZE * lot
    # Спред считаем один раз за сделку (упрощение - нет отдельных bid/ask в истории,
    # см. ASSUMED_SPREAD_POINTS в config.py и предупреждение в README).
    spread_cost = config.ASSUMED_SPREAD_POINTS * POINT * config.CONTRACT_SIZE * lot
    commission_cost = config.COMMISSION_PER_LOT_USD * lot
    pnl_usd = gross_pnl - spread_cost - commission_cost

    return Trade(
        date=signal.entry_time.date(),
        direction=signal.direction,
        entry_time=signal.entry_time,
        entry_price=signal.entry_price,
        exit_time=exit_time,
        exit_price=exit_price,
        stop_price=signal.stop_price,
        take_profit_price=signal.take_profit_price,
        lot=lot,
        pnl_usd=pnl_usd,
        exit_reason=exit_reason,
    )


def run_backtest(df: pd.DataFrame, starting_equity: float):
    """Возвращает (список Trade, DataFrame кривой капитала)."""

    trades: list[Trade] = []
    equity = starting_equity
    equity_curve = [{"date": None, "equity": equity}]

    for date, day_df in df.groupby(df["time_local"].dt.date):
        # Правило проекта: перед выходными позиции не держим и не открываем.
        if pd.Timestamp(date).weekday() >= 5 and config.NO_POSITIONS_OVER_WEEKEND:
            continue

        window_start = pd.Timestamp(f"{date} {config.TRADING_WINDOW_START}")
        window_end_full = pd.Timestamp(f"{date} {config.TRADING_WINDOW_END}")
        effective_end = window_end_full - config.FORCE_CLOSE_BEFORE_WINDOW_END

        if is_news_blackout(window_start) or is_news_blackout(effective_end):
            continue

        day_bars = day_df[(day_df["time_local"] >= window_start) & (day_df["time_local"] < effective_end)]
        day_bars = day_bars.sort_values("time_local")
        if day_bars.empty:
            continue

        # Лимиты MAX_LOSING_TRADES_PER_DAY / MAX_DAILY_LOSS_PCT сейчас не могут
        # сработать - стратегия даёт максимум 1 сделку в день. Оставлены здесь
        # как каркас для будущих стратегий с несколькими входами за окно.
        signal = opening_range_breakout(day_bars)
        if signal is None:
            continue

        trade = simulate_trade(signal, day_bars, equity, effective_end)
        if trade is None:
            continue

        equity += trade.pnl_usd
        trades.append(trade)
        equity_curve.append({"date": date, "equity": equity})

    return trades, pd.DataFrame(equity_curve)
