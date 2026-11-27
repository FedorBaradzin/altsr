"""Реферальная программа: ставки, привязка, начисления, баланс.

Тесты не требуют eth_account — работают с сервисом поверх sqlite-фикстуры `session`.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models import Payment, ReferralEarning, ReferralPayout, User
from app.referral import service as svc
from app.referral.rate import (
    OVERRIDE_MAX_RATE,
    OVERRIDE_MIN_RATE,
    auto_rate,
    clamp_override,
    effective_rate,
    tier_name,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _mk_user(session, subject: str, **kw) -> User:
    u = User(auth_method="wallet", subject=subject, tier="free",
             created_at=_utcnow(), last_login_at=_utcnow(), **kw)
    session.add(u)
    await session.flush()
    return u


async def _mk_paid_payment(session, user: User, tier: str = "pro",
                           status: str = "finished") -> Payment:
    p = Payment(user_id=user.id, tier=tier, provider="nowpayments",
                amount_usd=49.0, status=status,
                created_at=_utcnow(), updated_at=_utcnow())
    session.add(p)
    await session.flush()
    return p


# ---------------- Чистая логика ставок ----------------

def test_auto_rate_all_tiers():
    assert auto_rate(0) == 0.0
    assert auto_rate(1) == 0.10
    assert auto_rate(4) == 0.10
    assert auto_rate(5) == 0.15
    assert auto_rate(9) == 0.15
    assert auto_rate(10) == 0.20
    assert auto_rate(24) == 0.20
    assert auto_rate(25) == 0.30
    assert auto_rate(1000) == 0.30  # авто-потолок 30%


def test_auto_rate_never_exceeds_cap():
    for n in range(0, 500):
        assert auto_rate(n) <= 0.30


def test_clamp_override():
    assert clamp_override(0.10) == OVERRIDE_MIN_RATE  # ниже коридора → 0.30
    assert clamp_override(0.30) == 0.30
    assert clamp_override(0.42) == 0.42
    assert clamp_override(0.50) == 0.50
    assert clamp_override(0.99) == OVERRIDE_MAX_RATE  # выше коридора → 0.50


def test_effective_rate_override_wins_and_clamped():
    # Без override → авто-ставка.
    assert effective_rate(None, 1) == 0.10
    assert effective_rate(None, 25) == 0.30
    # Override зажимается в 0.30–0.50 вне зависимости от числа рефералов.
    assert effective_rate(0.45, 0) == 0.45
    assert effective_rate(0.80, 0) == 0.50
    assert effective_rate(0.05, 100) == 0.30


def test_tier_name():
    assert tier_name(0) == "None"
    assert tier_name(1) == "Starter"
    assert tier_name(5) == "Bronze"
    assert tier_name(10) == "Silver"
    assert tier_name(25) == "Gold"
    assert tier_name(3, override=0.40) == "Individual"


def test_gen_code_shape():
    code = svc.gen_code()
    assert len(code) == 8
    assert all(c in "23456789ABCDEFGHJKMNPQRSTUVWXYZ" for c in code)
    assert svc.gen_code() != svc.gen_code()  # практически всегда различны


# ---------------- ensure_code ----------------

async def test_ensure_code_assigns_and_is_stable(session):
    u = await _mk_user(session, "0xaaa")
    assert u.referral_code is None
    code1 = await svc.ensure_code(session, u)
    assert code1 and u.referral_code == code1
    code2 = await svc.ensure_code(session, u)
    assert code2 == code1  # повторный вызов не меняет код


# ---------------- attach_referrer ----------------

async def test_attach_referrer_happy_path(session):
    ref = await _mk_user(session, "0xref")
    await svc.ensure_code(session, ref)
    new = await _mk_user(session, "0xnew")
    ok = await svc.attach_referrer(session, new, ref.referral_code)
    assert ok is True
    assert new.referred_by_id == ref.id


async def test_attach_referrer_case_insensitive(session):
    ref = await _mk_user(session, "0xref2")
    code = await svc.ensure_code(session, ref)
    new = await _mk_user(session, "0xnew2")
    ok = await svc.attach_referrer(session, new, code.lower())
    assert ok is True
    assert new.referred_by_id == ref.id


async def test_attach_referrer_self_ignored(session):
    u = await _mk_user(session, "0xself")
    code = await svc.ensure_code(session, u)
    ok = await svc.attach_referrer(session, u, code)
    assert ok is False
    assert u.referred_by_id is None


async def test_attach_referrer_missing_code_ignored(session):
    new = await _mk_user(session, "0xnew3")
    assert await svc.attach_referrer(session, new, None) is False
    assert await svc.attach_referrer(session, new, "") is False
    assert await svc.attach_referrer(session, new, "NOPECODE") is False
    assert new.referred_by_id is None


async def test_attach_referrer_not_overwritten(session):
    ref1 = await _mk_user(session, "0xr1")
    c1 = await svc.ensure_code(session, ref1)
    ref2 = await _mk_user(session, "0xr2")
    c2 = await svc.ensure_code(session, ref2)
    new = await _mk_user(session, "0xn")
    assert await svc.attach_referrer(session, new, c1) is True
    # Повторная привязка игнорируется — первый реферер остаётся.
    assert await svc.attach_referrer(session, new, c2) is False
    assert new.referred_by_id == ref1.id


# ---------------- active_referrals ----------------

async def test_active_referrals_counts_distinct_paid(session):
    ref = await _mk_user(session, "0xcount")
    # 2 оплаченных, 1 только waiting, 1 без платежа.
    paid1 = await _mk_user(session, "0xp1", referred_by_id=ref.id)
    paid2 = await _mk_user(session, "0xp2", referred_by_id=ref.id)
    waiting = await _mk_user(session, "0xw", referred_by_id=ref.id)
    _none = await _mk_user(session, "0xz", referred_by_id=ref.id)
    await _mk_paid_payment(session, paid1, status="finished")
    await _mk_paid_payment(session, paid1, status="confirmed")  # второй платёж того же — не удваивает
    await _mk_paid_payment(session, paid2, status="sending")
    await _mk_paid_payment(session, waiting, status="waiting")
    await session.flush()
    assert await svc.active_referrals(session, ref.id) == 2


# ---------------- credit_referral ----------------

async def test_credit_referral_amount(session):
    ref = await _mk_user(session, "0xcr")
    referred = await _mk_user(session, "0xcrd", referred_by_id=ref.id)
    pay = await _mk_paid_payment(session, referred, tier="pro", status="finished")
    earning = await svc.credit_referral(session, referred, pay)
    assert earning is not None
    # active=1 → Starter 10%; 49 * 0.10 = 4.9
    assert earning.rate == 0.10
    assert earning.amount_usd == pytest.approx(4.9)
    assert earning.referrer_id == ref.id
    assert earning.referred_user_id == referred.id


async def test_credit_referral_idempotent(session):
    ref = await _mk_user(session, "0xid")
    referred = await _mk_user(session, "0xidd", referred_by_id=ref.id)
    pay = await _mk_paid_payment(session, referred, status="finished")
    e1 = await svc.credit_referral(session, referred, pay)
    e2 = await svc.credit_referral(session, referred, pay)  # повторный IPN
    assert e1.id == e2.id
    total = await svc._count(session, ReferralEarning, ReferralEarning.payment_id == pay.id)
    assert total == 1


async def test_credit_referral_respects_override(session):
    ref = await _mk_user(session, "0xov", referral_rate_override=0.40)
    referred = await _mk_user(session, "0xovd", referred_by_id=ref.id)
    pay = await _mk_paid_payment(session, referred, tier="pro", status="finished")
    earning = await svc.credit_referral(session, referred, pay)
    assert earning.rate == 0.40
    assert earning.amount_usd == pytest.approx(49.0 * 0.40)


async def test_credit_referral_no_referrer_noop(session):
    orphan = await _mk_user(session, "0xorph")  # referred_by_id is None
    pay = await _mk_paid_payment(session, orphan, status="finished")
    assert await svc.credit_referral(session, orphan, pay) is None


# ---------------- balance / stats ----------------

async def test_balance_math(session):
    ref = await _mk_user(session, "0xbal")
    # Два начисления: 10 + 10 = 20 заработано.
    for amt in (10.0, 10.0):
        session.add(ReferralEarning(referrer_id=ref.id, referred_user_id=ref.id,
                                    payment_id=None, amount_usd=amt, rate=0.10,
                                    created_at=_utcnow()))
    await session.flush()
    assert await svc.earned_total(session, ref.id) == pytest.approx(20.0)
    assert await svc.balance(session, ref.id) == pytest.approx(20.0)

    # pending выплата 5 → баланс 15.
    session.add(ReferralPayout(referrer_id=ref.id, amount_usd=5.0, status="pending",
                               created_at=_utcnow()))
    await session.flush()
    assert await svc.balance(session, ref.id) == pytest.approx(15.0)

    # rejected 100 → игнорируется, баланс всё ещё 15.
    session.add(ReferralPayout(referrer_id=ref.id, amount_usd=100.0, status="rejected",
                               created_at=_utcnow()))
    await session.flush()
    assert await svc.balance(session, ref.id) == pytest.approx(15.0)

    # paid 10 → баланс 5; paid_total=10.
    session.add(ReferralPayout(referrer_id=ref.id, amount_usd=10.0, status="paid",
                               created_at=_utcnow()))
    await session.flush()
    assert await svc.balance(session, ref.id) == pytest.approx(5.0)
    assert await svc.paid_total(session, ref.id) == pytest.approx(10.0)


async def test_balance_never_negative(session):
    ref = await _mk_user(session, "0xneg")
    session.add(ReferralEarning(referrer_id=ref.id, referred_user_id=ref.id,
                                payment_id=None, amount_usd=5.0, rate=0.10,
                                created_at=_utcnow()))
    session.add(ReferralPayout(referrer_id=ref.id, amount_usd=50.0, status="paid",
                               created_at=_utcnow()))
    await session.flush()
    assert await svc.balance(session, ref.id) == 0.0


async def test_stats_shape(session):
    ref = await _mk_user(session, "0xstat")
    await svc.ensure_code(session, ref)
    referred = await _mk_user(session, "0xstatd", referred_by_id=ref.id)
    pay = await _mk_paid_payment(session, referred, status="finished")
    await svc.credit_referral(session, referred, pay)
    data = await svc.stats(session, ref)
    assert data["code"] == ref.referral_code
    assert data["total_referrals"] == 1
    assert data["active_referrals"] == 1
    assert data["tier"] == "Starter"
    assert data["rate"] == 0.10
    assert data["earned_total"] == pytest.approx(4.9)
    assert data["balance"] == pytest.approx(4.9)
    assert len(data["recent_earnings"]) == 1
    assert data["payouts"] == []
