"""Скидка 5% приглашённому по реф-ссылке: математика цены, helper и комиссия
реферера от ФАКТИЧЕСКИ уплаченной (сниженной) суммы.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.api.billing import _referred_discount
from app.billing.tiers import apply_discount, tier_price
from app.config import get_settings
from app.models import Payment, User
from app.referral import service as svc


# ------------------------- apply_discount (чистая) ------------------------- #
def test_apply_discount_basic():
    assert apply_discount(49.0, 0.05) == 46.55
    assert apply_discount(89.0, 0.05) == 84.55


def test_apply_discount_zero_is_identity():
    assert apply_discount(49.0, 0.0) == 49.0


def test_apply_discount_clamps():
    assert apply_discount(49.0, -1.0) == 49.0  # отрицательную долю клампим в 0
    assert apply_discount(49.0, 2.0) == 0.0    # >1 клампим в 1 → цена 0


# --------------------------- _referred_discount --------------------------- #
class _U:
    def __init__(self, referred_by_id):
        self.referred_by_id = referred_by_id


def test_referred_discount_helper():
    s = get_settings()
    s.referral_referred_discount_pct = 0.05
    assert _referred_discount(None, s) == 0.0           # гость
    assert _referred_discount(_U(None), s) == 0.0       # не приглашённый
    assert _referred_discount(_U(7), s) == 0.05         # приглашённый → 5%


# ------------------- комиссия от фактически уплаченной --------------------- #
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _mk(session, subject, **kw) -> User:
    u = User(auth_method="wallet", subject=subject, tier="free",
             created_at=_utcnow(), last_login_at=_utcnow(), **kw)
    session.add(u)
    await session.flush()
    return u


async def test_commission_on_discounted_amount(session):
    ref = await _mk(session, "0xdref")
    referred = await _mk(session, "0xdrefd", referred_by_id=ref.id)
    paid = apply_discount(tier_price("pro"), 0.05)  # 49 → 46.55
    pay = Payment(user_id=referred.id, tier="pro", provider="nowpayments",
                  amount_usd=paid, status="finished",
                  created_at=_utcnow(), updated_at=_utcnow())
    session.add(pay)
    await session.flush()
    earning = await svc.credit_referral(session, referred, pay)
    assert earning is not None
    assert earning.rate == 0.10  # Starter (active=1)
    # 10% от фактически уплаченных 46.55 (а не от полной цены 49)
    assert earning.amount_usd == pytest.approx(round(paid * 0.10, 2))
    assert earning.amount_usd < 4.9  # меньше, чем было бы от полной цены
