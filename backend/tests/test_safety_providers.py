"""Парсинг ответов safety-провайдеров в SafetyFindings."""
from __future__ import annotations

from app.safety import goplus, honeypot_is, rugcheck
from app.safety.scoring import evaluate

from .conftest import load_fixture


def test_goplus_evm_clean_parse_and_pass():
    data = load_fixture("goplus_evm_clean.json")["result"]["0xtokenabc"]
    f = goplus.parse_evm("0xTOKENabc", data)
    assert f.is_honeypot is False
    assert f.sell_tax == 0.03
    assert f.is_open_source is True
    assert f.mint_authority_active is False
    assert f.lp_locked is True
    assert abs(f.top_holder_pct - 0.08) < 1e-9
    assert f.holder_count == 742
    assert evaluate(f).verdict == "PASS"


def test_goplus_evm_honeypot_parse_and_block():
    data = load_fixture("goplus_evm_honeypot.json")["result"]["0xscambbb"]
    f = goplus.parse_evm("0xSCAMbbb", data)
    assert f.is_honeypot is True
    assert f.sell_tax == 0.99
    assert f.mint_authority_active is True
    assert f.lp_locked is False
    r = evaluate(f)
    assert r.verdict == "BLOCK"
    assert r.risk_score >= 90


def test_rugcheck_clean_parse():
    data = load_fixture("rugcheck_report_clean.json")
    f = rugcheck.parse_report("So11111SolMintAAA", data)
    assert f.chain == "solana"
    assert f.mint_authority_active is False
    assert f.freeze_authority_active is False
    assert f.rugged is False
    assert f.lp_locked is True
    assert abs(f.top_holder_pct - 0.042) < 1e-9
    assert f.holder_count == 410
    assert evaluate(f).verdict == "PASS"


def test_honeypot_is_parse():
    data = load_fixture("honeypot_is_clean.json")
    f = honeypot_is.parse("0xTOKENabc", data)
    assert f.is_honeypot is False
    assert abs(f.buy_tax - 0.01) < 1e-9
    assert abs(f.sell_tax - 0.03) < 1e-9


def test_merge_combines_sources():
    gp = goplus.parse_evm("0xabc", load_fixture("goplus_evm_clean.json")["result"]["0xtokenabc"])
    hp = honeypot_is.parse("0xabc", load_fixture("honeypot_is_clean.json"))
    # honeypot.is добавляет независимое подтверждение is_honeypot/налогов.
    gp.is_honeypot = None  # представим, что GoPlus не дал honeypot
    merged = gp.merge(hp)
    assert merged.is_honeypot is False
    assert "goplus" in merged.sources and "honeypot.is" in merged.sources
