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


def resample_to_h1(df: pd.DataFrame) -> pd.DataFrame:
    """Ресемплит M15-бары в H1 - для стратегий, которым нужен более крупный
    таймфрейм (меньше сделок относительно фиксированных costов комиссии),
    без отдельного скачивания данных с биржи."""

    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in df.columns:
        agg["volume"] = "sum"
    if "turnover" in df.columns:
        agg["turnover"] = "sum"

    h1 = df.set_index("time_utc").resample("1h").agg(agg).dropna(subset=["close"])
    return h1.reset_index()


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

    # resample() иногда меняет разрешение datetime64 (мс/мкс/нс) относительно
    # исходной колонки - merge_asof в новых версиях pandas требует ТОЧНО
    # одинаковый dtype у обоих ключей, поэтому приводим оба явно к [ns].
    left_keys = df[["time_utc"]].sort_values("time_utc").copy()
    left_keys["time_utc"] = left_keys["time_utc"].astype("datetime64[ns]")
    right_keys = h1[["confirmed_time", "close", "ema"]].sort_values("confirmed_time").copy()
    right_keys["confirmed_time"] = right_keys["confirmed_time"].astype("datetime64[ns]")

    merged = pd.merge_asof(
        left_keys,
        right_keys,
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
ADX_TREND_THRESHOLD = 25    # ADX выше этого значения - рынок считается трендовым (для EMA)
ADX_RANGING_THRESHOLD = 20  # ADX НИЖЕ этого значения - рынок считается боковым (для mean-reversion)


def _adx(df: pd.DataFrame, period: int = ADX_PERIOD) -> pd.Series:
    """df должен уже содержать колонку 'atr' (см. _atr выше)."""
    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = pd.Series(0.0, index=df.index)
    minus_dm = pd.Series(0.0, index=df.index)
    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move

    atr = df["atr"].replace(0, pd.NA)
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def add_adx_filtered_ema_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = add_ema_signals(df)
    df["adx"] = _adx(df)
    return df


def adx_filtered_ema_entry_signal(bar: pd.Series) -> Signal | None:
    if pd.isna(bar.get("adx")) or bar["adx"] < ADX_TREND_THRESHOLD:
        return None
    return ema_entry_signal(bar)


# ---------------------------------------------------------------------------
# 6. Mean-reversion (Боллинджер) + фильтр БОКОВОГО рынка по ADX - обратная
#    логика идее 5: mean-reversion обычно работает в боковике, а в сильном
#    тренде "дешёвая" цена может продолжить дешеветь дальше, а не откатить.
#    Не подгонка параметров Боллинджера (это мы уже пробовали, не помогло) -
#    отсекаем именно РЕЖИМ рынка, где сама идея разворота уместна.
# ---------------------------------------------------------------------------
def add_adx_filtered_bollinger_signals(
    df: pd.DataFrame, period: int = BB_PERIOD, std_mult: float = BB_STD_MULT
) -> pd.DataFrame:
    df = add_bollinger_signals(df, period=period, std_mult=std_mult)
    df["adx"] = _adx(df)
    return df


def adx_filtered_bollinger_entry_signal(bar: pd.Series) -> Signal | None:
    if pd.isna(bar.get("adx")) or bar["adx"] > ADX_RANGING_THRESHOLD:
        return None
    return bollinger_entry_signal(bar)


# ---------------------------------------------------------------------------
# 7. То же самое (Боллинджер + ADX ranging), плюс фильтр волатильности: не
#    входим, если полосы УЖЕ УЖЕ своей обычной ширины для этой же монеты за
#    последнее время. Идея: комиссия+funding - это фиксированный % от notional,
#    а ожидаемый ход цены при mean-reversion примерно пропорционален ширине
#    полосы - значит на аномально узких полосах costы съедают edge сильнее
#    всего. Порог - НЕ константа (не подгоняем число под конкретную монету),
#    а скользящая медиана ширины полосы самой этой монеты - самонормирующийся
#    фильтр, одинаково работающий и на BTC, и на дешёвых альтах.
# ---------------------------------------------------------------------------
BB_WIDTH_MEDIAN_WINDOW = 200  # ~2 дня на M15 - достаточно баров для устойчивой медианы, не так много, чтобы съесть всю историю на прогрев


def add_adx_filtered_bollinger_vol_signals(
    df: pd.DataFrame, period: int = BB_PERIOD, std_mult: float = BB_STD_MULT
) -> pd.DataFrame:
    df = add_adx_filtered_bollinger_signals(df, period=period, std_mult=std_mult)
    bb_width_pct = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
    df["bb_width_pct"] = bb_width_pct
    df["bb_width_median"] = bb_width_pct.rolling(BB_WIDTH_MEDIAN_WINDOW).median()
    return df


def adx_vol_filtered_bollinger_entry_signal(bar: pd.Series) -> Signal | None:
    if pd.isna(bar.get("bb_width_median")) or bar["bb_width_pct"] <= bar["bb_width_median"]:
        return None
    return adx_filtered_bollinger_entry_signal(bar)


# ---------------------------------------------------------------------------
# 8. Асимметричный выход: не ждать ПОЛНОГО возврата к средней линии (bb_mid),
#    а фиксировать прибыль раньше - на BB_PARTIAL_EXIT_FRACTION пути от входа
#    до средней. Гипотеза: часть сделок разворачивается обратно НЕ ДОЙДЯ до
#    полной средней и уходит в стоп, пока мы ждём цель, которая была рядом.
#    Более раннее закрытие даёт меньший gross с выигрышной сделки, но может
#    спасать часть тех, что иначе стали бы убыточными - проверяем баланс на
#    истории, а не предполагаем результат заранее.
# ---------------------------------------------------------------------------
BB_PARTIAL_EXIT_FRACTION = 0.7  # доля пути от нижней/верхней полосы до средней, после которой фиксируем выход


def bollinger_partial_should_exit(bar: pd.Series, direction: str) -> bool:
    if pd.isna(bar["bb_mid"]) or pd.isna(bar["bb_lower"]) or pd.isna(bar["bb_upper"]):
        return False
    if direction == "long":
        target = bar["bb_lower"] + BB_PARTIAL_EXIT_FRACTION * (bar["bb_mid"] - bar["bb_lower"])
        return bar["close"] >= target
    target = bar["bb_upper"] - BB_PARTIAL_EXIT_FRACTION * (bar["bb_upper"] - bar["bb_mid"])
    return bar["close"] <= target


# ---------------------------------------------------------------------------
# 9. Mean-reversion + ADX ranging на H1 (ресемплинг M15, доп. данные не нужны) -
#    сама по себе H1-mean-reversion без ADX-фильтра не помогла (см. вариант
#    "Mean-reversion H1"), но там не было фильтра БОКОВОГО рынка - проверяем,
#    работает ли комбинация, доказавшая себя на M15, на более крупном таймфрейме.
# ---------------------------------------------------------------------------
def add_h1_adx_filtered_bollinger_signals(
    df: pd.DataFrame, period: int = BB_PERIOD, std_mult: float = BB_STD_MULT
) -> pd.DataFrame:
    return add_adx_filtered_bollinger_signals(resample_to_h1(df), period=period, std_mult=std_mult)


# ---------------------------------------------------------------------------
# 10. RSI-дивергенция - принципиально другой источник сигнала: не сама цена
#     (как у Боллинджера/Дончиана/EMA), а РАСХОЖДЕНИЕ цены и осциллятора RSI.
#     Классическая дивергенция ищется по свинг-точкам (локальным экстремумам) -
#     здесь упрощение: сравниваем текущий бар с минимумом/максимумом ЦЕНЫ и
#     RSI за одно и то же скользящее окно, без явного поиска свингов. Это
#     приближение к полноценной дивергенции, а не она сама - как и упрощение
#     базисного риска в funding_carry.py, явно проговариваем допущение.
#     Пример: цена обновляет N-баровый минимум, а RSI - НЕТ (остаётся выше
#     своего минимума за то же окно) - значит падение теряет импульс, ставим
#     на разворот вверх. RSI-фильтр перепроданности/перекупленности (<40/>60)
#     отсекает дивергенции на нейтральном рынке, где сигнал обычно шумовой.
# ---------------------------------------------------------------------------
RSI_PERIOD = 14
RSI_DIVERGENCE_WINDOW = 14
RSI_OVERSOLD = 40
RSI_OVERBOUGHT = 60
RSI_ATR_STOP_MULT = 2.0


def _rsi(df: pd.DataFrame, period: int = RSI_PERIOD) -> pd.Series:
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean().replace(0, float("nan"))
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def add_rsi_divergence_signals(
    df: pd.DataFrame, window: int = RSI_DIVERGENCE_WINDOW, atr_period: int = ATR_PERIOD
) -> pd.DataFrame:
    df = df.copy()
    df["rsi"] = _rsi(df)
    df["atr"] = _atr(df, atr_period)

    roll_low = df["low"].rolling(window).min()
    roll_high = df["high"].rolling(window).max()
    roll_rsi_low = df["rsi"].rolling(window).min()
    roll_rsi_high = df["rsi"].rolling(window).max()

    bullish_div = (df["low"] <= roll_low) & (df["rsi"] > roll_rsi_low) & (df["rsi"] < RSI_OVERSOLD)
    bearish_div = (df["high"] >= roll_high) & (df["rsi"] < roll_rsi_high) & (df["rsi"] > RSI_OVERBOUGHT)

    df["rsi_divergence"] = 0
    df.loc[bullish_div, "rsi_divergence"] = 1
    df.loc[bearish_div, "rsi_divergence"] = -1
    return df


def rsi_divergence_entry_signal(bar: pd.Series) -> Signal | None:
    if pd.isna(bar.get("atr")) or bar["atr"] <= 0:
        return None
    if bar["rsi_divergence"] == 1:
        entry = bar["close"]
        return Signal("long", entry, entry - RSI_ATR_STOP_MULT * bar["atr"])
    if bar["rsi_divergence"] == -1:
        entry = bar["close"]
        return Signal("short", entry, entry + RSI_ATR_STOP_MULT * bar["atr"])
    return None


def rsi_divergence_should_exit(bar: pd.Series, direction: str) -> bool:
    """Выход, когда RSI возвращается через середину (50) - импульс, вызвавший дивергенцию, исчерпан."""
    if pd.isna(bar.get("rsi")):
        return False
    return bar["rsi"] >= 50 if direction == "long" else bar["rsi"] <= 50


# ---------------------------------------------------------------------------
# 11. Объёмный breakout - тот же пробой канала, что и у Дончиана (идея 3), но
#     с фильтром по объёму: входим только если пробой сопровождается
#     АНОМАЛЬНЫМ всплеском объёма (реальный интерес рынка), а не просто ценой,
#     случайно задевшей N-баровый экстремум. Именно это отличает её от
#     Дончиана, а не другой period/ATR-множитель.
# ---------------------------------------------------------------------------
VOLUME_SPIKE_WINDOW = 20
VOLUME_SPIKE_MULT = 2.0  # объём должен быть минимум в 2 раза выше своей скользящей средней


def add_volume_breakout_signals(
    df: pd.DataFrame,
    period: int = DONCHIAN_PERIOD,
    atr_period: int = ATR_PERIOD,
    vol_window: int = VOLUME_SPIKE_WINDOW,
) -> pd.DataFrame:
    df = add_donchian_signals(df, period=period, atr_period=atr_period)
    df["volume_avg"] = df["volume"].rolling(vol_window).mean()
    return df


def volume_breakout_entry_signal(bar: pd.Series) -> Signal | None:
    if pd.isna(bar.get("volume_avg")) or bar["volume_avg"] <= 0:
        return None
    if bar["volume"] < VOLUME_SPIKE_MULT * bar["volume_avg"]:
        return None
    return donchian_entry_signal(bar)
