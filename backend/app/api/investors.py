"""Инвест-лендинг: приём заявок инвесторов + админ-список.

POST /api/investors/submit — публичный, с валидацией, антиспамом (honeypot +
rate-limit по IP) и best-effort уведомлением админа в Telegram.
GET  /api/admin/investors — список/экспорт, только для админа.
"""
from __future__ import annotations

import csv
import io
import re
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.service import require_admin
from ..config import Settings, get_settings
from ..db import get_session
from ..models import InvestorLead
from ..schemas import InvestorLeadIn

router = APIRouter(prefix="/api/investors", tags=["investors"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin-investors"], dependencies=[Depends(require_admin)])

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# простой in-memory rate-limit: не более N заявок с одного IP за окно.
_HITS: dict[str, list[float]] = {}
_WINDOW = 3600.0
_MAX = 6


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for") or ""
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "?")[:64]


def _rate_ok(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _HITS.get(ip, []) if now - t < _WINDOW]
    hits.append(now)
    _HITS[ip] = hits
    return len(hits) <= _MAX


@router.post("/submit")
async def submit(
    body: InvestorLeadIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    # honeypot: боты заполняют скрытое поле
    if (body.hp or "").strip():
        return {"ok": True}  # тихо игнорируем
    name = (body.name or "").strip()[:128]
    email = (body.email or "").strip()[:190]
    if not name or not _EMAIL.match(email):
        raise HTTPException(status_code=400, detail="Укажите имя и корректный email")
    if not body.consent:
        raise HTTPException(status_code=400, detail="Требуется согласие на обработку данных")
    ip = _client_ip(request)
    if not _rate_ok(ip):
        raise HTTPException(status_code=429, detail="Слишком много заявок, попробуйте позже")

    valuation = None
    if body.amountNum > 0 and body.equityNum > 0:
        valuation = round(body.amountNum / (body.equityNum / 100.0), 2)

    lead = InvestorLead(
        name=name, email=email, telegram=(body.telegram or "").strip()[:128],
        note=(body.note or "").strip()[:2000] or None,
        amount=(body.amount or "")[:64], amount_num=body.amountNum or None,
        equity=(body.equity or "")[:64], equity_num=body.equityNum or None,
        valuation=valuation, inv_type=(body.type or "")[:64],
        utm_source=(body.utm_source or "")[:190] or None,
        utm_medium=(body.utm_medium or "")[:190] or None,
        utm_campaign=(body.utm_campaign or "")[:190] or None,
        utm_content=(body.utm_content or "")[:190] or None,
        ip=ip,
    )
    session.add(lead)
    await session.commit()
    await session.refresh(lead)

    # best-effort уведомление админа
    try:
        if settings.telegram_bot_token and settings.telegram_admin_chat_id:
            from ..discovery.base import HttpClient
            from ..notify.telegram import send_to_chat
            val = f"${valuation:,.0f} post-money" if valuation else "—"
            text = (
                "💸 Новая заявка инвестора\n"
                f"Сумма: {lead.amount or '—'} · Доля: {lead.equity or '—'}\n"
                f"Оценка: {val}\n"
                f"Тип: {lead.inv_type or '—'}\n"
                f"{name} · {email} · {lead.telegram or '—'}\n"
                f"UTM: {lead.utm_source or '—'}/{lead.utm_campaign or '—'}"
            )
            async with HttpClient(timeout=8, max_retries=1) as http:
                await send_to_chat(settings, settings.telegram_admin_chat_id, text, http=http)
    except Exception:  # noqa: BLE001 — уведомление не должно ронять приём заявки
        pass

    return {"ok": True, "id": lead.id}


@admin_router.get("/investors")
async def list_investors(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(200, ge=1, le=1000),
    status: str = Query(""),
    export: str = Query(""),
) -> object:
    q = select(InvestorLead).order_by(InvestorLead.created_at.desc())
    if status:
        q = q.where(InvestorLead.status == status)
    rows = (await session.execute(q.limit(limit))).scalars().all()

    def row(x: InvestorLead) -> dict:
        return {
            "id": x.id, "name": x.name, "email": x.email, "telegram": x.telegram,
            "amount": x.amount, "equity": x.equity, "valuation": x.valuation,
            "type": x.inv_type, "status": x.status, "note": x.note,
            "utm_source": x.utm_source, "utm_campaign": x.utm_campaign,
            "created_at": x.created_at.isoformat(),
        }

    if export == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "created_at", "name", "email", "telegram", "amount", "equity",
                    "valuation", "type", "status", "utm_source", "utm_campaign", "note"])
        for x in rows:
            w.writerow([x.id, x.created_at.isoformat(), x.name, x.email, x.telegram, x.amount,
                        x.equity, x.valuation, x.inv_type, x.status, x.utm_source, x.utm_campaign, x.note])
        buf.seek(0)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d")
        return StreamingResponse(
            iter([buf.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=investor_leads_{ts}.csv"},
        )

    return [row(x) for x in rows]


@admin_router.post("/investors/{lead_id}/status")
async def set_status(
    lead_id: int,
    session: AsyncSession = Depends(get_session),
    value: str = Query(...),
) -> dict:
    allowed = {"new", "contacted", "qualified", "negotiating", "closed"}
    if value not in allowed:
        raise HTTPException(status_code=400, detail="Неизвестный статус")
    lead = (await session.execute(select(InvestorLead).where(InvestorLead.id == lead_id))).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    lead.status = value
    await session.commit()
    return {"ok": True, "id": lead_id, "status": value}
