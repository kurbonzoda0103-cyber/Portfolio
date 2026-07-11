"""
Этап 3: портфельный бэктест EMA trend-following на топ-10 монет Bybit по
объёму (не одна BTCUSDT), минимум 6 месяцев истории на каждую.

Не требует API-ключей и подключения к Bybit - работает с
data/{SYMBOL}_M{INTERVAL}.parquet для каждой монеты из data/top_symbols.txt,
скачанными заранее:
    python bot\\top_symbols.py
    python bot\\fetch_history_bybit.py TOP10

Общий баланс и общие дневные риск-лимиты на весь портфель - см. risk_gate.py.
Честно печатает результат, включая отрицательный - подгонять параметры под
красивую кривую доходности не будем.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
import risk_gate
from backtest.engine import run_portfolio_backtest
from backtest import strategies
from backtest.report import print_report, save_outputs


def load_symbol_list() -> list[str]:
    path = Path(config.DATA_DIR) / "top_symbols.txt"
    if not path.exists():
        print(f"Не найден {path}.")
        print("Сначала запустите: python bot\\top_symbols.py")
        sys.exit(1)
    return [s.strip() for s in path.read_text().splitlines() if s.strip()]


def load_symbol_data(symbols: list[str]) -> dict[str, pd.DataFrame]:
    tf_name = f"M{config.INTERVAL}" if config.INTERVAL.isdigit() else config.INTERVAL
    data_dir = Path(config.DATA_DIR)

    symbol_dfs = {}
    for symbol in symbols:
        path = data_dir / f"{symbol}_{tf_name}.parquet"
        if not path.exists():
            print(f"  {symbol}: нет файла {path} - пропускаю (запустите bot\\fetch_history_bybit.py TOP10).")
            continue
        symbol_dfs[symbol] = pd.read_parquet(path)

    if not symbol_dfs:
        print("Ни одной монеты с данными не найдено. Сначала скачайте историю.")
        sys.exit(1)

    return symbol_dfs


def align_to_common_window(symbol_dfs: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Обрезает все монеты до ОБЩЕГО пересекающегося периода (макс. из всех
    "начал" -> мин. из всех "концов"). Без этого монеты с долгой историей
    (BTC, ETH - годы) торговались бы годами В ОДИНОЧКУ, пока более новые
    листинги (например, недавно добавленные на Bybit) ещё не существовали -
    и если этот "одиночный" период оказался бы убыточным, общий капитал мог
    бы обвалиться до нуля ещё до того, как остальные монеты вообще получили
    бы шанс поторговать. Индикаторы (EMA/ATR) считаются ДО обрезки на полной
    истории каждой монеты, чтобы в начале общего окна они были уже "разогреты",
    а не начинали заново с NaN."""

    common_start = max(df["time_utc"].min() for df in symbol_dfs.values())
    common_end = min(df["time_utc"].max() for df in symbol_dfs.values())

    if common_start >= common_end:
        print("ОШИБКА: у монет нет общего периода истории - слишком разные даты листинга.")
        sys.exit(1)

    print(f"Общий период для всех монет: {common_start} -> {common_end} "
          f"(~{(common_end - common_start).days / 30:.1f} мес.)")

    aligned = {}
    for symbol, df in symbol_dfs.items():
        trimmed = df[(df["time_utc"] >= common_start) & (df["time_utc"] <= common_end)].reset_index(drop=True)
        if trimmed.empty:
            print(f"  {symbol}: после обрезки на общий период данных не осталось - исключаю из бэктеста.")
            continue
        aligned[symbol] = trimmed

    return aligned


def main():
    symbols = load_symbol_list()
    print(f"Монеты в портфеле ({len(symbols)}): {', '.join(symbols)}\n")

    symbol_dfs = load_symbol_data(symbols)

    print("Глубина истории по каждой монете (до выравнивания):")
    for symbol, df in symbol_dfs.items():
        print(f"  {symbol:14s} {df['time_utc'].min()} -> {df['time_utc'].max()}")
    print()

    symbol_dfs = {symbol: strategies.add_ema_signals(df) for symbol, df in symbol_dfs.items()}
    symbol_dfs = align_to_common_window(symbol_dfs)

    common_days = (
        min(df["time_utc"].max() for df in symbol_dfs.values())
        - max(df["time_utc"].min() for df in symbol_dfs.values())
    ).days
    if common_days < 180:
        print("\nВНИМАНИЕ: общий период короче 6 месяцев - для честной проверки стратегии")
        print("рекомендуется минимум 180 дней. Продолжаю с тем, что есть.")
    print()

    trades, equity_df = run_portfolio_backtest(symbol_dfs, risk_gate.STARTING_BALANCE_USDT)

    title = (
        f"Результаты портфельного бэктеста EMA trend-following, {len(symbol_dfs)} монет "
        f"({strategies.EMA_FAST}/{strategies.EMA_SLOW}, стоп {strategies.ATR_STOP_MULT}xATR{strategies.ATR_PERIOD})"
    )
    print_report(trades, equity_df, risk_gate.STARTING_BALANCE_USDT, title)

    out_dir = Path(__file__).resolve().parent
    save_outputs(trades, equity_df, out_dir, title, file_prefix="ema_trend_portfolio")


if __name__ == "__main__":
    main()
