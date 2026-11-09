"""Скоринг: HARD-BLOCK правила, SOFT-FLAG веса, вердикты, честность на неполных данных."""
from __future__ import annotations

from app.safety.base import SafetyFindings
from app.safety.scoring import evaluate


def _clean_evm(**kw) -> SafetyFindings:
    base = dict(
        chain="ethereum", address="0xabc",
        is_honeypot=False, buy_tax=0.01, sell_tax=0.02, is_open_source=True,
        mint_authority_active=False, owner_can_change_balance=False,
        owner_can_take_ownership=False, can_blacklist=False, is_proxy=False,
        lp_locked=True, lp_locked_pct=0.9, top_holder_pct=0.08, holder_count=500,
        is_true_token=True,
    )
    base.update(kw)
    return SafetyFindings(**base)


def _codes(result):
    return {f.code for f in result.red_flags}


def test_clean_token_passes():
    r = evaluate(_clean_evm())
    assert r.verdict == "PASS"
    assert r.risk_score < 30


def test_honeypot_is_hard_block():
    r = evaluate(_clean_evm(is_honeypot=True))
    assert r.verdict == "BLOCK"
    assert r.risk_score >= 90
    assert "honeypot" in _codes(r)


def test_high_sell_tax_hard_block():
    r = evaluate(_clean_evm(sell_tax=0.30))
    assert r.verdict == "BLOCK"
    assert "sell_tax_extreme" in _codes(r)


def test_mint_authority_hard_block():
    r = evaluate(_clean_evm(mint_authority_active=True))
    assert r.verdict == "BLOCK"
    assert "mint_authority" in _codes(r)


def test_unlocked_lp_hard_block():
    r = evaluate(_clean_evm(lp_locked=False))
    assert r.verdict == "BLOCK"
    assert "lp_unlocked" in _codes(r)


def test_top_holder_over_50_hard_block():
    r = evaluate(_clean_evm(top_holder_pct=0.62))
    assert r.verdict == "BLOCK"
    assert "holder_concentration_extreme" in _codes(r)


def test_owner_change_balance_hard_block():
    r = evaluate(_clean_evm(owner_can_change_balance=True))
    assert r.verdict == "BLOCK"


def test_soft_flags_accumulate_to_review():
    # Не критичные, но вместе → REVIEW.
    r = evaluate(_clean_evm(
        sell_tax=0.10,              # soft 15
        top_holder_pct=0.35,        # soft 20
        is_open_source=False,       # soft 25 → суммарно >=30
    ))
    assert r.verdict in ("REVIEW", "BLOCK")
    assert r.risk_score >= 30
    assert {"sell_tax", "holder_concentration", "unverified_contract"} <= _codes(r)


def test_missing_data_never_passes():
    # Ничего не известно → не PASS.
    r = evaluate(SafetyFindings(chain="ethereum", address="0xabc"))
    assert r.verdict != "PASS"
    assert "insufficient_data" in _codes(r)


def test_solana_freeze_authority_is_soft():
    f = SafetyFindings(
        chain="solana", address="so1", mint_authority_active=False,
        freeze_authority_active=True, rugged=False, lp_locked=True,
        top_holder_pct=0.05, holder_count=300,
    )
    r = evaluate(f)
    assert "freeze_authority" in _codes(r)
    assert r.verdict in ("PASS", "REVIEW")


def test_rugged_hard_block():
    r = evaluate(SafetyFindings(chain="solana", address="so1", rugged=True))
    assert r.verdict == "BLOCK"
