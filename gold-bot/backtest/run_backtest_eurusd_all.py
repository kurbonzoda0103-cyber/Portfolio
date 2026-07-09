"""
Прогон ВСЕХ протестированных на золоте стратегий (кроме тех, что требуют
фильтр по тренду H1 - для них нужна отдельно скачанная EURUSD_H1.parquet) на
EURUSD - чтобы понять, есть ли среди них что-то, что подходит именно этому
инструменту лучше, чем Momentum Continuation, а не переносить вывод по одной
стратегии на все остальные автоматически.

ВАЖНО: EURUSD_SPREAD_POINTS ниже - ПРИБЛИЖЕНИЕ (типичный спред форекс-мажора
на стандартном счёте), не измеренный факт для этого XM-счёта. Замерьте:
    python bot\\check_connection.py EURUSD

Перед запуском нужна история EURUSD:
    python bot\\fetch_history.py EURUSD M15

Не требует MT5 для самого бэктеста - работает с data/EURUSD_M15.parquet.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from backtest.engine import run_backtest, Instrument
from backtest import strategies

SYMBOL = "EURUSD"

# Евро появился только 01.01.1999 - всё раньше в истории брокера синтетика/
# реконструкция для графиков, а не реальные торги.
MIN_DATE = "1999-01-01"

# Приближение, НЕ измеренный факт - см. предупреждение в шапке файла.
EURUSD_POINT = 0.00001
EURUSD_CONTRACT_SIZE = 100_000
EURUSD_SPREAD_POINTS = 15

# Стратегии без фильтра по H1-тренду (тому нужна отдельная EURUSD_H1.parquet).
STRATEGIES = {
    "ORB (без фильтра)": lambda day_bars, date: strategies.opening_range_breakout(day_bars),
    "Range Fade": lambda day_bars, date: strategies.range_fade(day_bars),
    "VWAP Cross": lambda day_bars, date: strategies.vwap_cross(day_bars),
    "Volume ORB": lambda day_bars, date: strategies.volume_confirmed_breakout(day_bars),
    "Momentum Continuation (TP=1.5R)": lambda day_bars, date: strategies.momentum_continuation(day_bars),
    "Momentum (TP=1R)": lambda day_bars, date: strategies.momentum_continuation(day_bars, rr=1.0),
    "Momentum (5 баров)": lambda day_bars, date: strategies.momentum_continuation(day_bars, consecutive_bars=5),
    "Momentum + confluence VWAP": lambda day_bars, date: strategies.momentum_vwap_confluence(day_bars),
}


def load_data() -> pd.DataFrame:
    path = Path(config.DATA_DIR) / f"{SYMBOL}_M15.parquet"
    if not path.exists():
        print(f"Не найден файл {path}.")
        print(f"Сначала запустите: python bot\\fetch_history.py {SYMBOL} M15")
        sys.exit(1)

    df = pd.read_parquet(path)
    before = len(df)
    df = df[df["time_local"] >= MIN_DATE].reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        print(f"Отброшено {dropped} свечей до {MIN_DATE} (синтетическая до-euro история брокера).")
    return df


def summarize(trades, equity_df, starting_equity: float) -> dict:
    if not trades:
        return {
            "сделок": 0, "gross_$": 0.0, "cost_$": 0.0,
            "gross/сделку_$": 0.0, "costы_покрыты_%": 0.0, "доходность_%": 0.0,
        }

    gross = sum(t.gross_pnl_usd for t in trades)
    cost = sum(t.cost_usd for t in trades)
    final_equity = equity_df["equity"].iloc[-1]

    return {
        "сделок": len(trades),
        "gross_$": round(gross, 2),
        "cost_$": round(cost, 2),
        "gross/сделку_$": round(gross / len(trades), 4),
        "costы_покрыты_%": round(gross / cost * 100, 1) if cost else 0.0,
        "доходность_%": round((final_equity / starting_equity - 1) * 100, 1),
    }


def main():
    df = load_data()

    eurusd = Instrument(
        point=EURUSD_POINT,
        contract_size=EURUSD_CONTRACT_SIZE,
        spread_points=EURUSD_SPREAD_POINTS,
        commission_per_lot_usd=0.0,
    )

    print("=" * 70)
    print(f"Сравнение стратегий на EURUSD (спред {EURUSD_SPREAD_POINTS} пунктов - ПРИБЛИЖЕНИЕ, не измерено)")
    print("=" * 70)

    rows = {}
    for name, signal_fn in STRATEGIES.items():
        trades, equity_df = run_backtest(df, config.STARTING_BALANCE_USD, signal_fn, instrument=eurusd)
        rows[name] = summarize(trades, equity_df, config.STARTING_BALANCE_USD)
        print(f"  {name}: готово ({rows[name]['сделок']} сделок)")

    table = pd.DataFrame(rows).T.sort_values("gross/сделку_$", ascending=False)

    print()
    print(table.to_string())

    out_path = Path(__file__).resolve().parent / "eurusd_all_strategies_comparison.csv"
    table.to_csv(out_path)
    print(f"\nТаблица сохранена: {out_path}")

    print()
    print("НАПОМИНАНИЕ: спред EURUSD - неизмеренное приближение. Замерьте реальный:")
    print("  python bot\\check_connection.py EURUSD")
    print("Исторические новости (NFP/ФРС/CPI) не исключены из этого прогона.")


if __name__ == "__main__":
    main()
