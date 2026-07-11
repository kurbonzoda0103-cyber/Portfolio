"""
risk_gate.py - ЕДИНАЯ точка проверки риска. И бэктест, и живой бот (когда
дойдём до этапа 4) обязаны проводить КАЖДЫЙ ордер через этот модуль - ни
стратегия, ни движок бэктеста не считают размер позиции напрямую. Смысл:
бэктест и реальная торговля должны использовать один и тот же риск-код, иначе
они могут разойтись (в бэктесте одни правила, в реальности - другие по ошибке).

Правила ЖЁСТКО зашиты здесь как константы модуля, а не в config.py - чтобы
стратегия физически не могла их случайно обойти или переопределить. Менять
можно только вручную, отредактировав этот файл, осознанно.
"""

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Жёсткие риск-правила проекта
# ---------------------------------------------------------------------------
STARTING_BALANCE_USDT = 50.0

RISK_PER_TRADE_PCT = 2.0          # % от equity на одну сделку
RISK_PER_TRADE_CEILING_PCT = 3.0  # RISK_PER_TRADE_PCT можно менять руками, но не выше этого потолка

MAX_EFFECTIVE_LEVERAGE = 5.0      # номинал позиции <= MAX_EFFECTIVE_LEVERAGE * equity, даже если биржа даёт больше

DAILY_LOSS_LIMIT_PCT = 6.0        # % от equity на НАЧАЛО дня - при достижении полная остановка до следующего дня
MAX_LOSING_TRADES_PER_DAY = 2     # после стольких убыточных сделок за день - тоже стоп до следующего дня

MIN_ORDER_USDT = 5.0              # минимальный размер ордера на Bybit (примерно; уточняется у биржи для конкретного инструмента)

# Это НЕ защитный риск-лимит (не про убытки), а осознанный выбор селективности:
# Али важно совершать пару качественных сделок в день по всему портфелю, а не
# заходить в каждый сигнал по каждой из 8 монет. Ограничивает число НОВЫХ
# позиций за день - остальные сигналы в этот день просто пропускаются.
MAX_NEW_POSITIONS_PER_DAY = 2

TAKER_FEE_PCT = 0.055 / 100       # комиссия taker (вход и выход - оба маркет-ордера в бэктесте)

# ПРИБЛИЖЕНИЕ, не измеренный факт: типичный funding rate для BTCUSDT perpetual
# на Bybit колеблется в районе 0.01% за 8 часов, но реально плавает и может
# быть отрицательным. Перед тем как доверять итоговым цифрам бэктеста, стоит
# свериться с реальной историей funding rate через Bybit API.
ASSUMED_FUNDING_RATE_PER_8H = 0.0001

assert RISK_PER_TRADE_PCT <= RISK_PER_TRADE_CEILING_PCT, (
    f"RISK_PER_TRADE_PCT ({RISK_PER_TRADE_PCT}) не может быть выше потолка {RISK_PER_TRADE_CEILING_PCT}"
)


class OrderRejected(Exception):
    """Ордер не может быть отправлен: нет стопа, лот меньше минимума биржи,
    или торговля на сегодня уже остановлена риск-лимитами."""


@dataclass
class DailyState:
    """Состояние риска на текущий торговый день - ОБЩЕЕ на весь портфель (все
    монеты сразу), не по одной монете. Сбрасывается в начале каждого нового
    дня (используется и в бэктесте, и в живом боте одинаково).

    open_notional_usdt - суммарный номинал ВСЕХ открытых позиций по ВСЕМ
    монетам прямо сейчас. Нужен, чтобы MAX_EFFECTIVE_LEVERAGE ограничивал
    портфель целиком, а не давал каждой монете своё собственное 5x - иначе
    при 10 одновременных позициях реальный риск мог бы дойти до 50x депозита."""

    day: object = None
    start_of_day_equity: float = 0.0
    losing_trades_today: int = 0
    realized_pnl_today: float = 0.0
    halted: bool = False
    halt_reason: str = ""
    open_notional_usdt: float = 0.0
    new_positions_today: int = 0

    def reset(self, day, equity: float):
        self.day = day
        self.start_of_day_equity = equity
        self.losing_trades_today = 0
        self.realized_pnl_today = 0.0
        self.halted = False
        self.halt_reason = ""
        self.new_positions_today = 0
        # open_notional_usdt НЕ сбрасываем - позиции могли остаться открытыми с предыдущего дня

    def register_trade_result(self, pnl_usdt: float):
        """Вызывать после КАЖДОГО закрытия сделки (по любой монете) - обновляет
        счётчики и, если лимиты превышены, останавливает торговлю ПО ВСЕМУ
        ПОРТФЕЛЮ до конца дня (не только по той монете, где случился убыток)."""
        self.realized_pnl_today += pnl_usdt
        if pnl_usdt < 0:
            self.losing_trades_today += 1

        if self.losing_trades_today >= MAX_LOSING_TRADES_PER_DAY:
            self.halted = True
            self.halt_reason = f"{MAX_LOSING_TRADES_PER_DAY} убыточных сделки за день (по всему портфелю)"
        elif self.realized_pnl_today <= -self.start_of_day_equity * DAILY_LOSS_LIMIT_PCT / 100:
            self.halted = True
            self.halt_reason = f"дневной лимит убытка {DAILY_LOSS_LIMIT_PCT}% от equity на начало дня достигнут"


