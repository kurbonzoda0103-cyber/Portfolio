"""
Стратегии для бэктеста. Каждая стратегия получает свечи одного торгового дня,
уже обрезанные по торговому окну (config.TRADING_WINDOW_START-TRADING_WINDOW_END),
и возвращает Signal (сигнал на вход) или None, если сигнала не было.

Параметры стратегий ниже - это ПЕРВОЕ ПРИБЛИЖЕНИЕ для проверки на истории, а не
финально настроенные числа. Не подгоняем их под красивый результат бэктеста -
если стратегия покажет себя плохо, так и скажем, а не будем крутить параметры,
пока не получится нужная кривая доходности (это оверфиттинг).
"""

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config

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


def build_trend_lookup(m15_df: pd.DataFrame, h1_df: pd.DataFrame) -> dict:
    """Для каждого торгового дня определяет тренд H1 на момент начала окна,
    используя только уже закрытые H1-бары (см. compute_h1_trend_series).
    Общий помощник для всех стратегий с фильтром по тренду."""

    h1_trend = compute_h1_trend_series(h1_df)

    dates = sorted(m15_df["time_local"].dt.date.unique())
    windows = pd.DataFrame({
        "date": dates,
        "window_start": [pd.Timestamp(f"{d} {config.TRADING_WINDOW_START}") for d in dates],
    }).sort_values("window_start")

    merged = pd.merge_asof(
        windows,
        h1_trend.sort_values("confirmed_time"),
        left_on="window_start",
        right_on="confirmed_time",
        direction="backward",
    )

    trend_by_date = {}
    for _, row in merged.iterrows():
        if pd.isna(row["ema"]) or row["close"] == row["ema"]:
            trend_by_date[row["date"]] = None
        elif row["close"] > row["ema"]:
            trend_by_date[row["date"]] = "long"
        else:
            trend_by_date[row["date"]] = "short"

    return trend_by_date


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


# --- VWAP Cross ---
# Идея: VWAP (средняя цена дня, взвешенная по объёму tick_volume) - ориентир
# "справедливой" цены сессии. Пока цена ниже VWAP - на рынке перевес продавцов,
# выше - покупателей. Даём VWAP_WARMUP_MINUTES "разогреться" (в начале окна он
# неустойчив из-за малого числа баров), потом входим по первому пересечению цены
# и VWAP в сторону пересечения (моментум-продолжение, а не разворот).
VWAP_WARMUP_MINUTES = 30
VWAP_RR = 1.5


def _session_vwap(day_bars: pd.DataFrame) -> pd.Series:
    typical_price = (day_bars["high"] + day_bars["low"] + day_bars["close"]) / 3
    cum_pv = (typical_price * day_bars["tick_volume"]).cumsum()
    cum_volume = day_bars["tick_volume"].cumsum()
    return cum_pv / cum_volume


