"""
Стратегия для бэктеста: EMA trend-following на BTCUSDT.

Идея простая и понятная (первая гипотеза для проверки на истории, а не
финально настроенные параметры - не подгоняем их под красивый результат):
быстрая EMA пересекает медленную - открываем позицию по направлению
пересечения, держим, пока EMA не пересекутся обратно (разворот тренда) или
не сработает стоп-лосс (обязателен по правилам проекта - см. risk_gate.py).

Крипта торгуется 24/7 - в отличие от MT5/золота здесь НЕТ торгового окна и
принудительного закрытия к концу дня: позиция живёт, пока жив тренд.
"""

from dataclasses import dataclass

import pandas as pd

EMA_FAST = 9    # ~2.25 часа на M15
EMA_SLOW = 21   # ~5.25 часа на M15
ATR_PERIOD = 14
ATR_STOP_MULT = 2.0  # стоп на расстоянии ATR_STOP_MULT * ATR от цены входа


@dataclass
class Signal:
    direction: str  # "long" или "short"
    entry_price: float
    stop_price: float


def add_ema_signals(
    df: pd.DataFrame, fast: int = EMA_FAST, slow: int = EMA_SLOW, atr_period: int = ATR_PERIOD
) -> pd.DataFrame:
    """Векторизованно добавляет колонки ema_fast, ema_slow, atr, cross
    (1 = пересечение вверх, -1 = вниз, 0 = нет) - считается один раз на весь
    датасет, а не пересчитывается по кусочку истории в каждой итерации цикла
    бэктеста (так быстрее и проще держать логику в одном месте)."""

    df = df.copy()
    df["ema_fast"] = df["close"].ewm(span=fast, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=slow, adjust=False).mean()

    prev_close = df["close"].shift()
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr"] = true_range.rolling(atr_period).mean()

    prev_fast = df["ema_fast"].shift()
    prev_slow = df["ema_slow"].shift()
    cross_up = (prev_fast <= prev_slow) & (df["ema_fast"] > df["ema_slow"])
    cross_down = (prev_fast >= prev_slow) & (df["ema_fast"] < df["ema_slow"])

    df["cross"] = 0
    df.loc[cross_up, "cross"] = 1
    df.loc[cross_down, "cross"] = -1

    return df


def entry_signal(bar: pd.Series) -> Signal | None:
    """bar - строка датафрейма после add_ema_signals (нужны колонки cross, atr, close)."""

    if pd.isna(bar["atr"]) or bar["atr"] <= 0:
        return None  # ATR ещё не набрал данных (самое начало истории)

    if bar["cross"] == 1:
        entry = bar["close"]
        stop = entry - ATR_STOP_MULT * bar["atr"]
        return Signal("long", entry, stop)
    if bar["cross"] == -1:
        entry = bar["close"]
        stop = entry + ATR_STOP_MULT * bar["atr"]
        return Signal("short", entry, stop)
    return None


def should_exit_by_signal(bar: pd.Series, direction: str) -> bool:
    """True, если EMA пересеклись в обратную сторону - сигнал на выход по развороту тренда."""
    if direction == "long":
        return bar["cross"] == -1
    return bar["cross"] == 1
