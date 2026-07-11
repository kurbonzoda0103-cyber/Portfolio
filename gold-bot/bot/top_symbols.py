"""
Готовит список монет для портфеля в data/top_symbols.txt - его использует
bot/fetch_history_bybit.py (режим TOP10) и backtest/run_backtest.py.

Если config.MANUAL_SYMBOLS не пуст - используется он напрямую, без обращения
к API (список монет выбран владельцем проекта вручную, не по объёму).
Если пуст - определяется топ-N USDT-перпетуалов по объёму торгов за 24ч на
Bybit (публичные данные, ключи не нужны).

Использование:
    python bot\\top_symbols.py        # config.MANUAL_SYMBOLS, если задан; иначе топ-10 по объёму
    python bot\\top_symbols.py 20     # топ-20 по объёму (игнорирует MANUAL_SYMBOLS)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
    out_path = Path(config.DATA_DIR) / "top_symbols.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Ручной список побеждает авто-подбор, если явно не запросили конкретное
    # число монет через аргумент командной строки (sys.argv[1] означает "хочу
    # именно топ-N по объёму, а не ручной список").
    if config.MANUAL_SYMBOLS and len(sys.argv) <= 1:
        symbols = config.MANUAL_SYMBOLS
        print(f"Используется ручной список из config.py -> MANUAL_SYMBOLS ({len(symbols)} монет):")
        for i, s in enumerate(symbols, 1):
            print(f"  {i}. {s}")
    else:
        try:
            from pybit.unified_trading import HTTP
        except ImportError:
            print("Библиотека pybit не установлена.")
            print("Установите её командой:  pip install pybit")
            sys.exit(1)

        top_n = int(sys.argv[1]) if len(sys.argv) > 1 else TOP_N_DEFAULT
        session = HTTP(testnet=False)  # публичные данные, ключи не нужны

        print(f"Запрашиваю топ-{top_n} USDT-перпетуалов по объёму за 24ч на Bybit...")
        symbols = get_top_symbols(session, top_n)

        print(f"\nТоп-{top_n} по объёму:")
        for i, s in enumerate(symbols, 1):
            print(f"  {i}. {s}")

    out_path.write_text("\n".join(symbols))
    print(f"\nСписок сохранён: {out_path}")
    print("Дальше: python bot\\fetch_history_bybit.py TOP10")


if __name__ == "__main__":
    main()
