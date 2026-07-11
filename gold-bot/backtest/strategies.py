"""
Стратегии для портфельного бэктеста на Bybit. Каждая функция подготовки
(add_*_signals) векторизованно добавляет нужные колонки на весь датафрейм
одной монеты, а entry/exit-функции читают их по одному бару за раз внутри
цикла движка (см. backtest/engine.py).

Параметры ниже - ПЕРВОЕ ПРИБЛИЖЕНИЕ для проверки на истории, а не финально
настроенные числа. Не подгоняем их под красивый результат бэктеста - если
стратегия покажет себя плохо, так и скажем, а не будем крутить параметры,
пока не получится нужная кривая доходности (это оверфиттинг).
"""

from dataclasses import dataclass

import pandas as pd


@dataclass
class Signal:
    direction: str  # "long" или "short"
    entry_price: float
    stop_price: float


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift()
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(period).mean()


# ---------------------------------------------------------------------------
# 1. EMA trend-following (базовая идея, уже проверена: сырой сигнал в минусе
#    на всех 8 монетах - см. README/CLAUDE.md, честный отрицательный результат)
# ---------------------------------------------------------------------------
EMA_FAST = 9
EMA_SLOW = 21
ATR_PERIOD = 14
ATR_STOP_MULT = 2.0


def add_ema_signals(df: pd.DataFrame, fast: int = EMA_FAST, slow: int = EMA_SLOW, atr_period: int = ATR_PERIOD) -> pd.DataFrame:
    df = df.copy()
    df["ema_fast"] = df["close"].ewm(span=fast, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=slow, adjust=False).mean()
    df["atr"] = _atr(df, atr_period)

    prev_fast = df["ema_fast"].shift()
    prev_slow = df["ema_slow"].shift()
    cross_up = (prev_fast <= prev_slow) & (df["ema_fast"] > df["ema_slow"])
    cross_down = (prev_fast >= prev_slow) & (df["ema_fast"] < df["ema_slow"])
    df["cross"] = 0
    df.loc[cross_up, "cross"] = 1
    df.loc[cross_down, "cross"] = -1

    return df


def ema_entry_signal(bar: pd.Series) -> Signal | None:
    if pd.isna(bar["atr"]) or bar["atr"] <= 0:
        return None
    if bar["cross"] == 1:
        entry = bar["close"]
        return Signal("long", entry, entry - ATR_STOP_MULT * bar["atr"])
    if bar["cross"] == -1:
        entry = bar["close"]
        return Signal("short", entry, entry + ATR_STOP_MULT * bar["atr"])
    return None


def ema_should_exit(bar: pd.Series, direction: str) -> bool:
    return bar["cross"] == -1 if direction == "long" else bar["cross"] == 1


# ---------------------------------------------------------------------------
# 2. EMA trend + фильтр по тренду H1 (та же идея, что помогла ORB в проекте
#    золота: медленный старший таймфрейм отсекает контр-трендовые сигналы).
#    H1 считаем ресемплингом из тех же M15-данных - отдельно скачивать не нужно.
# ---------------------------------------------------------------------------
H1_TREND_EMA_SPAN = 20


