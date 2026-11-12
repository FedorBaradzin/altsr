"""GeckoTerminal gt_score как доп. safety-сигнал (та же репутация, что рисует
плашку «Отмечен как скам-токен»). Низкий балл → soft-риск (REVIEW), не BLOCK.
'Нет данных' не меняет вердикт.
"""
from __future__ import annotations

from app.safety.base import SafetyFindings
from app.safety.geckoterminal_info import parse_token_info
from app.safety.scoring import evaluate


def _info(score):
    return {"data": {"attributes": {"gt_score": score}}}


def test_parse_reads_gt_score():
    f = parse_token_info("0xabc", _info(72.5), chain="ethereum")
    assert f.reputation_score == 72.5
    assert "geckoterminal" in f.sources


def test_parse_missing_or_garbage_is_none():
    assert parse_token_info("0x1", {}, "ethereum").reputation_score is None
    assert parse_token_info("0x1", {"data": {"attributes": {}}}, "e").reputation_score is None
    assert parse_token_info("0x1", {"data": {"attributes": {"gt_score": "x"}}},
                            "e").reputation_score is None
    # Вне диапазона 0..100 — мусор, отбрасываем.
    assert parse_token_info("0x1", {"data": {"attributes": {"gt_score": 250}}},
                            "e").reputation_score is None


def _clean() -> SafetyFindings:
    return SafetyFindings(
        chain="ethereum", address="0xabc",
        is_honeypot=False, sell_tax=0.0, buy_tax=0.0, mint_authority_active=False,
        top_holder_pct=0.1, lp_locked=True, holder_count=500, is_open_source=True,
    )


def test_low_score_adds_soft_risk_but_alone_not_decisive():
    """Низкий gt_score — soft-вклад в риск; сам по себе не рубит PASS (молодые
    легитимные токены часто имеют низкий балл), но повышает risk_score."""
    f = _clean()
    f.reputation_score = 12.0
    r = evaluate(f, gecko_min_score=35.0)
    assert any(fl.code == "low_reputation" for fl in r.red_flags)
    assert r.risk_score >= 25
    assert r.verdict == "PASS"        # один soft < порога REVIEW
    assert r.is_malicious is False


def test_low_score_plus_other_soft_tips_to_review():
    """В связке с другим soft-сигналом низкая репутация уводит токен в REVIEW."""
    f = _clean()
    f.reputation_score = 12.0
    f.freeze_authority_active = True   # +20 soft
    r = evaluate(f, gecko_min_score=35.0)
    assert r.verdict == "REVIEW"       # 25 + 20 ≥ 30
    assert r.is_malicious is False


def test_high_score_keeps_pass():
    f = _clean()
    f.reputation_score = 80.0
    r = evaluate(f, gecko_min_score=35.0)
    assert not any(fl.code == "low_reputation" for fl in r.red_flags)
    assert r.verdict == "PASS"


def test_no_score_does_not_affect_verdict():
    r = evaluate(_clean(), gecko_min_score=35.0)  # reputation_score=None
    assert not any(fl.code == "low_reputation" for fl in r.red_flags)
    assert r.verdict == "PASS"


def test_disabled_when_threshold_none():
    f = _clean()
    f.reputation_score = 5.0
    r = evaluate(f, gecko_min_score=None)  # фича выключена → балл игнорируется
    assert not any(fl.code == "low_reputation" for fl in r.red_flags)
    assert r.verdict == "PASS"
