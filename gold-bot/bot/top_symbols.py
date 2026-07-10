"""
Определяет топ-N USDT-перпетуалов по объёму торгов за 24ч на Bybit и
сохраняет список в data/top_symbols.txt - его использует
bot/fetch_history_bybit.py (режим TOP10) и backtest/run_backtest.py.

Публичные данные - API-ключи НЕ нужны.

Использование:
    python bot\\top_symbols.py        # топ-10 (по умолчанию)
    python bot\\top_symbols.py 20     # топ-20
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from pybit.unified_trading import HTTP
except ImportError:
    print("Библиотека pybit не установлена.")
    print("Установите её командой:  pip install pybit")
    sys.exit(1)

import config

TOP_N_DEFAULT = 10


def get_top_symbols(session, top_n: int = TOP_N_DEFAULT) -> list[str]:
    resp = session.get_tickers(category=config.CATEGORY)
    tickers = resp["result"]["list"]

    # На всякий случай фильтруем именно USDT-перпы (linear-категория может
    # в теории содержать и другие quote-валюты).
    usdt_perps = [t for t in tickers if t["symbol"].endswith("USDT")]
    usdt_perps.sort(key=lambda t: float(t["turnover24h"]), reverse=True)

    return [t["symbol"] for t in usdt_perps[:top_n]]


def main():
    top_n = int(sys.argv[1]) if len(sys.argv) > 1 else TOP_N_DEFAULT

    session = HTTP(testnet=False)  # публичные данные, ключи не нужны

    print(f"Запрашиваю топ-{top_n} USDT-перпетуалов по объёму за 24ч на Bybit...")
    symbols = get_top_symbols(session, top_n)

    print(f"\nТоп-{top_n} по объёму:")
    for i, s in enumerate(symbols, 1):
        print(f"  {i}. {s}")

    out_path = Path(config.DATA_DIR) / "top_symbols.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(symbols))
    print(f"\nСписок сохранён: {out_path}")
    print("Дальше: python bot\\fetch_history_bybit.py TOP10")


if __name__ == "__main__":
    main()
