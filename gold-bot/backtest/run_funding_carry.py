"""
Этап 3, принципиально новая идея: funding rate carry (не направленная
торговля, а сбор funding через дельта-нейтральную позицию спот-лонг + шорт-
перп). См. backtest/funding_carry.py - там подробно объяснена механика и
упрощения (в частности: базисный риск спот/перп не смоделирован).

Каждая монета тестируется НЕЗАВИСИМО (свой стартовый капитал risk_gate.
STARTING_BALANCE_USDT) - это не портфель с общими лимитами, как в
run_backtest.py, а раздельная проверка идеи по каждой монете. Если результат
по какой-то монете выглядит рабочим, тогда уже можно думать про объединение
в портфель.

Нужна история funding rate (публичные данные, ключи не нужны):
    python bot\\top_symbols.py
    python bot\\fetch_funding_rate.py TOP10

Честно печатает результат, включая отрицательный.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
import risk_gate
from backtest.funding_carry import run_funding_carry_backtest


def load_symbol_list() -> list[str]:
    path = Path(config.DATA_DIR) / "top_symbols.txt"
    if not path.exists():
        print(f"Не найден {path}.")
        print("Сначала запустите: python bot\\top_symbols.py")
        sys.exit(1)
    return [s.strip() for s in path.read_text().splitlines() if s.strip()]


def summarize(trades, equity_df, starting_equity: float) -> dict:
    if not trades:
        return {"сделок": 0, "funding_$": 0.0, "cost_$": 0.0, "доходность_%": 0.0, "ср_часов_держали": 0.0}

    funding = sum(t.funding_collected_usdt for t in trades)
    cost = sum(t.entry_exit_cost_usdt for t in trades)
    final_equity = equity_df["equity"].iloc[-1]
    avg_periods = sum(t.periods_held for t in trades) / len(trades)

    return {
        "сделок": len(trades),
        "funding_$": round(funding, 2),
        "cost_$": round(cost, 2),
        "доходность_%": round((final_equity / starting_equity - 1) * 100, 1),
        "ср_часов_держали": round(avg_periods * 8, 1),
    }


def main():
    symbols = load_symbol_list()
    data_dir = Path(config.DATA_DIR)

    rows = {}
    for symbol in symbols:
        path = data_dir / f"{symbol}_funding.parquet"
        if not path.exists():
            print(f"{symbol}: нет файла {path} - пропускаю (запустите bot\\fetch_funding_rate.py TOP10).")
            continue

        funding_df = pd.read_parquet(path)
        trades, equity_df = run_funding_carry_backtest(funding_df, symbol, risk_gate.STARTING_BALANCE_USDT)
        rows[symbol] = summarize(trades, equity_df, risk_gate.STARTING_BALANCE_USDT)

    if not rows:
        print("Ни одной монеты с funding rate данными не найдено.")
        sys.exit(1)

    table = pd.DataFrame(rows).T.sort_values("доходность_%", ascending=False)

    print("=" * 90)
    print(f"Funding rate carry - независимая проверка по каждой монете, старт ${risk_gate.STARTING_BALANCE_USDT:.0f}")
    print("=" * 90)
    print(table.to_string())

    out_path = Path(__file__).resolve().parent / "funding_carry_comparison.csv"
    table.to_csv(out_path)
    print(f"\nТаблица сохранена: {out_path}")

    print()
    print("ВАЖНО: упрощение - базисный риск (расхождение спот/перп) не смоделирован,")
    print("комиссия спот-счёта (0.10%) - ПРИБЛИЖЕНИЕ, не измерено на вашем счету.")
    print("Если результат выглядит многообещающе - перед тем как доверять, нужно")
    print("замерить реальную комиссию спот-счёта и оценить базисный риск отдельно.")


if __name__ == "__main__":
    main()