def add_h1_trend_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Добавляет колонку h1_trend ('long'/'short'/None) - тренд по ПОСЛЕДНЕМУ
    УЖЕ ЗАКРЫТОМУ H1-бару на момент каждого M15-бара (без заглядывания в
    будущее: H1-бар с меткой t закрывается только в t+1ч)."""

    df = df.copy()

    h1 = df.set_index("time_utc")[["high", "low", "close"]].resample("1h").agg(
        {"high": "max", "low": "min", "close": "last"}
    ).dropna()
    h1["ema"] = h1["close"].ewm(span=H1_TREND_EMA_SPAN, adjust=False).mean()
    h1 = h1.reset_index()
    h1["confirmed_time"] = h1["time_utc"] + pd.Timedelta(hours=1)

    merged = pd.merge_asof(
        df[["time_utc"]].sort_values("time_utc"),
        h1[["confirmed_time", "close", "ema"]].sort_values("confirmed_time"),
        left_on="time_utc",
        right_on="confirmed_time",
        direction="backward",
    )

    trend = pd.Series(None, index=merged.index, dtype=object)
    trend[merged["close"] > merged["ema"]] = "long"
    trend[merged["close"] < merged["ema"]] = "short"

    df["h1_trend"] = trend.values
    return df


def h1_trend_ema_entry_signal(bar: pd.Series) -> Signal | None:
    signal = ema_entry_signal(bar)
    if signal is None or bar.get("h1_trend") != signal.direction:
        return None
    return signal


# ---------------------------------------------------------------------------
# 3. Пробой канала Дончиана (аналог ORB из проекта золота, но без "окна" -
#    крипта 24/7, поэтому канал считаем скользящим, а не от начала фиксированного
#    периода). Вход по пробою N-бара high/low, стоп - по ATR.
# ---------------------------------------------------------------------------
DONCHIAN_PERIOD = 20
DONCHIAN_ATR_STOP_MULT = 2.0


def add_donchian_signals(df: pd.DataFrame, period: int = DONCHIAN_PERIOD, atr_period: int = ATR_PERIOD) -> pd.DataFrame:
    df = df.copy()
    # shift(1), чтобы канал на баре i считался ПРЕДЫДУЩИМИ барами, а не включал текущий -
    # иначе пробой всегда "случайно" совпадал бы с самим текущим экстремумом.
    df["donchian_high"] = df["high"].rolling(period).max().shift(1)
    df["donchian_low"] = df["low"].rolling(period).min().shift(1)
    df["atr"] = _atr(df, atr_period)
    return df


def donchian_entry_signal(bar: pd.Series) -> Signal | None:
    if pd.isna(bar["donchian_high"]) or pd.isna(bar["atr"]) or bar["atr"] <= 0:
        return None
    if bar["close"] > bar["donchian_high"]:
        entry = bar["close"]
        return Signal("long", entry, entry - DONCHIAN_ATR_STOP_MULT * bar["atr"])
    if bar["close"] < bar["donchian_low"]:
        entry = bar["close"]
        return Signal("short", entry, entry + DONCHIAN_ATR_STOP_MULT * bar["atr"])
    return None


def donchian_should_exit(bar: pd.Series, direction: str) -> bool:
    """Выход по возврату цены за середину канала - разворот пробоя, не только стоп."""
    mid = (bar["donchian_high"] + bar["donchian_low"]) / 2 if pd.notna(bar["donchian_high"]) else None
    if mid is None:
        return False
    return bar["close"] < mid if direction == "long" else bar["close"] > mid


# ---------------------------------------------------------------------------
# 4. Mean-reversion от полос Боллинджера - ставим на то, что цена, ушедшая
#    далеко от своей скользящей средней, вернётся обратно, а не продолжит.
# ---------------------------------------------------------------------------
BB_PERIOD = 20
BB_STD_MULT = 2.0
BB_ATR_STOP_MULT = 1.5


def add_bollinger_signals(df: pd.DataFrame, period: int = BB_PERIOD, std_mult: float = BB_STD_MULT, atr_period: int = ATR_PERIOD) -> pd.DataFrame:
    df = df.copy()
    mid = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    df["bb_mid"] = mid
    df["bb_upper"] = mid + std_mult * std
    df["bb_lower"] = mid - std_mult * std
    df["atr"] = _atr(df, atr_period)
    return df


def bollinger_entry_signal(bar: pd.Series) -> Signal | None:
    if pd.isna(bar["bb_lower"]) or pd.isna(bar["atr"]) or bar["atr"] <= 0:
        return None
    if bar["close"] < bar["bb_lower"]:
        entry = bar["close"]
        return Signal("long", entry, entry - BB_ATR_STOP_MULT * bar["atr"])
    if bar["close"] > bar["bb_upper"]:
        entry = bar["close"]
        return Signal("short", entry, entry + BB_ATR_STOP_MULT * bar["atr"])
    return None


def bollinger_should_exit(bar: pd.Series, direction: str) -> bool:
    """Выход при возврате к средней линии (bb_mid) - цель mean-reversion достигнута."""
    if pd.isna(bar["bb_mid"]):
        return False
    return bar["close"] >= bar["bb_mid"] if direction == "long" else bar["close"] <= bar["bb_mid"]


# ---------------------------------------------------------------------------
# 5. EMA trend + фильтр силы тренда по ADX - не входим на слабом/боковом рынке,
#    где EMA-пересечения обычно случайный шум, а не начало настоящего тренда.
# ---------------------------------------------------------------------------
ADX_PERIOD = 14
ADX_THRESHOLD = 25  # ADX выше этого значения - рынок считается трендовым


def add_adx_filtered_ema_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = add_ema_signals(df)

    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = pd.Series(0.0, index=df.index)
    minus_dm = pd.Series(0.0, index=df.index)
    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move

    atr = df["atr"].replace(0, pd.NA)
    plus_di = 100 * plus_dm.ewm(alpha=1 / ADX_PERIOD, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / ADX_PERIOD, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df["adx"] = dx.ewm(alpha=1 / ADX_PERIOD, adjust=False).mean()

    return df


def adx_filtered_ema_entry_signal(bar: pd.Series) -> Signal | None:
    if pd.isna(bar.get("adx")) or bar["adx"] < ADX_THRESHOLD:
        return None
    return ema_entry_signal(bar)
