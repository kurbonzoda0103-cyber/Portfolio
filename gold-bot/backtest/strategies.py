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


# --- ORB + фильтр по тренду H1 ---
# ORB без фильтра (см. run_backtest.py) дал сырой P&L в минусе ещё до спреда -
# то есть у самого пробоя нет edge, и часть сделок открывались против старшего
# тренда. Проверяем гипотезу: пробой диапазона принимаем ТОЛЬКО по направлению
# тренда H1 (простой фильтр: цена закрытия последнего закрытого H1-бара выше/ниже
# его EMA). Контр-трендовые сигналы просто пропускаем (не переворачиваем и не
# входим против тренда).
H1_TREND_EMA_SPAN = 20  # число H1-баров для EMA-фильтра тренда - первая гипотеза, не подобранная под результат


def compute_h1_trend_series(h1_df: pd.DataFrame) -> pd.DataFrame:
    """Готовит H1-данные для определения тренда: EMA и время, когда бар считается
    ПОДТВЕРЖДЁННЫМ (закрытым). H1-бар с меткой time_local покрывает интервал
    [time_local, time_local+1ч) - использовать его для решений можно только после
    time_local+1ч, иначе это заглядывание в будущее (lookahead bias)."""

    h1_df = h1_df.sort_values("time_local").copy()
    h1_df["ema"] = h1_df["close"].ewm(span=H1_TREND_EMA_SPAN, adjust=False).mean()
    h1_df["confirmed_time"] = h1_df["time_local"] + pd.Timedelta(hours=1)
    return h1_df[["confirmed_time", "close", "ema"]]


def trend_filtered_orb(day_bars: pd.DataFrame, h1_trend: str | None) -> Signal | None:
    """Как opening_range_breakout, но сигнал принимается только если его
    направление совпадает с h1_trend ("long"/"short"). h1_trend=None - тренд
    не определён (например, начало истории, EMA ещё не набрала данных) -
    сделок в этот день не берём."""

    if h1_trend is None:
        return None

    signal = opening_range_breakout(day_bars)
    if signal is None or signal.direction != h1_trend:
        return None
    return signal


# --- Range Fade (mean-reversion от ложного пробоя) ---
# Идея: первый импульс в начале окна нередко оказывается ложным выносом - сессии
# Лондон+Нью-Йорк ещё не набрали объём, ранние трейдеры входят по пробою и потом
# разворачиваются. Ждём пробоя диапазона первых RANGE_FADE_MINUTES минут, и если
# цена возвращается обратно ВНУТРЬ диапазона - входим ПРОТИВ направления пробоя,
# на возврат к противоположной границе диапазона.
RANGE_FADE_MINUTES = 30
RANGE_FADE_STOP_BUFFER_USD = 0.0


def range_fade(day_bars: pd.DataFrame) -> Signal | None:
    """day_bars - M15 свечи одного дня внутри торгового окна, отсортированы по времени."""

    bar_minutes = 15  # ожидаем M15
    range_bar_count = max(1, RANGE_FADE_MINUTES // bar_minutes)

    if len(day_bars) <= range_bar_count:
        return None

    range_bars = day_bars.iloc[:range_bar_count]
    range_high = range_bars["high"].max()
    range_low = range_bars["low"].min()
    if range_high <= range_low:
        return None

    broke_direction = None  # None, "up" или "down"
    extreme = None  # самая дальняя точка выноса за пределы диапазона (нужна для стопа)

    for _, bar in day_bars.iloc[range_bar_count:].iterrows():
        if broke_direction is None:
            if bar["high"] > range_high:
                broke_direction, extreme = "up", bar["high"]
            elif bar["low"] < range_low:
                broke_direction, extreme = "down", bar["low"]
            continue  # ждём пробоя, прежде чем искать возврат

        if broke_direction == "up":
            extreme = max(extreme, bar["high"])
            if bar["close"] < range_high:
                entry = bar["close"]
                stop = extreme + RANGE_FADE_STOP_BUFFER_USD
                if stop <= entry:
                    return None
                return Signal("short", entry, stop, range_low, bar["time_local"])
        else:
            extreme = min(extreme, bar["low"])
            if bar["close"] > range_low:
                entry = bar["close"]
                stop = extreme - RANGE_FADE_STOP_BUFFER_USD
                if stop >= entry:
                    return None
                return Signal("long", entry, stop, range_high, bar["time_local"])

    return None  # пробоя не было, либо цена так и не вернулась в диапазон