def can_trade_today(daily_state: DailyState) -> bool:
    """Разрешена ли торговля вообще (риск-лимиты не нарушены). Не путать с
    has_reached_daily_trade_quota - это про убытки, а квота про селективность."""
    return not daily_state.halted


def has_reached_daily_trade_quota(daily_state: DailyState) -> bool:
    """True, если на сегодня уже открыто MAX_NEW_POSITIONS_PER_DAY новых
    позиций - остальные сигналы в этот день пропускаются, даже если риск-лимиты
    не нарушены. Это выбор селективности (пара сделок в день), а не защита от убытков."""
    return daily_state.new_positions_today >= MAX_NEW_POSITIONS_PER_DAY


def compute_position_size(
    equity_usdt: float, entry_price: float, stop_price: float | None, open_notional_usdt: float = 0.0
) -> float:
    """Размер позиции в базовой монете (BTC, ETH, ...), рассчитанный от риска
    на сделку, с ограничением по ЭФФЕКТИВНОМУ ПЛЕЧУ ВСЕГО ПОРТФЕЛЯ (а не этой
    одной монеты - см. open_notional_usdt в DailyState). Стоп-лосс ОБЯЗАТЕЛЕН -
    без него функция сразу бросает исключение, а не считает "какой-нибудь" размер."""

    if stop_price is None:
        raise OrderRejected("Стоп-лосс обязателен - ордер без стопа не отправляется.")

    if entry_price <= 0:
        raise OrderRejected(f"Цена входа некорректна ({entry_price}) - реальная цена не может быть <= 0.")

    stop_distance = abs(entry_price - stop_price)
    if stop_distance <= 0:
        raise OrderRejected("Стоп-лосс совпадает с ценой входа или некорректен.")

    risk_amount_usdt = equity_usdt * RISK_PER_TRADE_PCT / 100
    qty = risk_amount_usdt / stop_distance

    # Плечо ограничиваем на весь портфель: новая позиция не может увеличить
    # суммарный номинал (уже открытые позиции по другим монетам + эта) выше
    # MAX_EFFECTIVE_LEVERAGE * equity.
    remaining_notional_budget = max(0.0, MAX_EFFECTIVE_LEVERAGE * equity_usdt - open_notional_usdt)
    max_qty_by_leverage = remaining_notional_budget / entry_price
    qty = min(qty, max_qty_by_leverage)

    return qty


def validate_order(
    equity_usdt: float, entry_price: float, stop_price: float | None, daily_state: DailyState
) -> float:
    """ЕДИНСТВЕННЫЙ способ получить размер позиции для реального/бэктестового
    ордера. Возвращает qty, если ордер разрешён; иначе бросает OrderRejected с
    человекочитаемой причиной. daily_state.open_notional_usdt используется для
    портфельного лимита плеча - вызывающий код должен обновлять его при
    открытии/закрытии КАЖДОЙ позиции по КАЖДОЙ монете (см. backtest/engine.py)."""

    if not can_trade_today(daily_state):
        raise OrderRejected(f"Торговля на сегодня остановлена: {daily_state.halt_reason}")

    qty = compute_position_size(equity_usdt, entry_price, stop_price, daily_state.open_notional_usdt)
    notional_usdt = qty * entry_price

    if notional_usdt < MIN_ORDER_USDT:
        raise OrderRejected(
            f"Размер позиции ${notional_usdt:.2f} меньше минимального ордера Bybit (${MIN_ORDER_USDT})."
        )

    return qty


def compute_costs_usdt(qty: float, entry_price: float, exit_price: float, funding_periods_held: int) -> dict:
    """Комиссия taker (вход + выход, оба маркет-ордера) + funding за время
    удержания позиции. Funding - ПРИБЛИЖЕНИЕ (см. ASSUMED_FUNDING_RATE_PER_8H
    выше), не измеренный факт для реального счёта."""

    entry_notional = qty * entry_price
    exit_notional = qty * exit_price
    fee_usdt = (entry_notional + exit_notional) * TAKER_FEE_PCT
    funding_usdt = entry_notional * ASSUMED_FUNDING_RATE_PER_8H * funding_periods_held

    return {
        "fee_usdt": fee_usdt,
        "funding_usdt": funding_usdt,
        "total_cost_usdt": fee_usdt + funding_usdt,
    }
