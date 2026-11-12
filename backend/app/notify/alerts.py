"""Системные алерты о поломках платформы → Telegram.

Отдельно от торговых BUY-алертов: здесь — эксплуатационные инциденты (упал воркер,
исчерпаны кредиты провайдера, сработал kill switch, расхождение балансов и т.п.).

Дедуп через Redis (SET NX EX): один и тот же код алерта не шлётся повторно в течение
окна dedup_seconds — чтобы инцидент не превращался в поток одинаковых сообщений.
Без Redis дедупа нет (шлём каждый раз). Без настроенного Telegram — тихий no-op.
"""
from __future__ import annotations

import logging

from ..config import Settings
from ..discovery.base import HttpClient
from .telegram import TelegramNotifier

logger = logging.getLogger("altsr.notify.alerts")

_SEVERITY_EMOJI = {"info": "ℹ️", "warning": "⚠️", "error": "🛑", "critical": "🚨"}


def format_blocked_scam_alert(
    chain: str,
    address: str,
    symbol: str | None,
    verdict: str,
    red_flag_codes: list[str],
    *,
    malicious: bool,
) -> str:
    """Алерт: свежая перепроверка поймала скам ПЕРЕД отправкой сигнала в Telegram."""
    tag = "🚫 malicious" if malicious else f"вердикт {_esc(verdict)}"
    title = _esc(symbol) if symbol else _esc(address[:10] + "…")
    flags = ", ".join(_esc(c) for c in red_flag_codes[:6]) if red_flag_codes else "—"
    return (
        "🛡️ <b>ALTSR · скам пойман перед отправкой</b>\n"
        f"Токен <b>{title}</b> ({_esc(chain)}) не ушёл в канал сигналов.\n"
        f"Свежая проверка: {tag}\n"
        f"Флаги: {flags}\n"
        f"<code>{_esc(address)}</code>"
    )


def format_system_alert(code: str, message: str, severity: str = "error") -> str:
    emoji = _SEVERITY_EMOJI.get(severity, "🛑")
    return (
        f"{emoji} <b>ALTSR · системный алерт</b>\n"
        f"Код: <code>{_esc(code)}</code> · {_esc(severity)}\n"
        f"{_esc(message)}"
    )


class SystemAlerter:
    def __init__(self, settings: Settings, *, redis=None) -> None:
        self.settings = settings
        self.redis = redis
        self.notifier = TelegramNotifier(settings)

    async def _should_send(self, code: str, dedup_seconds: int) -> bool:
        """True, если алерт с этим кодом ещё не слался в окне дедупа."""
        if self.redis is None or dedup_seconds <= 0:
            return True
        key = f"altsr:alert:{code}"
        try:
            was_set = await self.redis.set(key, "1", nx=True, ex=dedup_seconds)
        except Exception as exc:  # noqa: BLE001 — дедуп не должен ронять алерт
            logger.warning("Дедуп алерта недоступен (%s) — шлём без дедупа", exc)
            return True
        return bool(was_set)

    async def alert(
        self,
        code: str,
        message: str,
        *,
        severity: str = "error",
        dedup_seconds: int = 3600,
        http: HttpClient | None = None,
    ) -> bool:
        """Отправить системный алерт. Возвращает True, если сообщение ушло в Telegram."""
        if not await self._should_send(code, dedup_seconds):
            logger.info("Алерт %s подавлён дедупом", code)
            return False
        logger.warning("СИСТЕМНЫЙ АЛЕРТ [%s/%s]: %s", code, severity, message)
        text = format_system_alert(code, message, severity)
        return await self.notifier.send(text, http=http)


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
