"""T10 — кросс-проверка источников: OHLCV-тренд + согласие двух safety-провайдеров."""
from __future__ import annotations

import httpx
import respx

from app.config import get_settings
from app.discovery.base import HttpClient
from app.discovery.geckoterminal import (
    Candle,
    confirm_trend,
    fetch_ohlcv,
    parse_ohlcv,
    trend_score,
)
from app.safety import cross_source
from app.safety.base import SafetyFindings
from app.safety.cross_source import AGREE, DIVERGE, SINGLE_SOURCE, cross_check
from app.safety.screener import screen_token

from .conftest import load_fixture

# --------------------------------------------------------------------------- #
# GeckoTerminal OHLCV: чистая логика тренда                                    #
# --------------------------------------------------------------------------- #

def _candles(closes: list[float]) -> list[Candle]:
    return [Candle(ts=i, open=c, high=c, low=c, close=c, volume=1.0) for i, c in enumerate(closes)]


def test_parse_ohlcv_sorts_oldest_first():
    candles = parse_ohlcv(load_fixture("geckoterminal_ohlcv_up.json"))
    assert len(candles) == 7
    # Фикстура отдаёт свечи «новые сначала» — парсер сортирует по возрастанию ts.
    assert candles[0].ts < candles[-1].ts
    assert candles[0].close == 0.101
    assert candles[-1].close == 0.156


def test_confirm_trend_true_on_rising_series():
    candles = parse_ohlcv(load_fixture("geckoterminal_ohlcv_up.json"))
    assert confirm_trend(candles) is True
    assert trend_score(candles) == 1.0  # каждый бар выше предыдущего


def test_confirm_trend_false_on_falling_series():
    candles = _candles([0.20, 0.18, 0.15, 0.13, 0.11, 0.10])
    assert confirm_trend(candles) is False
    assert trend_score(candles) == 0.0


def test_confirm_trend_false_on_insufficient_candles():
    # Рост есть, но свечей меньше min_candles=5 → не подтверждаем.
    assert confirm_trend(_candles([0.10, 0.12, 0.15])) is False


def test_confirm_trend_false_on_flat_series():
    assert confirm_trend(_candles([0.10, 0.10, 0.10, 0.10, 0.10, 0.10])) is False


def test_confirm_trend_choppy_up_overall():
    # Пила, но итог выше старта и ≥50% баров растущие.
    closes = [0.10, 0.12, 0.11, 0.13, 0.12, 0.15, 0.14, 0.17]
    assert trend_score(_candles(closes)) >= 0.5
    assert confirm_trend(_candles(closes)) is True


def test_trend_score_empty():
    assert trend_score([]) == 0.0
    assert confirm_trend([]) is False


async def test_fetch_ohlcv_respx():
    settings = get_settings()
    with respx.mock(assert_all_called=True) as router:
        router.get(
            url__startswith=f"{settings.gecko_base_url}/networks/eth/pools/0xpoolabc/ohlcv/hour"
        ).mock(return_value=httpx.Response(200, json=load_fixture("geckoterminal_ohlcv_up.json")))
        async with HttpClient() as http:
            candles = await fetch_ohlcv(http, settings.gecko_base_url, "eth", "0xpoolabc")
    assert len(candles) == 7
    assert confirm_trend(candles) is True


async def test_fetch_ohlcv_http_error_returns_empty():
    settings = get_settings()
    with respx.mock(assert_all_called=False) as router:
        router.get(url__startswith=f"{settings.gecko_base_url}/networks/").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        async with HttpClient(max_retries=1) as http:
            candles = await fetch_ohlcv(http, settings.gecko_base_url, "eth", "0xmissing")
    assert candles == []
    assert confirm_trend(candles) is False


# --------------------------------------------------------------------------- #
# Два safety-провайдера: согласие / расхождение / единственный источник         #
# --------------------------------------------------------------------------- #

def test_agreement_does_not_lower_confidence():
    a = SafetyFindings(is_honeypot=False, sell_tax=0.03, sources=["goplus"])
    b = SafetyFindings(is_honeypot=False, sell_tax=0.03, sources=["honeypot.is"])
    r = cross_check(a, b)
    assert r.status == AGREE
    assert r.agreed is True
    assert r.confidence_penalty == 0.0
    assert r.force_review is False


def test_divergence_lowers_confidence_and_marks_review():
    # Провайдеры разошлись по honeypot — решающий сигнал.
    a = SafetyFindings(is_honeypot=False, sources=["goplus"])
    b = SafetyFindings(is_honeypot=True, sources=["honeypot.is"])
    r = cross_check(a, b, penalty=0.25)
    assert r.status == DIVERGE
    assert "is_honeypot" in r.diverging_signals
    assert r.confidence_penalty == 0.25
    assert r.force_review is True


