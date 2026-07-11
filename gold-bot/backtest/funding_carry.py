"""
Funding rate carry: дельта-нейтральная идея - спот-лонг + шорт перпетуала
ОДНОГО notional'а. Пока funding положительный, лонги (по перпетуалу) платят
шортам - наша позиция (шорт перп + лонг спот) получает эти выплаты. Движение
цены самого актива для P&L не важно - спот и перп компенсируют друг друга.
Принципиально другой профиль риска, чем всё, что тестировали раньше:
не направленная ставка на цену, а ставка на то, что funding останется
положительным достаточно долго, чтобы окупить costы входа/выхода.

ВАЖНОЕ УПРОЩЕНИЕ этого первого прогона: считаем спот и перп идеально
синхронными (базисный риск = 0) - у нас нет скачанной истории спот-цены
отдельно от перпетуала. Реальный funding-carry несёт небольшой базисный риск
(спот и перп расходятся на исполнении) - здесь он не смоделирован, это
приближение, а не полная картина.

Это НЕ вписывается в обычную модель risk_gate (стоп-лосс от цены) - здесь
риск другой (funding развернётся, а не цена уйдёт против позиции). Размер
позиции считается через капитал ОБЕИХ ног хеджа (см. size_position ниже) -
спот требует полную сумму кэшем, перп - только маржу с плечом. Без
стоп-дистанции - осознанное, явно прописанное отступление от общего правила
"нет стопа - нет сделки", подходящее именно для дельта-нейтральных позиций,
где ценовой стоп не имеет смысла (цена не создаёт риска напрямую - но см.
предупреждение про риск ликвидации перп-ноги в size_position).

Параметры ниже - первая гипотеза для проверки на истории, не подогнанные числа.
"""

import sys
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import risk_gate

SPOT_TAKER_FEE_PCT = 0.10 / 100  # типичная комиссия Bybit spot taker - ПРИБЛИЖЕНИЕ, не измерено на вашем счету
PERP_TAKER_FEE_PCT = risk_gate.TAKER_FEE_PCT  # 0.055%, официальная ставка Bybit (та же, что у направленных стратегий)

ENTRY_FUNDING_THRESHOLD = 0.0003  # входим, если funding rate за период > 0.03% - должен окупить round-trip costы
EXIT_FUNDING_THRESHOLD = 0.0      # выходим (закрываем обе ноги), если funding падает до нуля/отрицательный


@dataclass
class CarryTrade:
    symbol: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    notional_usdt: float
    periods_held: int
    funding_collected_usdt: float
    entry_exit_cost_usdt: float
    pnl_usdt: float


PERP_LEG_LEVERAGE = 5.0  # плечо ТОЛЬКО на перп-ноге хеджа (margin trading для спота здесь не считаем)


def size_position(equity_usdt: float) -> float:
    """Дельта-нейтральная позиция состоит из ДВУХ ног: спот-лонг (обычно
    требует ПОЛНУЮ сумму кэшем, без плеча - в отличие от перпетуала) и
    шорт-перп (margin = notional / PERP_LEG_LEVERAGE). Значит весь капитал
    равен notional (спот) + notional/PERP_LEG_LEVERAGE (маржа перпа):

        equity = notional * (1 + 1 / PERP_LEG_LEVERAGE)
        notional = equity / (1 + 1 / PERP_LEG_LEVERAGE)

    ВАЖНО: даже позиция без ценового риска (спот и перп теоретически
    компенсируют друг друга) НЕ означает без риска ликвидации - маржа на
    перп-ноге считается биржей ОТДЕЛЬНО от спот-позиции (если не используется
    специальный portfolio margin режим), так что резкое движение цены может
    залинквидировать именно перп-ногу раньше, чем спот успеет компенсировать
    это на бумаге. Здесь этот риск НЕ смоделирован (для этого нужна отдельная
    история цены с достаточной детализацией) - используем консервативное
    PERP_LEG_LEVERAGE, а не берём его "бесплатно" как расчётный трюк."""
    return equity_usdt / (1 + 1 / PERP_LEG_LEVERAGE)


def run_funding_carry_backtest(funding_df: pd.DataFrame, symbol: str, starting_equity: float):
    """funding_df - история funding rate одной монеты (колонки time_utc,
    funding_rate), отсортирована по времени. Каждая строка - один период
    начисления (8ч на Bybit).

    Возвращает (список CarryTrade, DataFrame кривой капитала).
    """

    trades: list[CarryTrade] = []
    equity = starting_equity
    equity_curve = [{"time": funding_df["time_utc"].iloc[0] if len(funding_df) else None, "equity": equity}]

    in_position = False
    entry_time = None
    notional_usdt = 0.0
    funding_collected = 0.0
    periods_held = 0

    for _, row in funding_df.iterrows():
        rate = row["funding_rate"]

        if not in_position:
            if rate > ENTRY_FUNDING_THRESHOLD:
                candidate_notional = size_position(equity)
                if candidate_notional < risk_gate.MIN_ORDER_USDT:
                    continue  # даже с максимальным плечом позиция меньше минимального ордера - пропускаем
                in_position = True
                entry_time = row["time_utc"]
                notional_usdt = candidate_notional
                funding_collected = 0.0
                periods_held = 0
            continue

        # Продолжаем держать хедж, пока funding остаётся выгодным - копим
        # funding за КАЖДЫЙ период вместо того, чтобы разворачивать обе ноги
        # каждый раз. Именно в этом смысл carry: costы входа/выхода платятся
        # один раз за всё время удержания, а не за каждый отдельный период.
        funding_collected += notional_usdt * rate
        periods_held += 1

        if rate <= EXIT_FUNDING_THRESHOLD:
            cost = notional_usdt * (SPOT_TAKER_FEE_PCT + PERP_TAKER_FEE_PCT) * 2  # вход + выход, обе ноги
            pnl = funding_collected - cost
            equity += pnl

            trades.append(CarryTrade(
                symbol=symbol,
                entry_time=entry_time,
                exit_time=row["time_utc"],
                notional_usdt=notional_usdt,
                periods_held=periods_held,
                funding_collected_usdt=funding_collected,
                entry_exit_cost_usdt=cost,
                pnl_usdt=pnl,
            ))
            equity_curve.append({"time": row["time_utc"], "equity": equity})
            in_position = False

    if in_position:
        last_row = funding_df.iloc[-1]
        cost = notional_usdt * (SPOT_TAKER_FEE_PCT + PERP_TAKER_FEE_PCT) * 2
        pnl = funding_collected - cost
        equity += pnl
        trades.append(CarryTrade(
            symbol=symbol,
            entry_time=entry_time,
            exit_time=last_row["time_utc"],
            notional_usdt=notional_usdt,
            periods_held=periods_held,
            funding_collected_usdt=funding_collected,
            entry_exit_cost_usdt=cost,
            pnl_usdt=pnl,
        ))
        equity_curve.append({"time": last_row["time_utc"], "equity": equity})

    return trades, pd.DataFrame(equity_curve)
