"""
Этап 0: проверка связки Python <-> MetaTrader5 <-> демо-счёт XM.

Что делает скрипт:
1. Подключается к уже запущенному и залогиненному терминалу MetaTrader 5.
2. Печатает информацию о счёте: баланс, эквити, плечо, демо это или реальный счёт.
3. Печатает текущий bid/ask по XAUUSD.
4. Считает фактический спред: в пунктах и в долларах на лот 0.01 (пригодится в бэктесте на этапе 3).
5. Печатает время последнего тика и реальное UTC-время - чтобы вручную посчитать смещение
   сервера брокера от UTC и вписать его в config.py (SERVER_UTC_OFFSET_HOURS).

Запускать на Windows, где установлен и открыт терминал MetaTrader 5 с демо-счётом XM.
Терминал должен быть открыт и залогинен ДО запуска скрипта - initialize() сам логин не делает,
он просто подключается к уже работающему терминалу.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Добавляем корневую папку проекта (gold-bot/) в пути поиска модулей.
# Без этого `import config` работает только если запускать скрипт из корня проекта -
# Python по умолчанию ищет модули рядом со скриптом, а не в текущей папке.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import MetaTrader5 as mt5
except ImportError:
    print("Библиотека MetaTrader5 не установлена.")
    print("Установите её командой:  pip install MetaTrader5")
    sys.exit(1)

import config

SYMBOL = config.SYMBOL


def main():
    # 1. Подключаемся к уже открытому терминалу. Логин/пароль здесь не нужны -
    # терминал должен быть заранее вручную залогинен в демо-счёт XM.
    if not mt5.initialize():
        print("Не удалось подключиться к терминалу MT5.")
        print("Код ошибки:", mt5.last_error())
        print()
        print("Проверьте:")
        print("  1. Терминал MetaTrader 5 запущен и залогинен в демо-счёт XM.")
        print("  2. В терминале включена автоторговля (кнопка 'Algo Trading' зелёная).")
        print("  3. Если терминал установлен не в стандартную папку, укажите путь явно:")
        print("     mt5.initialize(path=r'C:\\Program Files\\XM Global MT5\\terminal64.exe')")
        sys.exit(1)

    print("=" * 60)
    print("Подключение к MT5 успешно")
    print("=" * 60)

    # 2. Информация о терминале и счёте
    terminal_info = mt5.terminal_info()
    account_info = mt5.account_info()

    if account_info is None:
        print("Не удалось получить данные счёта. Вы точно залогинены в терминале вручную?")
        mt5.shutdown()
        sys.exit(1)

    is_demo = account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO

    print(f"Терминал:         {terminal_info.name} (сборка {terminal_info.build})")
    print(f"Сервер:           {account_info.server}")
    print(f"Счёт:             {account_info.login}  ({'демо' if is_demo else 'РЕАЛЬНЫЙ !!!'})")
    print(f"Баланс:           {account_info.balance:.2f} {account_info.currency}")
    print(f"Эквити:           {account_info.equity:.2f} {account_info.currency}")
    print(f"Кредитное плечо:  1:{account_info.leverage}")

    if not is_demo:
        print()
        print("!!! ВНИМАНИЕ: это НЕ демо-счёт.")
        print("!!! По правилам проекта этапы 0-4 выполняются только на демо-счёте.")
        print("!!! Переключите терминал на демо-счёт XM и запустите скрипт заново.")
        mt5.shutdown()
        sys.exit(1)

    # 3. Проверяем, что символ доступен, и добавляем его в Market Watch, если нужно
    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None:
        print(f"\nСимвол {SYMBOL} не найден у брокера.")
        print("Откройте Market Watch в терминале и проверьте точное название золота у XM")
        print("(бывает XAUUSD, реже XAUUSD.m и т.п.) - поправьте SYMBOL в config.py.")
        mt5.shutdown()
        sys.exit(1)

    if not symbol_info.visible:
        mt5.symbol_select(SYMBOL, True)
        symbol_info = mt5.symbol_info(SYMBOL)  # перечитываем после добавления в обзор рынка

    # 4. Текущая котировка и спред
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        print(f"\nНе удалось получить котировку по {SYMBOL}.")
        mt5.shutdown()
        sys.exit(1)

    point = symbol_info.point                       # шаг цены (обычно 0.01 у золота)
    contract_size = symbol_info.trade_contract_size  # унций золота на 1 лот - берём у брокера, не считаем "на глаз"
    spread_points = (tick.ask - tick.bid) / point
    spread_usd_per_lot = (tick.ask - tick.bid) * contract_size
    spread_usd_001_lot = spread_usd_per_lot * 0.01

    print()
    print("-" * 60)
    print(f"Котировка {SYMBOL}")
    print("-" * 60)
    print(f"Bid:                     {tick.bid}")
    print(f"Ask:                     {tick.ask}")
    print(f"Шаг цены (point):        {point}")
    print(f"Contract size:           {contract_size} (унций золота на 1 лот)")
    print(f"Спред:                   {spread_points:.1f} пунктов")
    print(f"Спред в $ на лот 0.01:   ${spread_usd_001_lot:.2f}")
    print()
    print("Это МГНОВЕННЫЙ замер - спред у золота гуляет в течение дня (шире на новостях")
    print("и в моменты низкой ликвидности). Для бэктеста на этапе 3 такие замеры нужно")
    print("будет сделать несколько раз в разное время суток, а не полагаться на один запуск.")

    # 5. Время сервера vs UTC - нужно для этапа 2 (анализ по часам суток в UTC+5)
    server_time = datetime.fromtimestamp(tick.time, tz=timezone.utc)
    utc_now = datetime.now(timezone.utc)
    my_time_now = utc_now.astimezone(timezone(timedelta(hours=config.MY_TIMEZONE_OFFSET_HOURS)))

    print()
    print("-" * 60)
    print("Время (для расчёта смещения сервера брокера от UTC)")
    print("-" * 60)
    print(f"Время последнего тика (метка сервера):  {server_time}")
    print(f"Реальное текущее время UTC:              {utc_now}")
    print(f"Реальное текущее время в вашем поясе:    {my_time_now}  (UTC+{config.MY_TIMEZONE_OFFSET_HOURS})")
    print()
    print("Разница между 'временем тика' и 'реальным UTC' (округлённо, в часах) и есть")
    print("смещение сервера XM от UTC. Впишите это число в config.py -> SERVER_UTC_OFFSET_HOURS,")
    print("оно понадобится на этапе 2, чтобы правильно перевести часы свечей MT5 в UTC+5.")

    mt5.shutdown()
    print()
    print("=" * 60)
    print("Проверка завершена успешно. Связка Python <-> MT5 <-> XM работает.")
    print("=" * 60)


if __name__ == "__main__":
    main()