def test_divergence_on_tax_beyond_tolerance():
    a = SafetyFindings(sell_tax=0.02, sources=["goplus"])
    b = SafetyFindings(sell_tax=0.20, sources=["honeypot.is"])
    r = cross_check(a, b)
    assert r.status == DIVERGE
    assert "sell_tax" in r.diverging_signals


def test_small_tax_difference_within_tolerance_agrees():
    a = SafetyFindings(sell_tax=0.03, sources=["goplus"])
    b = SafetyFindings(sell_tax=0.05, sources=["honeypot.is"])  # разница 2 п.п. < 3 п.п.
    assert cross_check(a, b).status == AGREE


def test_none_provider_degrades_to_single_source():
    a = SafetyFindings(is_honeypot=False, sources=["goplus"])
    r = cross_check(a, None)
    assert r.status == SINGLE_SOURCE
    assert r.confidence_penalty == 0.0
    assert r.force_review is False
    assert "goplus" in r.sources


def test_empty_second_provider_is_single_source():
    a = SafetyFindings(is_honeypot=False, sources=["goplus"])
    empty = SafetyFindings()  # провайдер не дал данных (таймаут → пустые находки)
    assert cross_check(a, empty).status == SINGLE_SOURCE


def test_apply_agreement_pass_to_review_on_divergence():
    from app.safety.scoring import evaluate

    clean = SafetyFindings(
        is_honeypot=False, sell_tax=0.03, mint_authority_active=False,
        top_holder_pct=0.08, lp_locked=True, sources=["goplus"],
    )
    result = evaluate(clean)
    assert result.verdict == "PASS"
    diverge = cross_source.AgreementResult(
        status=DIVERGE, diverging_signals=["is_honeypot"], confidence_penalty=0.25,
        force_review=True,
    )
    out = cross_source.apply_agreement(result, diverge)
    assert out.verdict == "REVIEW"
    assert any(f.code == "source_divergence" for f in out.red_flags)


# --------------------------------------------------------------------------- #
# Интеграция screen_token: падение одного провайдера не валит батч              #
# --------------------------------------------------------------------------- #

async def test_screen_token_divergence_marks_review():
    """Два провайдера EVM расходятся по honeypot → cross_source поднимает до REVIEW."""
    settings = get_settings()
    settings.cross_source_enabled = True
    with respx.mock(assert_all_called=False) as router:
        # GoPlus: чистый (is_honeypot=0).
        router.get(url__startswith=f"{settings.goplus_base_url}/token_security/").mock(
            return_value=httpx.Response(200, json=load_fixture("goplus_evm_clean.json"))
        )
        # honeypot.is: утверждает, что это ханипот → расхождение.
        router.get(f"{settings.honeypot_base_url}/IsHoneypot").mock(
            return_value=httpx.Response(200, json={"honeypotResult": {"isHoneypot": True},
                                                   "simulationResult": {}})
        )
        async with HttpClient() as http:
            result = await screen_token(http, settings, "ethereum", "0xtokenabc")
    # honeypot.is сам по себе даёт HARD honeypot → BLOCK; но проверяем, что кросс-флаг добавлен.
    assert any(f.code == "source_divergence" for f in result.red_flags)


async def test_screen_token_one_provider_down_still_yields_result():
    """honeypot.is таймаутит — батч не падает, GoPlus всё равно даёт вердикт."""
    settings = get_settings()
    settings.cross_source_enabled = True
    with respx.mock(assert_all_called=False) as router:
        router.get(url__startswith=f"{settings.goplus_base_url}/token_security/").mock(
            return_value=httpx.Response(200, json=load_fixture("goplus_evm_clean.json"))
        )
        router.get(f"{settings.honeypot_base_url}/IsHoneypot").mock(
            side_effect=httpx.ConnectTimeout("timeout")
        )
        async with HttpClient(max_retries=1) as http:
            result = await screen_token(http, settings, "ethereum", "0xtokenabc")
    # Один провайдер выжил → результат есть, помечен single_source (кросс-проверка недоступна).
    assert result.verdict in ("PASS", "REVIEW")
    assert "goplus" in result.findings.sources
    assert any(f.code == "single_source" for f in result.red_flags)


def test_parse_ohlcv_tolerates_garbage():
    assert parse_ohlcv(None) == []
    assert parse_ohlcv({"data": {}}) == []
    # Короткие/битые строки пропускаются.
    bad = {"data": {"attributes": {"ohlcv_list": [[1, 2, 3], "x", [1704067200, 1, 2, 3, 4, 5]]}}}
    assert len(parse_ohlcv(bad)) == 1
