"""Явные сигналы «вредоносный/скам» (parity с GeckoTerminal/Coinbase).

GoPlus отдаёт флаги is_airdrop_scam / honeypot_with_same_creator / cannot_sell_all /
fake_token — мы обязаны их читать и помечать токен как скам (BLOCK + is_malicious).
"""
from __future__ import annotations

import pytest

from app.safety.base import SafetyFindings
from app.safety.goplus import parse_evm
from app.safety.scoring import evaluate


def _clean() -> dict:
    """Чистый по остальным признакам токен (чтобы изолировать проверяемый флаг)."""
    return SafetyFindings(
        chain="bsc", address="0xabc",
        is_honeypot=False, sell_tax=0.0, buy_tax=0.0, mint_authority_active=False,
        top_holder_pct=0.1, lp_locked=True, holder_count=500, is_open_source=True,
    )


@pytest.mark.parametrize("field,code", [
    ("is_airdrop_scam", "airdrop_scam"),
    ("honeypot_same_creator", "honeypot_same_creator"),
    ("cannot_sell_all", "cannot_sell_all"),
    ("is_fake_token", "fake_token"),
])
def test_explicit_scam_signal_blocks_and_marks_malicious(field, code):
    f = _clean()
    setattr(f, field, True)
    r = evaluate(f)
    assert r.verdict == "BLOCK"
    assert r.is_malicious is True
    assert any(fl.code == code for fl in r.red_flags)


def test_tax_modifiable_adds_soft_risk_not_auto_block():
    f = _clean()
    f.tax_modifiable = True
    r = evaluate(f)
    assert any(fl.code == "tax_modifiable" for fl in r.red_flags)
    assert r.is_malicious is False  # риск, но не явный скам


def test_clean_token_still_passes_and_not_malicious():
    r = evaluate(_clean())
    assert r.verdict == "PASS"
    assert r.is_malicious is False


def test_goplus_parses_scam_fields():
    data = {
        "is_honeypot": "0",
        "is_airdrop_scam": "1",
        "honeypot_with_same_creator": "1",
        "cannot_sell_all": "1",
        "cannot_buy": "0",
        "fake_token": {"value": 1, "true_token_address": "0xreal"},
        "slippage_modifiable": "1",
        "trading_cooldown": "0",
    }
    f = parse_evm("0xABC", data)
    assert f.is_airdrop_scam is True
    assert f.honeypot_same_creator is True
    assert f.cannot_sell_all is True
    assert f.is_fake_token is True
    assert f.tax_modifiable is True
    # И итоговый вердикт — скам.
    assert evaluate(f).is_malicious is True


def test_fake_token_flat_and_absent():
    assert parse_evm("0x1", {"fake_token": 1}).is_fake_token is True
    assert parse_evm("0x1", {}).is_fake_token is None
