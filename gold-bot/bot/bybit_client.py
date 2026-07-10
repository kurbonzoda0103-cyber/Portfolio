"""
Этап 0: обёртка над pybit для подключения к Bybit (testnet / demo trading /
live - режим выбирается через .env, см. .env.example и README).

Что даёт:
- get_session()       - настроенный HTTP-клиент pybit с нужным режимом
- get_balance()       - баланс USDT unified-счёта
- get_ticker()        - текущая котировка по символу
- account_mode_label() - человекочитаемое описание режима, для логов
- warn_if_live()      - явное предупреждение, если .env указывает на реальный счёт

ВАЖНО: если BYBIT_TESTNET=false И BYBIT_DEMO=false в .env - это РЕАЛЬНЫЙ счёт
с настоящими деньгами. Модуль печатает явное предупреждение при такой
конфигурации. По правилам проекта переход на live требует явного письменного
подтверждения в чате с Claude - если ты не давал такого подтверждения,
останови скрипт и проверь .env.

Запускать этот файл напрямую - быстрая проверка подключения (аналог этапа 0
из MT5-версии проекта): python bot\\bybit_client.py
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


def account_mode_label() -> str:
    if config.BYBIT_DEMO:
        return "DEMO TRADING (виртуальный баланс, реальные рыночные данные Bybit mainnet)"
    if config.BYBIT_TESTNET:
        return "TESTNET (виртуальные деньги, отдельная тестовая сеть Bybit - не настоящие данные рынка)"
    return "LIVE - РЕАЛЬНЫЙ СЧЁТ С НАСТОЯЩИМИ ДЕНЬГАМИ"


def warn_if_live():
    if not config.BYBIT_DEMO and not config.BYBIT_TESTNET:
        print("!" * 70)
        print("!!! ВНИМАНИЕ: BYBIT_DEMO=false и BYBIT_TESTNET=false в .env -")
        print("!!! это РЕАЛЬНЫЙ счёт с настоящими деньгами.")
        print("!!! По правилам проекта переход на live (этап 5) требует твоего явного")
        print("!!! письменного подтверждения в чате с Claude. Если ты не давал такого")
        print("!!! подтверждения - ОСТАНОВИСЬ и проверь .env (BYBIT_DEMO / BYBIT_TESTNET).")
        print("!" * 70)


def get_session() -> "HTTP":
    if not config.BYBIT_API_KEY or not config.BYBIT_API_SECRET:
        print("В .env не заполнены BYBIT_API_KEY / BYBIT_API_SECRET.")
        print("Скопируйте .env.example в .env и впишите ключи (инструкция - в README).")
        sys.exit(1)

    warn_if_live()

    return HTTP(
        testnet=config.BYBIT_TESTNET,
        demo=config.BYBIT_DEMO,
        api_key=config.BYBIT_API_KEY,
        api_secret=config.BYBIT_API_SECRET,
    )


def get_balance(session) -> float:
    """Баланс USDT в unified trading account."""
    resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
    coin_list = resp["result"]["list"][0]["coin"]
    for coin in coin_list:
        if coin["coin"] == "USDT":
            return float(coin["walletBalance"])
    return 0.0


def get_ticker(session, symbol: str | None = None) -> dict:
    """Текущий bid/ask/last по символу (по умолчанию config.SYMBOL)."""
    symbol = symbol or config.SYMBOL
    resp = session.get_tickers(category=config.CATEGORY, symbol=symbol)
    return resp["result"]["list"][0]


def main():
    print("=" * 60)
    print(f"Проверка подключения к Bybit ({account_mode_label()})")
    print("=" * 60)

    session = get_session()

    balance = get_balance(session)
    print(f"Баланс USDT (unified account): {balance:.2f}")

    ticker = get_ticker(session)
    bid, ask, last = float(ticker["bid1Price"]), float(ticker["ask1Price"]), float(ticker["lastPrice"])
    spread = ask - bid

    print(f"\nКотировка {config.SYMBOL}:")
    print(f"  Bid: {bid}   Ask: {ask}   Last: {last}")
    print(f"  Спред: {spread:.2f} USDT ({spread / last * 100:.4f}% от цены)")

    print()
    print("Проверка завершена. Если баланс и котировка выше похожи на правду -")
    print("связка Python <-> Bybit работает.")


if __name__ == "__main__":
    main()
