"""
Стратегии для бэктеста. Каждая стратегия получает свечи одного торгового дня,
уже обрезанные по торговому окну (config.TRADING_WINDOW_START-TRADING_WINDOW_END),
и возвращает Signal (сигнал на вход) или None, если сигнала не было.

Параметры стратегий ниже - это ПЕРВОЕ ПРИБЛИЖЕНИЕ для проверки на истории, а не
финально настроенные числа. Не подгоняем их под красивый результат бэктеста -
если стратегия покажет себя плохо, так и скажем, а не будем крутить параметры,
пока не получится нужная кривая доходности (это оверфиттинг).
"""

from dataclasses import dataclass

import pandas as pd

# --- Opening Range Breakout (ORB) ---
# Идея: в начале торгового окна (пересечение сессий Лондон+Нью-Йорк) волатильность
# резко растёт и часто задаёт направление на весь день - это подтвердили данные
# этапа 2 (research/hourly_volatility.py: пик волатильности именно в первые часы
# окна, 17:00-18:00). Берём диапазон первых ORB_MINUTES минут окна, ждём пробоя
# в одну из сторон, входим по пробою.
ORB_MINUTES = 30           # длина "открывающего диапазона" в минутах
ORB_STOP_BUFFER_USD = 0.0  # доп. буфер за границу диапазона для стоп-лосса (0 = стоп ровно на границе)
ORB_RR = 1.5               # тейк-профит как множитель риска (1.5 = TP на расстоянии 1.5 * риск)


@dataclass
class Signal:
    direction: str            # "long" или "short"
    entry_price: float
    stop_price: float
    take_profit_price: float
    entry_time: pd.Timestamp


def opening_range_breakout(day_bars: pd.DataFrame) -> Signal | None:
    """day_bars - M15 свечи одного дня внутри торгового окна, отсортированы по времени."""

    bar_minutes = 15  # ожидаем M15
    orb_bar_count = max(1, ORB_MINUTES // bar_minutes)

    if len(day_bars) <= orb_bar_count:
        return None  # мало баров в окне (например, укороченный день) - пропускаем

    range_bars = day_bars.iloc[:orb_bar_count]
    range_high = range_bars["high"].max()
    range_low = range_bars["low"].min()
    if range_high <= range_low:
        return None

    for _, bar in day_bars.iloc[orb_bar_count:].iterrows():
        if bar["close"] > range_high:
            stop = range_low - ORB_STOP_BUFFER_USD
            entry = bar["close"]
            risk = entry - stop
            return Signal("long", entry, stop, entry + risk * ORB_RR, bar["time_local"])
        if bar["close"] < range_low:
            stop = range_high + ORB_STOP_BUFFER_USD
            entry = bar["close"]
            risk = stop - entry
            return Signal("short", entry, stop, entry - risk * ORB_RR, bar["time_local"])

    return None  # диапазон ни разу не был пробит за окно - сигнала нет
