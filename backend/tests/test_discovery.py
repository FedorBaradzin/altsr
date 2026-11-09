"""Discovery end-to-end на фикстурах: сбор со всех источников → БД, дедуп меж источников."""
from __future__ import annotations

import httpx
import pytest
import respx
from sqlalchemy import func, select

from app.config import get_settings
from app.db import create_all
from app.discovery.base import HttpClient
from app.discovery.runner import collect_once, run_tick
from app.models import Token

from .conftest import load_fixture


def _mock_sources(router: respx.Router, settings):
    router.get(url__startswith=f"{settings.gecko_base_url}/networks/").mock(
        return_value=httpx.Response(200, json=load_fixture("geckoterminal_new_pools.json"))
    )
    router.get(f"{settings.rugcheck_base_url}/stats/new_tokens").mock(
        return_value=httpx.Response(200, json=load_fixture("rugcheck_new_tokens.json"))
    )
    router.get(f"{settings.dexscreener_base_url}/token-profiles/latest/v1").mock(
        return_value=httpx.Response(200, json=load_fixture("dexscreener_profiles.json"))
    )


async def test_collect_once_merges_all_sources():
    settings = get_settings()
    # Ограничим сети одной, чтобы фикстура GeckoTerminal не дублировалась по сетям.
    object.__setattr__(settings, "gecko_networks", "eth")
    with respx.mock(assert_all_called=False) as router:
        _mock_sources(router, settings)
        async with HttpClient() as http:
            tokens = await collect_once(http, settings)
    sources = {t.source for t in tokens}
    assert sources == {"geckoterminal", "rugcheck", "dexscreener"}


@respx.mock(assert_all_called=False)
async def test_run_tick_persists_and_dedups_across_sources(respx_mock):
    settings = get_settings()
    object.__setattr__(settings, "gecko_networks", "eth")
    _mock_sources(respx_mock, settings)
    await create_all()

    # Первый тик — записываем.
    inserted_first = await run_tick(settings)
    assert inserted_first > 0

    # GeckoTerminal(0xTOKENabc) и DexScreener(0xTOKENabc) — один адрес из двух источников.
    from app.db import get_sessionmaker

    async with get_sessionmaker()() as s:
        rows = (await s.execute(select(Token).where(Token.address == "0xtokenabc"))).scalars().all()
        assert len(rows) == 1  # дедуп меж источниками

    # Второй тик с теми же данными — ни одной новой строки.
    inserted_second = await run_tick(settings)
    assert inserted_second == 0

    async with get_sessionmaker()() as s:
        total_after = (await s.execute(select(func.count()).select_from(Token))).scalar_one()
    assert total_after == inserted_first


@respx.mock(assert_all_called=False)
async def test_one_source_down_does_not_break_tick(respx_mock):
    settings = get_settings()
    object.__setattr__(settings, "gecko_networks", "eth")
    object.__setattr__(settings, "http_max_retries", 1)
    # RugCheck падает 500, остальные — ок.
    respx_mock.get(url__startswith=f"{settings.gecko_base_url}/networks/").mock(
        return_value=httpx.Response(200, json=load_fixture("geckoterminal_new_pools.json"))
    )
    respx_mock.get(f"{settings.rugcheck_base_url}/stats/new_tokens").mock(
        return_value=httpx.Response(500)
    )
    respx_mock.get(f"{settings.dexscreener_base_url}/token-profiles/latest/v1").mock(
        return_value=httpx.Response(200, json=load_fixture("dexscreener_profiles.json"))
    )
    await create_all()
    inserted = await run_tick(settings)
    # EVM-пары + dexscreener-профиль всё равно записались.
    assert inserted > 0
