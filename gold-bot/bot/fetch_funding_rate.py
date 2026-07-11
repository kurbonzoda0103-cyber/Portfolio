"""
Выгрузка исторических funding rate с Bybit - нужна для проверки идеи funding
rate carry (см. backtest/funding_carry.py): дельта-нейтральная позиция
(спот-лонг + шорт перпетуала одного объёма) собирает funding rate вместо
направленной ставки на цену - принципиально другой профиль риска, чем всё,
что тестировали раньше.

Публичный REST API - ключи НЕ нужны.

Bybit отдаёт максимум 200 записей funding rate за один запрос (funding
начисляется раз в 8 часов - 200 записей это ~66 дней) - тянем порциями назад
по времени, как и историю свечей.

Использование:
    python bot\\fetch_funding_rate.py                # config.SYMBOL
    python bot\\fetch_funding_rate.py ETHUSDT
    python bot\\fetch_funding_rate.py TOP10           # все монеты из data/top_symbols.txt
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

import pandas as pd
import config

MAX_LIMIT_PER_REQUEST = 200  # ограничение Bybit funding rate history API за один запрос
MAX_REQUESTS = 2000


def fetch_funding_history(session, symbol: str) -> pd.DataFrame | None:
    """Тянет всю доступную историю funding rate порциями, от новых к старым."""

    all_rows = []
    end_time = None

    for request_num in range(1, MAX_REQUESTS + 1):
        params = {"category": config.CATEGORY, "symbol": symbol, "limit": MAX_LIMIT_PER_REQUEST}
        if end_time is not None:
            params["endTime"] = end_time

        resp = session.get_funding_rate_history(**params)
        rows = resp["result"]["list"]
        if not rows:
            break

        all_rows.extend(rows)
        print(f"    ...порция {request_num}: получено {len(rows)} записей (всего пока {len(all_rows)})")

        oldest_ts_ms = min(int(r["fundingRateTimestamp"]) for r in rows)
        end_time = oldest_ts_ms - 1

        if len(rows) < MAX_LIMIT_PER_REQUEST:
            break

    if not all_rows:
        return None

    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates(subset="fundingRateTimestamp")
    df["funding_rate"] = df["fundingRate"].astype(float)
    df["time_utc"] = pd.to_datetime(df["fundingRateTimestamp"].astype(int), unit="ms", utc=True).dt.tz_localize(None)
    df["time_local"] = df["time_utc"] + pd.Timedelta(hours=config.MY_TIMEZONE_OFFSET_HOURS)
    df = df[["time_utc", "time_local", "funding_rate"]].sort_values("time_utc").reset_index(drop=True)

    return df


def fetch_and_save_one(session, symbol: str, data_dir: Path) -> bool:
    print(f"\n{symbol}: запрашиваю funding rate у биржи...")
    df = fetch_funding_history(session, symbol)
    if df is None:
        print(f"  {symbol}: данных нет.")
        return False

    out_path = data_dir / f"{symbol}_funding.parquet"
    df.to_parquet(out_path, index=False)

    print(f"  Записей: {len(df)}")
    print(f"  Период (UTC): {df['time_utc'].min()} -> {df['time_utc'].max()}")
    print(f"  Средний funding rate: {df['funding_rate'].mean() * 100:.4f}% за период")
    print(f"  Сохранено в: {out_path}")
    return True


def main():
    first_arg = sys.argv[1] if len(sys.argv) > 1 else config.SYMBOL
    session = HTTP(testnet=False)  # публичные данные, ключи не нужны

    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)

    if first_arg.upper() == "TOP10":
        symbols_path = data_dir / "top_symbols.txt"
        if not symbols_path.exists():
            print(f"Не найден {symbols_path}. Сначала запустите: python bot\\top_symbols.py")
            sys.exit(1)
        symbols = [s.strip() for s in symbols_path.read_text().splitlines() if s.strip()]

        print("=" * 60)
        print(f"Выгрузка funding rate для {len(symbols)} монет из top_symbols.txt")
        print("=" * 60)

        ok_count = 0
        for symbol in symbols:
            if fetch_and_save_one(session, symbol, data_dir):
                ok_count += 1
        print(f"\nГотово: {ok_count}/{len(symbols)} монет успешно скачаны.")
        return

    print("=" * 60)
    print(f"Выгрузка funding rate {first_arg} с Bybit")
    print("=" * 60)
    if not fetch_and_save_one(session, first_arg, data_dir):
        sys.exit(1)


if __name__ == "__main__":
    main()
