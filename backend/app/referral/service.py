"""Сервис реферальной программы: коды, привязка, начисления, статистика.

Начисление денег — только ЗАПИСИ в БД (ReferralEarning/ReferralPayout). Никаких
реальных переводов крипты: выплаты обрабатывает админ вручную по статус-флагу.
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..billing.nowpayments import PAID_STATES
from ..billing.tiers import tier_price
from ..models import Payment, ReferralEarning, ReferralPayout, User
from .rate import effective_rate, tier_name

# Алфавит кода: base32-подобный без похожих символов (0/O/1/I исключены).
_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_CODE_LEN = 8


def gen_code(length: int = _CODE_LEN) -> str:
    """Случайный код приглашения (без визуально похожих символов)."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


async def _code_exists(session: AsyncSession, code: str) -> bool:
    row = (
        await session.execute(select(User.id).where(User.referral_code == code))
    ).first()
    return row is not None


async def ensure_code(session: AsyncSession, user: User) -> str:
    """Вернуть реферальный код пользователя, сгенерировав и сохранив при отсутствии."""
    if user.referral_code:
        return user.referral_code
    for _ in range(10):
        code = gen_code()
        if not await _code_exists(session, code):
            user.referral_code = code
            await session.flush()
            return code
    # Крайне маловероятно; расширяем длину как запасной вариант.
    code = gen_code(_CODE_LEN + 4)
    user.referral_code = code
    await session.flush()
    return code


async def attach_referrer(
    session: AsyncSession, user: User, ref_code: str | None
) -> bool:
    """Привязать пригласившего к НОВОМУ пользователю по коду.

    Игнорируется, если: кода нет, код не найден, код свой, привязка уже есть.
    Возвращает True, если привязка установлена.
    """
    if not ref_code:
        return False
    if user.referred_by_id is not None:
        return False
    code = ref_code.strip().upper()
    if not code:
        return False
    referrer = (
        await session.execute(select(User).where(User.referral_code == code))
    ).scalar_one_or_none()
    if referrer is None:
        return False
    if referrer.id == user.id:
        return False
    user.referred_by_id = referrer.id
    await session.flush()
    return True


async def active_referrals(session: AsyncSession, referrer_id: int) -> int:
    """Число РАЗНЫХ приглашённых, у кого есть ≥1 оплаченный платёж."""
    stmt = (
        select(func.count(func.distinct(User.id)))
        .select_from(User)
        .join(Payment, Payment.user_id == User.id)
        .where(
            User.referred_by_id == referrer_id,
            Payment.status.in_(PAID_STATES),
        )
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def credit_referral(
    session: AsyncSession, paying_user: User, payment: Payment
) -> ReferralEarning | None:
    """Начислить реферальное вознаграждение за оплаченный платёж.

    Идемпотентно по payment.id (повторный IPN не создаёт второе начисление).
    Вызывается внутри IPN после установки оплаченного статуса платежа.
    """
    if paying_user.referred_by_id is None:
        return None
    # Идемпотентность: уже начисляли за этот платёж?
    existing = (
        await session.execute(
            select(ReferralEarning).where(ReferralEarning.payment_id == payment.id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    referrer = (
        await session.execute(
            select(User).where(User.id == paying_user.referred_by_id)
        )
    ).scalar_one_or_none()
    if referrer is None:
        return None

    # active включает этого плательщика: его платёж уже помечен оплаченным.
    active = await active_referrals(session, referrer.id)
    rate = effective_rate(referrer.referral_rate_override, active)
    # База комиссии = ФАКТИЧЕСКИ уплаченная сумма (payment.amount_usd уже со скидкой
    # приглашённого −5%). Фолбэк на цену тарифа, если сумма не записана (старые платежи).
    base = payment.amount_usd if payment.amount_usd is not None else (tier_price(payment.tier) or 0.0)
    amount = round(float(base) * rate, 2)

    earning = ReferralEarning(
        referrer_id=referrer.id,
        referred_user_id=paying_user.id,
        payment_id=payment.id,
        amount_usd=amount,
        rate=rate,
        created_at=datetime.now(timezone.utc),
    )
    session.add(earning)
    await session.flush()
    return earning


async def _sum(session: AsyncSession, column, *where) -> float:
    val = (await session.execute(select(func.coalesce(func.sum(column), 0.0)).where(*where))).scalar_one()
    return float(val or 0.0)


async def _count(session: AsyncSession, model, *where) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(model).where(*where))).scalar_one()
    )


async def earned_total(session: AsyncSession, referrer_id: int) -> float:
    return await _sum(
        session, ReferralEarning.amount_usd, ReferralEarning.referrer_id == referrer_id
    )


async def reserved_payouts(session: AsyncSession, referrer_id: int) -> float:
    """Сумма выплат, которые уже «съели» баланс (pending + paid, без rejected)."""
    return await _sum(
        session,
        ReferralPayout.amount_usd,
        ReferralPayout.referrer_id == referrer_id,
        ReferralPayout.status != "rejected",
    )


async def paid_total(session: AsyncSession, referrer_id: int) -> float:
    return await _sum(
        session,
        ReferralPayout.amount_usd,
        ReferralPayout.referrer_id == referrer_id,
        ReferralPayout.status == "paid",
    )


async def balance(session: AsyncSession, referrer_id: int) -> float:
    """Доступный баланс = заработано − (pending + paid выплаты). Никогда не отрицателен."""
    bal = await earned_total(session, referrer_id) - await reserved_payouts(session, referrer_id)
    return round(max(0.0, bal), 2)


async def stats(session: AsyncSession, user: User, recent_limit: int = 20) -> dict:
    """Полная сводка кабинета реферала."""
    referrer_id = user.id
    total_referrals = await _count(session, User, User.referred_by_id == referrer_id)
    active = await active_referrals(session, referrer_id)
    earned = round(await earned_total(session, referrer_id), 2)
    paid = round(await paid_total(session, referrer_id), 2)
    bal = await balance(session, referrer_id)
    rate = effective_rate(user.referral_rate_override, active)

    earnings_rows = (
        await session.execute(
            select(ReferralEarning)
            .where(ReferralEarning.referrer_id == referrer_id)
            .order_by(ReferralEarning.created_at.desc())
            .limit(recent_limit)
        )
    ).scalars().all()
    payout_rows = (
        await session.execute(
            select(ReferralPayout)
            .where(ReferralPayout.referrer_id == referrer_id)
            .order_by(ReferralPayout.created_at.desc())
            .limit(recent_limit)
        )
    ).scalars().all()

    return {
        "code": user.referral_code,
        "total_referrals": total_referrals,
        "active_referrals": active,
        "tier": tier_name(active, user.referral_rate_override),
        "rate": rate,
        "rate_override": user.referral_rate_override,
        "earned_total": earned,
        "paid_total": paid,
        "balance": bal,
        "recent_earnings": [
            {
                "id": e.id,
                "referred_user_id": e.referred_user_id,
                "payment_id": e.payment_id,
                "amount_usd": e.amount_usd,
                "rate": e.rate,
                "created_at": e.created_at.isoformat(),
            }
            for e in earnings_rows
        ],
        "payouts": [
            {
                "id": p.id,
                "amount_usd": p.amount_usd,
                "status": p.status,
                "address": p.address,
                "note": p.note,
                "created_at": p.created_at.isoformat(),
                "paid_at": p.paid_at.isoformat() if p.paid_at else None,
            }
            for p in payout_rows
        ],
    }
