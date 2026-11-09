"""Рендер рилса: ключевые поля присутствуют, цвет по знаку P&L, экранирование."""
from __future__ import annotations

from app.reels.render import ReelData, render_reel_html


def _d(**kw):
    base = dict(symbol="NEXO", chain="solana", verdict="PASS", risk_score=12,
                status="closed", entry_price=0.0000014, last_price=0.0000021,
                pnl_pct=49.0, pnl_usd=245.0, exit_reason="take-profit 2x + trailing",
                confidence=0.78)
    base.update(kw)
    return ReelData(**base)


def test_reel_contains_core_fields():
    html = render_reel_html(_d())
    assert "$NEXO" in html
    assert "ПОЗИЦИЯ ЗАКРЫТА" in html
    assert "PASS" in html and "risk 12" in html
    assert "take-profit" in html
    assert "бумажная симуляция" in html.lower() or "Бумажная симуляция" in html


def test_profit_is_green_loss_is_red():
    win = render_reel_html(_d(pnl_pct=49.0, pnl_usd=245))
    assert "#34D399" in win
    loss = render_reel_html(_d(pnl_pct=-26.0, pnl_usd=-130, exit_reason="hard stop −25%"))
    assert "#F87171" in loss


def test_open_position_reel():
    html = render_reel_html(_d(status="open", exit_reason=None))
    assert "ОТКРЫТАЯ ПОЗИЦИЯ" in html


def test_html_escaping():
    html = render_reel_html(_d(symbol="<b>X", exit_reason="<script>alert(1)</script>"))
    # Пользовательские данные экранированы, инъекция не проходит.
    assert "&lt;b" in html
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;alert(1)" in html
