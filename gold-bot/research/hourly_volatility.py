"""
Этап 2: анализ волатильности и объёма золота по часам суток (в твоём времени, UTC+5).

Проверяем гипотезу: активнее ли золото в окно пересечения Лондон+Нью-Йорк
(TRADING_WINDOW_START-TRADING_WINDOW_END из config.py, по умолчанию 17:00-21:00),
чем в середине дня. Решают данные, а не наши ожидания - если гипотеза не
подтвердится, так и скажем и подберём окно по факту.

Что делает скрипт:
1. Читает data/{SYMBOL}_M15.parquet (нужен этап 1 - bot/fetch_history.py).
2. Для каждого часа суток (0-23, локальное время UTC+5) считает:
     - средний РЕАЛЬНЫЙ размах часа (max(high) - min(low) внутри часа, а не
       среднее по 15-минуткам - так честнее, потому что не теряем движение,
       если цена внутри часа сходила туда-обратно несколькими свечками);
     - средний объём (tick_volume - число тиков, у форекс-брокеров это
       единственный доступный показатель активности, реальный объём в лотах
       брокеры обычно не дают).
3. Печатает таблицу по часам и сравнивает три окна:
     - предполагаемое торговое окно (config.py: 17:00-21:00 по умолчанию)
     - "середина дня" (условно 11:00-15:00 - гипотеза Али)
     - весь день целиком (для контекста)
4. Строит график (research/plots/hourly_volatility.png) и сохраняет таблицу
   в research/hourly_stats.csv для дальнейшего использования на этапе 3.

Не требует MT5 - работает с уже скачанными данными, можно запускать где угодно,
где стоит Python и есть файл data/{SYMBOL}_M15.parquet.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import matplotlib.pyplot as plt

import config

# "Середина дня" - условное окно для сравнения с гипотезой Али про 17:00-21:00.
# Это НЕ жёсткая настройка проекта (в отличие от TRADING_WINDOW_* в config.py),
# а просто ориентир для этого конкретного сравнения.
MIDDAY_START_HOUR = 11
MIDDAY_END_HOUR = 15  # не включая - т.е. часы 11,12,13,14


def load_data() -> pd.DataFrame:
    path = Path(config.DATA_DIR) / f"{config.SYMBOL}_M15.parquet"
    if not path.exists():
        print(f"Не найден файл {path}.")
        print("Сначала запустите bot/fetch_history.py (Этап 1), чтобы скачать историю.")
        sys.exit(1)

    df = pd.read_parquet(path)
    df["date"] = df["time_local"].dt.date
    df["hour"] = df["time_local"].dt.hour
    return df


def compute_hourly_stats(df: pd.DataFrame):
    # Группируем по (дата, час) - это один "час торговли" в конкретный день.
    # high/low берём экстремумы внутри часа, а не среднее по 15-минуткам -
    # так не теряем движение, если цена внутри часа сходила туда-обратно.
    per_hour_per_day = df.groupby(["date", "hour"]).agg(
        high=("high", "max"),
        low=("low", "min"),
        volume=("tick_volume", "sum"),
    )
    per_hour_per_day["range"] = per_hour_per_day["high"] - per_hour_per_day["low"]
    per_hour_per_day = per_hour_per_day.reset_index()
    per_hour_per_day["weekday"] = pd.to_datetime(per_hour_per_day["date"]).dt.weekday  # 0=Пн ... 6=Вс

    # Усредняем по всем дням, отдельно для каждого часа суток (0-23).
    # avg vs median - если среднее сильно больше медианы, значит его тянут вверх
    # несколько дней-выбросов, а не стабильно высокая волатильность каждый день.
    stats = per_hour_per_day.groupby("hour").agg(
        avg_range_usd=("range", "mean"),
        median_range_usd=("range", "median"),
        max_range_usd=("range", "max"),
        avg_volume=("volume", "mean"),
        days_count=("range", "count"),
    )
    stats["avg_range_points"] = stats["avg_range_usd"] / 0.01  # у золота point обычно 0.01
    return stats.sort_index(), per_hour_per_day


def window_average(stats: pd.DataFrame, start_hour: int, end_hour: int, column: str = "avg_range_usd") -> float:
    """Среднее значение колонки внутри часового окна [start_hour, end_hour)."""
    hours = [h % 24 for h in range(start_hour, end_hour)]
    return stats.loc[stats.index.intersection(hours), column].mean()


WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

# Если среднее в часе больше медианы в OUTLIER_RATIO раз - подозреваем, что среднее
# тянут вверх редкие дни-выбросы (недельный гэп открытия, технический артефакт
# смены торгового дня у брокера), а не стабильно высокая волатильность каждый день.
OUTLIER_RATIO = 2.0


def print_weekday_breakdown(per_hour_per_day: pd.DataFrame, hour: int):
    subset = per_hour_per_day[per_hour_per_day["hour"] == hour]
    by_weekday = subset.groupby("weekday")["range"].agg(["mean", "median", "max", "count"])
    for wd, row in by_weekday.iterrows():
        name = WEEKDAYS_RU[wd] if wd < len(WEEKDAYS_RU) else str(wd)
        print(
            f"    {name}: среднее {row['mean']:.2f}$, медиана {row['median']:.2f}$, "
            f"максимум {row['max']:.2f}$, дней {int(row['count'])}"
        )


def main():
    print("=" * 70)
    print(f"Волатильность {config.SYMBOL} по часам суток (ваше время UTC+{config.MY_TIMEZONE_OFFSET_HOURS})")
    print("=" * 70)

    df = load_data()
    stats, per_hour_per_day = compute_hourly_stats(df)

    print(f"\nВсего дней в выборке: {stats['days_count'].max()} (по самому полному часу)")
    print(f"Период данных: {df['time_local'].min()} -> {df['time_local'].max()}\n")

    print(f"{'Час':>4} | {'Ср. $':>8} | {'Медиана $':>9} | {'Макс $':>8} | {'Пункты':>8} | {'Ср. объём':>10} | Дней")
    print("-" * 70)
    for hour, row in stats.iterrows():
        print(
            f"{hour:>4} | {row['avg_range_usd']:>8.2f} | {row['median_range_usd']:>9.2f} | "
            f"{row['max_range_usd']:>8.2f} | {row['avg_range_points']:>8.1f} | "
            f"{row['avg_volume']:>10.0f} | {int(row['days_count'])}"
        )

    # Проверяем, нет ли часов, где среднее раздуто редкими выбросами (см. OUTLIER_RATIO).
    suspicious = stats[stats["avg_range_usd"] > OUTLIER_RATIO * stats["median_range_usd"]]
    if not suspicious.empty:
        print("\n" + "!" * 70)
        print("ВНИМАНИЕ: среднее заметно выше медианы в этих часах - похоже на выбросы")
        print("(недельный гэп открытия рынка в воскресенье или технический артефакт смены")
        print("торгового дня у брокера), а не на стабильную волатильность каждый день:")
        for hour, row in suspicious.iterrows():
            print(f"\n  {hour}:00 - среднее {row['avg_range_usd']:.2f}$, медиана {row['median_range_usd']:.2f}$, максимум {row['max_range_usd']:.2f}$")
            print_weekday_breakdown(per_hour_per_day, hour)
        print("\n" + "!" * 70)
        print("Эти часы исключены из сравнения окон и топ-листа ниже, чтобы выбросы")
        print("не искажали общий вывод. Числа по ним остаются в hourly_stats.csv.")

    clean_stats = stats.drop(index=suspicious.index)

    window_start_hour = int(config.TRADING_WINDOW_START.split(":")[0])
    window_end_hour = int(config.TRADING_WINDOW_END.split(":")[0])

    trading_window_avg = window_average(clean_stats, window_start_hour, window_end_hour)
    midday_avg = window_average(clean_stats, MIDDAY_START_HOUR, MIDDAY_END_HOUR)
    full_day_avg = clean_stats["avg_range_usd"].mean()

    print("\n" + "-" * 70)
    print("Сравнение окон без выбросов (средний часовой размах в $):")
    print(f"  Торговое окно {config.TRADING_WINDOW_START}-{config.TRADING_WINDOW_END} (Лондон+NY): {trading_window_avg:.2f} $/час")
    print(f"  Середина дня {MIDDAY_START_HOUR:02d}:00-{MIDDAY_END_HOUR:02d}:00:                {midday_avg:.2f} $/час")
    print(f"  Весь день (среднее по всем часам, без выбросов):  {full_day_avg:.2f} $/час")

    top_hours = clean_stats["avg_range_usd"].sort_values(ascending=False).head(5)
    print(f"\nТоп-5 часов по волатильности (без выбросов): {', '.join(f'{h}:00' for h in top_hours.index)}")

    if trading_window_avg > midday_avg:
        diff_pct = (trading_window_avg / midday_avg - 1) * 100
        print(f"\nВывод: окно {config.TRADING_WINDOW_START}-{config.TRADING_WINDOW_END} волатильнее середины дня на {diff_pct:.0f}%.")
    else:
        diff_pct = (midday_avg / trading_window_avg - 1) * 100
        print(f"\nВывод: гипотеза НЕ подтвердилась - середина дня волатильнее окна {config.TRADING_WINDOW_START}-{config.TRADING_WINDOW_END} на {diff_pct:.0f}%.")

    # Сохраняем таблицу и график для этапа 3
    out_dir = Path(__file__).resolve().parent
    stats.to_csv(out_dir / "hourly_stats.csv")

    plots_dir = out_dir / "plots"
    plots_dir.mkdir(exist_ok=True)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)

    # Часы-выбросы красим отдельным цветом на графике, чтобы визуально не путать
    # их со стабильно высокой волатильностью торгового окна.
    bar_colors = ["tab:red" if h in suspicious.index else "tab:orange" for h in stats.index]
    ax1.bar(stats.index, stats["avg_range_usd"], color=bar_colors)
    ax1.set_ylabel("Средний размах, $")
    ax1.set_title(f"{config.SYMBOL}: волатильность и объём по часам суток (UTC+{config.MY_TIMEZONE_OFFSET_HOURS})")
    ax1.axvspan(window_start_hour - 0.5, window_end_hour - 0.5, color="green", alpha=0.15, label="Торговое окно")
    ax1.axvspan(MIDDAY_START_HOUR - 0.5, MIDDAY_END_HOUR - 0.5, color="blue", alpha=0.1, label="Середина дня")
    if not suspicious.empty:
        ax1.bar([], [], color="tab:red", label="Похоже на выброс (см. вывод в консоли)")
    ax1.legend()

    ax2.bar(stats.index, stats["avg_volume"], color="tab:blue")
    ax2.set_ylabel("Средний объём (тики)")
    ax2.set_xlabel("Час суток (UTC+5)")
    ax2.set_xticks(range(0, 24))
    ax2.axvspan(window_start_hour - 0.5, window_end_hour - 0.5, color="green", alpha=0.15)
    ax2.axvspan(MIDDAY_START_HOUR - 0.5, MIDDAY_END_HOUR - 0.5, color="blue", alpha=0.1)

    fig.tight_layout()
    out_path = plots_dir / "hourly_volatility.png"
    fig.savefig(out_path, dpi=120)
    print(f"\nГрафик сохранён: {out_path}")
    print(f"Таблица сохранена: {out_dir / 'hourly_stats.csv'}")


if __name__ == "__main__":
    main()
