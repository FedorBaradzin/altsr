"""Hard-rules R1–R6 (T4): каждое правило блокирует/пропускает, fail-fast порядок."""
from __future__ import annotations

from app.signals.hard_rules import (
    HardRuleConfig,
    HardRuleInput,
    check_hard_rules,
    social_confidence_boost,
)


def _cfg(**over) -> HardRuleConfig:
    base = dict(min_volume_usd=10_000.0, require_verified=True, sell_buy_max=2.0,
                dev_max_pct=10.0, max_consec_losses=2)
    base.update(over)
    return HardRuleConfig(**base)


def _ok(**over) -> HardRuleInput:
    base = dict(volume_usd=50_000.0, contract_verified=True, buys_m5=20, sells_m5=5,
                dev_pct=3.0, has_bundles=False, repeat_rug=False, consec_losses=0)
    base.update(over)
    return HardRuleInput(**base)


def test_clean_input_passes():
    assert check_hard_rules(_ok(), _cfg()).blocked is False


def test_r1_low_volume_blocks():
    r = check_hard_rules(_ok(volume_usd=1_000.0), _cfg())
    assert r.blocked and r.rule_id == "R1"


def test_r1_missing_volume_fails_closed():
    r = check_hard_rules(_ok(volume_usd=None), _cfg())
    assert r.blocked and r.rule_id == "R1"


def test_r2_unverified_blocks():
    assert check_hard_rules(_ok(contract_verified=False), _cfg()).rule_id == "R2"
    assert check_hard_rules(_ok(contract_verified=None), _cfg()).rule_id == "R2"


def test_r2_disabled_passes_unverified():
    assert not check_hard_rules(
        _ok(contract_verified=False), _cfg(require_verified=False, min_volume_usd=0)
    ).blocked


def test_r3_sell_pressure_blocks():
    r = check_hard_rules(_ok(buys_m5=5, sells_m5=12), _cfg())
    assert r.blocked and r.rule_id == "R3"


def test_r3_few_txns_not_judged():
    # Мало сделок — R3 не срабатывает (остальное чисто).
    assert not check_hard_rules(_ok(buys_m5=1, sells_m5=3), _cfg()).blocked


def test_r4_dev_too_high():
    assert check_hard_rules(_ok(dev_pct=25.0), _cfg()).rule_id == "R4"


def test_r4_bundles_and_repeat_rug():
    assert check_hard_rules(_ok(has_bundles=True), _cfg()).rule_id == "R4"
    assert check_hard_rules(_ok(repeat_rug=True), _cfg()).rule_id == "R4"


def test_r5_consecutive_losses_stop():
    r = check_hard_rules(_ok(consec_losses=2), _cfg())
    assert r.blocked and r.rule_id == "R5"
    assert not check_hard_rules(_ok(consec_losses=1), _cfg()).blocked


def test_fail_fast_order_r1_before_r3():
    # И объём мал (R1), и давление продаж (R3) — вернуться должен R1.
    r = check_hard_rules(_ok(volume_usd=100.0, buys_m5=5, sells_m5=20), _cfg())
    assert r.rule_id == "R1"


def test_r6_social_only_boosts_confidence():
    # R6 не блокирует; соц-сигнал даёт буст в пределах max_boost.
    assert social_confidence_boost(_ok(social_score=1.0), max_boost=0.1) == 0.1
    assert social_confidence_boost(_ok(social_score=0.0)) == 0.0
    assert social_confidence_boost(_ok(social_score=None)) == 0.0


def test_evaluate_entry_hard_rule_rejection_carries_rule_id():
    from app.config import get_settings
    from app.signals.engine import SignalInput, evaluate_entry

    s = get_settings()
    s.momentum_enabled = False
    s.indicators_enabled = False
    s.hard_rules_enabled = True
    s.hr_require_verified = True
    inp = SignalInput(chain="eth", address="0x", liquidity_usd=8000.0,
                      age_minutes=30.0, verdict="PASS", risk_score=10)
    # Неверифицированный контракт → R2, rule_id в rejected.
    d = evaluate_entry(inp, s, hr=HardRuleInput(contract_verified=False))
    assert not d.passed
    assert "[R2]" in d.rejected

    # Без hr — hard-rules не применяются (вход проходит прочие гейты).
    d2 = evaluate_entry(inp, s)
    assert d2.passed