def vwap_cross(day_bars: pd.DataFrame) -> Signal | None:
    """day_bars - M15 свечи одного дня внутри торгового окна, отсортированы по времени."""

    bar_minutes = 15  # ожидаем M15
    warmup_bar_count = max(1, VWAP_WARMUP_MINUTES // bar_minutes)

    if len(day_bars) <= warmup_bar_count + 1:
        return None

    day_bars = day_bars.reset_index(drop=True)
    vwap = _session_vwap(day_bars)

    prev_side = None  # "above" или "below" - где была цена относительно VWAP на предыдущем баре

    for i in range(warmup_bar_count, len(day_bars)):
        bar = day_bars.iloc[i]
        side = "above" if bar["close"] > vwap.iloc[i] else "below"

        if prev_side is not None and side != prev_side:
            entry = bar["close"]
            recent = day_bars.iloc[max(0, i - 2): i + 1]  # последние пару баров - ориентир для стопа

            if side == "above":
                stop = recent["low"].min()
                if stop >= entry:
                    return None
                risk = entry - stop
                return Signal("long", entry, stop, entry + risk * VWAP_RR, bar["time_local"])
            else:
                stop = recent["high"].max()
                if stop <= entry:
                    return None
                risk = stop - entry
                return Signal("short", entry, stop, entry - risk * VWAP_RR, bar["time_local"])

        prev_side = side

    return None  # пересечения после разогрева не было


# --- Momentum Breakout + фильтр объёма ---
# Идея: тот же пробой диапазона, что и в ORB, но входим только если пробойный
# бар показал всплеск объёма (tick_volume) относительно объёма во время
# формирования диапазона - отсекаем "тихие" ложные пробои без реального интереса
# участников рынка (231 из 1207 сделок ORB без фильтра ушли в стоп - гипотеза:
# часть из них были как раз пробоями без объёма).
VOLUME_ORB_MINUTES = 30
VOLUME_ORB_STOP_BUFFER_USD = 0.0
VOLUME_ORB_RR = 1.5
VOLUME_MULTIPLIER = 1.5  # объём пробойного бара должен быть в VOLUME_MULTIPLIER раз выше среднего в диапазоне


def volume_confirmed_breakout(day_bars: pd.DataFrame) -> Signal | None:
    """day_bars - M15 свечи одного дня внутри торгового окна, отсортированы по времени."""

    bar_minutes = 15  # ожидаем M15
    range_bar_count = max(1, VOLUME_ORB_MINUTES // bar_minutes)

    if len(day_bars) <= range_bar_count:
        return None

    range_bars = day_bars.iloc[:range_bar_count]
    range_high = range_bars["high"].max()
    range_low = range_bars["low"].min()
    if range_high <= range_low:
        return None

    avg_range_volume = range_bars["tick_volume"].mean()
    if avg_range_volume <= 0:
        return None
    volume_threshold = avg_range_volume * VOLUME_MULTIPLIER

    for _, bar in day_bars.iloc[range_bar_count:].iterrows():
        if bar["tick_volume"] < volume_threshold:
            continue  # пробой без объёма - ждём следующий бар, этот не в счёт

        if bar["close"] > range_high:
            stop = range_low - VOLUME_ORB_STOP_BUFFER_USD
            entry = bar["close"]
            risk = entry - stop
            return Signal("long", entry, stop, entry + risk * VOLUME_ORB_RR, bar["time_local"])
        if bar["close"] < range_low:
            stop = range_high + VOLUME_ORB_STOP_BUFFER_USD
            entry = bar["close"]
            risk = stop - entry
            return Signal("short", entry, stop, entry - risk * VOLUME_ORB_RR, bar["time_local"])

    return None  # пробоя с достаточным объёмом не было


# --- Momentum Continuation (N баров подряд в одну сторону) ---
# Идея: не входить на первом же импульсе (как в ORB), а дождаться ПОДТВЕРЖДЕНИЯ -
# MOMENTUM_CONSECUTIVE_BARS баров подряд закрылись в одну сторону (устойчивый
# моментум), и только потом входить по направлению, а не на первом рывке.
MOMENTUM_CONSECUTIVE_BARS = 3
MOMENTUM_STOP_BUFFER_USD = 0.0
MOMENTUM_RR = 1.5


def momentum_continuation(
    day_bars: pd.DataFrame,
    rr: float = MOMENTUM_RR,
    consecutive_bars: int = MOMENTUM_CONSECUTIVE_BARS,
) -> Signal | None:
    """day_bars - M15 свечи одного дня внутри торгового окна, отсортированы по времени.

    rr - множитель тейк-профита к риску, consecutive_bars - сколько баров подряд
    нужно для подтверждения моментума. Оба параметризованы, чтобы сравнивать
    варианты (например, TP=1.5R против 1R, 3 бара против 5) без копирования
    функции."""

    day_bars = day_bars.reset_index(drop=True)
    n = consecutive_bars

    if len(day_bars) <= n:
        return None

    for i in range(n, len(day_bars)):
        window = day_bars.iloc[i - n:i]
        bullish = (window["close"] > window["open"]).all()
        bearish = (window["close"] < window["open"]).all()

        if not bullish and not bearish:
            continue

        entry_bar = day_bars.iloc[i - 1]
        entry = entry_bar["close"]

        if bullish:
            stop = window["low"].min() - MOMENTUM_STOP_BUFFER_USD
            if stop >= entry:
                continue
            risk = entry - stop
            return Signal("long", entry, stop, entry + risk * rr, entry_bar["time_local"])
        else:
            stop = window["high"].max() + MOMENTUM_STOP_BUFFER_USD
            if stop <= entry:
                continue
            risk = stop - entry
            return Signal("short", entry, stop, entry - risk * rr, entry_bar["time_local"])

    return None  # подтверждённого моментума за окно не случилось


# --- Momentum Continuation + фильтр тренда H1 ---
# Из всех протестированных идей momentum_continuation показал лучший сырой edge
# на сделку ($0.235 против $0.09 у второго места, VWAP) - но всё ещё в минусе
# после costов. Пробуем усилить его тем же фильтром тренда, что помог ORB:
# подтверждённый моментум принимаем только по направлению тренда H1.
def trend_filtered_momentum(day_bars: pd.DataFrame, h1_trend: str | None) -> Signal | None:
    """Как momentum_continuation, но сигнал принимается только если его
    направление совпадает с h1_trend ("long"/"short")."""

    if h1_trend is None:
        return None

    signal = momentum_continuation(day_bars)
    if signal is None or signal.direction != h1_trend:
        return None
    return signal


# --- Momentum Continuation + confluence с VWAP ---
# Фильтр по тренду H1 испортил momentum_continuation (edge упал с $0.235 до
# $0.161/сделку). Но и momentum_continuation, и vwap_cross по ОТДЕЛЬНОСТИ
# показали положительный сырой сигнал - в отличие от H1 EMA20 (слишком
# медленный ориентир для 4-часового окна), VWAP пересчитывается внутри самой
# сессии и может согласовываться с моментумом лучше. Пробуем конфлюэнс: сигнал
# momentum_continuation принимаем только если цена в момент входа на той же
# стороне VWAP, что и направление сигнала - два независимых индикатора должны
# совпасть, а не просто добавляем ещё один произвольный фильтр с нуля.
def momentum_vwap_confluence(day_bars: pd.DataFrame) -> Signal | None:
    """day_bars - M15 свечи одного дня внутри торгового окна, отсортированы по времени."""

    signal = momentum_continuation(day_bars)
    if signal is None:
        return None

    day_bars = day_bars.reset_index(drop=True)
    vwap = _session_vwap(day_bars)

    entry_idx = day_bars.index[day_bars["time_local"] == signal.entry_time]
    if len(entry_idx) == 0:
        return None
    idx = entry_idx[0]

    price_side = "above" if day_bars.loc[idx, "close"] > vwap.loc[idx] else "below"
    expected_side = "above" if signal.direction == "long" else "below"

    if price_side != expected_side:
        return None
    return signal
