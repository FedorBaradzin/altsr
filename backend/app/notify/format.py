"""Форматирование сообщений уведомлений."""
from __future__ import annotations

from ..signals.venues import BuyOption

DISCLAIMER = (
    "⚠️ Не инвест-рекомендация. Крайне высокий риск полной потери средств. "
    "~98% новых токенов обнуляются. Это скрининг, не прогноз прибыли."
)


def format_buy_alert(
    *,
    chain: str,
    address: str,
    symbol: str | None,
    name: str | None,
    confidence: float,
    risk_score: int | None,
    reasons: list[str],
    liquidity_usd: float | None,
    buy_options: list[BuyOption],
    plan: list[str] | None = None,
) -> str:
    """HTML-сообщение Telegram: сигнал + «как купить» + дисклеймер."""
    title = symbol or name or address[:12]
    lines = [
        f"🟢 <b>BUY-сигнал</b> · <b>{_esc(title)}</b> ({chain})",
        f"Уверенность: {confidence:.0%}"
        + (f" · risk {risk_score}" if risk_score is not None else "")
        + (f" · ликв. ${liquidity_usd:,.0f}" if liquidity_usd else ""),
        f"<code>{_esc(address)}</code>",
    ]
    if reasons:
        lines.append("Почему прошёл: " + "; ".join(_esc(r) for r in reasons))

    if buy_options:
        lines.append("")
        lines.append("<b>Где и как купить:</b>")
        for o in buy_options:
            note = f" — {_esc(o.note)}" if o.note else ""
            lines.append(f"• {_esc(o.name)}: {_esc(o.url)}{note}")

    if plan:
        lines.append("")
        lines.append("<b>План по позиции</b> (не прогноз прибыли):")
        for p in plan:
            lines.append(f"• {_esc(p)}")

    lines.append("")
    lines.append(f"<i>{DISCLAIMER}</i>")
    return "\n".join(lines)


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
