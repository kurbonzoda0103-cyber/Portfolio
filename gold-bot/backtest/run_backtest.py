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


def main():
    symbols = load_symbol_list()
    print(f"Монеты в портфеле ({len(symbols)}): {', '.join(symbols)}\n")

    symbol_dfs = load_symbol_data(symbols)

    min_days = min(
        (df["time_utc"].max() - df["time_utc"].min()).days for df in symbol_dfs.values()
    )
    print(f"Данные загружены для {len(symbol_dfs)}/{len(symbols)} монет, "
          f"кратчайшая история: {min_days} дней (~{min_days / 30:.1f} мес.)")
    if min_days < 180:
        print("ВНИМАНИЕ: у минимум одной монеты истории меньше 6 месяцев - для честной")
        print("проверки стратегии рекомендуется минимум 180 дней по каждой монете.")
    print()

    symbol_dfs = {symbol: strategies.add_ema_signals(df) for symbol, df in symbol_dfs.items()}

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
