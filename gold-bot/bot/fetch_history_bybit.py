"""
Этап 1: выгрузка исторических свечей с Bybit и сохранение в parquet.

Публичный REST API - API-ключи НЕ нужны, работает даже без .env (в отличие
от MT5 не нужен запущенный терминал - это просто HTTP-запрос).

Bybit отдаёт максимум 1000 свечей за один запрос (лимит kline API) - тянем
порциями назад по времени (пагинация через параметр end), пока биржа не
перестанет отдавать новые данные.

Использование:
    python bot\\fetch_history_bybit.py                  # config.SYMBOL, config.INTERVAL, максимум истории
    python bot\\fetch_history_bybit.py ETHUSDT           # другой символ
    python bot\\fetch_history_bybit.py BTCUSDT 60        # другой интервал (60 = 1H, "D" = 1 день)
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

MAX_LIMIT_PER_REQUEST = 1000  # ограничение Bybit kline API за один запрос
MAX_REQUESTS = 2000           # защита от бесконечного цикла


def fetch_klines(session, symbol: str, interval: str) -> pd.DataFrame | None:
    """Тянет всю доступную историю порциями, от новых к старым (так Bybit
    отдаёт по умолчанию), и возвращает единый DataFrame в хронологическом порядке."""

    all_rows = []
    end_time = None  # None = начать с самых свежих свечей

    for request_num in range(1, MAX_REQUESTS + 1):
        params = {
            "category": config.CATEGORY,
            "symbol": symbol,
            "interval": interval,
            "limit": MAX_LIMIT_PER_REQUEST,
        }
        if end_time is not None:
            params["end"] = end_time

        resp = session.get_kline(**params)
        rows = resp["result"]["list"]
        if not rows:
            break

        all_rows.extend(rows)
        print(f"    ...порция {request_num}: получено {len(rows)} свечей (всего пока {len(all_rows)})")

        # Bybit возвращает от новых к старым - последний элемент страницы самый старый.
        oldest_ts_ms = int(rows[-1][0])
        end_time = oldest_ts_ms - 1  # следующий запрос - строго раньше самой старой полученной свечи

        if len(rows) < MAX_LIMIT_PER_REQUEST:
            break  # биржа отдала меньше, чем просили - история закончилась

    if not all_rows:
        return None

    df = pd.DataFrame(all_rows, columns=["ts_ms", "open", "high", "low", "close", "volume", "turnover"])
    df = df.drop_duplicates(subset="ts_ms")
    for col in ["open", "high", "low", "close", "volume", "turnover"]:
        df[col] = df[col].astype(float)

    df["time_utc"] = pd.to_datetime(df["ts_ms"].astype(int), unit="ms", utc=True).dt.tz_localize(None)
    df["time_local"] = df["time_utc"] + pd.Timedelta(hours=config.MY_TIMEZONE_OFFSET_HOURS)
    df = df.drop(columns=["ts_ms"]).sort_values("time_utc").reset_index(drop=True)

    return df


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else config.SYMBOL
    interval = sys.argv[2] if len(sys.argv) > 2 else config.INTERVAL

    # Публичные данные - ключи не нужны. testnet=False всегда для истории цен:
    # у testnet своя ненастоящая история, для честного бэктеста нужны только
    # реальные mainnet-данные (даже если торговать потом будем через demo/testnet).
    session = HTTP(testnet=False)

    print("=" * 60)
    print(f"Выгрузка истории {symbol}, интервал {interval}, с Bybit (публичные данные mainnet)")
    print("=" * 60)

    df = fetch_klines(session, symbol, interval)
    if df is None:
        print("Данных не получено - проверьте название символа и интервал.")
        sys.exit(1)

    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)

    tf_name = f"M{interval}" if interval.isdigit() else interval
    out_path = data_dir / f"{symbol}_{tf_name}.parquet"
    df.to_parquet(out_path, index=False)

    print(f"\nСвечей: {len(df)}")
    print(f"Период (UTC):              {df['time_utc'].min()} -> {df['time_utc'].max()}")
    print(f"Период (UTC+{config.MY_TIMEZONE_OFFSET_HOURS}, ваше время): {df['time_local'].min()} -> {df['time_local'].max()}")
    print(f"Сохранено в: {out_path}")


if __name__ == "__main__":
    main()
