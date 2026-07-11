"""
Этап 3: сравнение 5 разных стратегий на портфеле монет. EMA trend-following
сама по себе не сработала - сырой сигнал был в минусе на ВСЕХ монетах портфеля
(см. README/CLAUDE.md). Перебираем принципиально разные идеи вместо того,
чтобы крутить параметры одной и той же - это защита от переподгонки.

Стратегии:
1. EMA trend (база) - уже проверена и убыточна, оставлена для сравнения
2. EMA + фильтр тренда H1 (H1 считается ресемплингом из тех же M15-данных)
3. Пробой канала Дончиана (20 баров)
4. Mean-reversion от полос Боллинджера (20, 2 std)
5. EMA + фильтр силы тренда ADX (> 25)

Не требует API-ключей - работает с уже скачанными data/*.parquet:
    python bot\\top_symbols.py
    python bot\\fetch_history_bybit.py TOP10

Честно печатает результат по каждой стратегии, включая отрицательный -
подгонять параметры под красивую кривую доходности не будем.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
import risk_gate
from backtest.engine import run_portfolio_backtest
from backtest import strategies


def load_symbol_list() -> list[str]:
    path = Path(config.DATA_DIR) / "top_symbols.txt"
    if not path.exists():
        print(f"Не найден {path}.")
        print("Сначала запустите: python bot\\top_symbols.py")
        sys.exit(1)
    return [s.strip() for s in path.read_text().splitlines() if s.strip()]


def load_raw_data(symbols: list[str]) -> dict[str, pd.DataFrame]:
    tf_name = f"M{config.INTERVAL}" if config.INTERVAL.isdigit() else config.INTERVAL
    data_dir = Path(config.DATA_DIR)

    raw = {}
    for symbol in symbols:
        path = data_dir / f"{symbol}_{tf_name}.parquet"
        if not path.exists():
            print(f"  {symbol}: нет файла {path} - пропускаю (запустите bot\\fetch_history_bybit.py TOP10).")
            continue
        raw[symbol] = pd.read_parquet(path)

    if not raw:
        print("Ни одной монеты с данными не найдено. Сначала скачайте историю.")
        sys.exit(1)
    return raw


def align_to_common_window(symbol_dfs: dict[str, pd.DataFrame]):
    """Обрезает все монеты до ОБЩЕГО пересекающегося периода - иначе монеты с
    долгой историей торговались бы годами в одиночку, пока более новые
    листинги ещё не существовали (см. коммит с этим исправлением)."""

    common_start = max(df["time_utc"].min() for df in symbol_dfs.values())
    common_end = min(df["time_utc"].max() for df in symbol_dfs.values())

    aligned = {}
    for symbol, df in symbol_dfs.items():
        trimmed = df[(df["time_utc"] >= common_start) & (df["time_utc"] <= common_end)].reset_index(drop=True)
        if not trimmed.empty:
            aligned[symbol] = trimmed
    return aligned, common_start, common_end


STRATEGIES = {
    "EMA trend (база)": {
        "prepare": strategies.add_ema_signals,
        "entry": strategies.ema_entry_signal,
        "exit": strategies.ema_should_exit,
    },
    "EMA + фильтр H1": {
        "prepare": lambda df: strategies.add_h1_trend_filter(strategies.add_ema_signals(df)),
        "entry": strategies.h1_trend_ema_entry_signal,
        "exit": strategies.ema_should_exit,
    },
    "Пробой Дончиана": {
        "prepare": strategies.add_donchian_signals,
        "entry": strategies.donchian_entry_signal,
        "exit": strategies.donchian_should_exit,
    },
    "Mean-reversion (Боллинджер)": {
        "prepare": strategies.add_bollinger_signals,
        "entry": strategies.bollinger_entry_signal,
        "exit": strategies.bollinger_should_exit,
    },
    "Mean-reversion (модификация: полосы 30/2.5)": {
        # Модификация 1: реже, но качественнее вход - длиннее период (30 вместо
        # 20) и шире полосы (2.5 std вместо 2.0). Base-вариант выше показал
        # реальный положительный edge, но слишком частые сделки - costы съедали
        # его вдвое. Проверяем, вырастет ли edge на сделку при более строгом входе.
        "prepare": lambda df: strategies.add_bollinger_signals(df, period=30, std_mult=2.5),
        "entry": strategies.bollinger_entry_signal,
        "exit": strategies.bollinger_should_exit,
    },
    "EMA + фильтр ADX": {
        "prepare": strategies.add_adx_filtered_ema_signals,
        "entry": strategies.adx_filtered_ema_entry_signal,
        "exit": strategies.ema_should_exit,
    },
    "Mean-reversion H1 (Боллинджер)": {
        # Модификация 2: та же идея (Боллинджер 20/2.0), но на H1 вместо M15 -
        # реже сделки, зато каждая крупнее относительно фиксированных costов
        # комиссии/funding. H1 получаем ресемплингом M15, докачивать не нужно.
        "prepare": lambda df: strategies.add_bollinger_signals(strategies.resample_to_h1(df)),
        "entry": strategies.bollinger_entry_signal,
        "exit": strategies.bollinger_should_exit,
    },
    "Mean-reversion + ADX ranging (Боллинджер)": {
        # Модификация 3: mean-reversion обычно работает в боковике - отсекаем
        # сильный тренд (ADX > 20), а не подгоняем параметры полос (это уже
        # пробовали, не помогло) - фильтруем именно РЕЖИМ рынка. Подтверждено
        # train/test валидацией (validate_portfolio_train_test.py): edge
        # устойчив на обеих половинах времени (~60% costов покрыто и там, и там).
        "prepare": strategies.add_adx_filtered_bollinger_signals,
        "entry": strategies.adx_filtered_bollinger_entry_signal,
        "exit": strategies.bollinger_should_exit,
    },
    "Mean-reversion + ADX ranging (полосы 30/2.5)": {
        # Модификация 4: комбинация двух идей - широкие полосы/длинный период
        # (провалились САМИ ПО СЕБЕ без ADX-фильтра) + подтверждённый ADX-фильтр
        # бокового рынка. Взаимодействие может отличаться от изолированных тестов.
        "prepare": lambda df: strategies.add_adx_filtered_bollinger_signals(df, period=30, std_mult=2.5),
        "entry": strategies.adx_filtered_bollinger_entry_signal,
        "exit": strategies.bollinger_should_exit,
    },
    "Mean-reversion + ADX ranging + фильтр волатильности": {
        # Модификация 5: НЕ меняем параметры полос (20/2.0, подтверждённый
        # train/test вариант) - вместо этого режем costы через отказ от входов
        # на аномально узких полосах (маленький ожидаемый ход при том же % costе).
        "prepare": strategies.add_adx_filtered_bollinger_vol_signals,
        "entry": strategies.adx_vol_filtered_bollinger_entry_signal,
        "exit": strategies.bollinger_should_exit,
    },
}


def summarize(trades, equity_df, starting_equity: float) -> dict:
    if not trades:
        return {
            "сделок": 0, "gross_$": 0.0, "cost_$": 0.0,
            "gross/сделку_$": 0.0, "costы_покрыты_%": 0.0, "доходность_%": 0.0, "монет_в_плюсе": "0/0",
        }

    gross = sum(t.gross_pnl_usdt for t in trades)
    cost = sum(t.cost_usdt for t in trades)
    final_equity = equity_df["equity"].iloc[-1]

    by_symbol_pnl: dict[str, float] = {}
    for t in trades:
        by_symbol_pnl[t.symbol] = by_symbol_pnl.get(t.symbol, 0.0) + t.pnl_usdt
    profitable = sum(1 for v in by_symbol_pnl.values() if v > 0)

    return {
        "сделок": len(trades),
        "gross_$": round(gross, 2),
        "cost_$": round(cost, 2),
        "gross/сделку_$": round(gross / len(trades), 4),
        "costы_покрыты_%": round(gross / cost * 100, 1) if cost else 0.0,
        "доходность_%": round((final_equity / starting_equity - 1) * 100, 1),
        "монет_в_плюсе": f"{profitable}/{len(by_symbol_pnl)}",
    }


def print_symbol_breakdown(name: str, trades):
    print()
    print(f"Разбивка по монетам для лучшей стратегии ({name}), отсортировано по P&L:")
    by_symbol = pd.DataFrame(
        {"symbol": [t.symbol for t in trades], "pnl": [t.pnl_usdt for t in trades]}
    ).groupby("symbol")["pnl"].agg(["sum", "count"]).sort_values("sum", ascending=False)
    for symbol, row in by_symbol.iterrows():
        mark = "+" if row["sum"] > 0 else " "
        print(f"  {mark} {symbol:12s}  P&L ${row['sum']:+8.2f}   сделок: {int(row['count'])}")


def main():
    symbols = load_symbol_list()
    print(f"Монеты в портфеле ({len(symbols)}): {', '.join(symbols)}\n")

    raw = load_raw_data(symbols)

    common_start = common_end = None
    rows = {}
    trades_by_strategy = {}
    for name, spec in STRATEGIES.items():
        print(f"Прогоняю: {name}...")
        prepared = {symbol: spec["prepare"](df) for symbol, df in raw.items()}
        aligned, common_start, common_end = align_to_common_window(prepared)

        trades, equity_df = run_portfolio_backtest(
            aligned, risk_gate.STARTING_BALANCE_USDT, spec["entry"], spec["exit"]
        )
        rows[name] = summarize(trades, equity_df, risk_gate.STARTING_BALANCE_USDT)
        trades_by_strategy[name] = trades

    table = pd.DataFrame(rows).T.sort_values("gross/сделку_$", ascending=False)

    print()
    print("=" * 100)
    print(f"Сравнение стратегий, {len(raw)} монет, общий период: {common_start} -> {common_end} "
          f"(~{(common_end - common_start).days / 30:.1f} мес.)")
    print("=" * 100)
    print(table.to_string())

    best_name = table.index[0]
    if trades_by_strategy[best_name]:
        print_symbol_breakdown(best_name, trades_by_strategy[best_name])

    out_path = Path(__file__).resolve().parent / "strategy_comparison.csv"
    table.to_csv(out_path)
    print(f"\nТаблица сохранена: {out_path}")

    print()
    print("ВАЖНО: funding rate - ПРИБЛИЖЕНИЕ (risk_gate.ASSUMED_FUNDING_RATE_PER_8H), не измерено.")
    print("Комиссия 0.055% (taker) - официальная ставка Bybit. Исторические новости не исключены.")
    print()
    print("Читать таблицу по колонке 'gross/сделку_$' - это сырой edge ДО costов, показывает,")
    print("есть ли у идеи вообще смысл, а не только итоговую доходность (которая зависит от числа сделок).")


if __name__ == "__main__":
    main()
