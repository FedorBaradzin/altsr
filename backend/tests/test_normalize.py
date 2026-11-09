"""Нормализация ответов источников в единую модель Token."""
from __future__ import annotations

from app.discovery import dexscreener, geckoterminal, rugcheck
from app.discovery.geckoterminal import _index_included

from .conftest import load_fixture


def test_gecko_normalizes_base_token():
    payload = load_fixture("geckoterminal_new_pools.json")
    included = _index_included(payload)
    tokens = [
        geckoterminal.normalize_pool(p, included, "eth") for p in payload["data"]
    ]
    assert all(t is not None for t in tokens)
    first = tokens[0]
    # Адрес — именно базового токена, не адрес пула.
    assert first.address == "0xtokenabc"  # нижний регистр
    assert first.chain == "ethereum"
    assert first.symbol == "PEPE2"
    assert first.pair_address == "0xpool1address"
    assert first.dex == "uniswap_v3"
    assert first.liquidity_usd == 18450.50
    assert first.fdv == 920000.0
    assert first.created_at is not None
    assert first.socials.get("twitter_handle") == "pepe2coin"


def test_rugcheck_handles_iso_and_unix_time():
    rows = load_fixture("rugcheck_new_tokens.json")
    tokens = [rugcheck.normalize_mint(r) for r in rows]
    assert tokens[0].chain == "solana"
    assert tokens[0].symbol == "BONKJR"
    assert tokens[0].created_at is not None
    # Вторая запись — unix-секунды.
    assert tokens[1].created_at is not None
    assert tokens[1].address == "so11111solmintbbb"


def test_dexscreener_profiles_links():
    rows = load_fixture("dexscreener_profiles.json")
    tokens = [dexscreener.normalize_profile(r) for r in rows]
    assert tokens[0].chain == "ethereum"
    assert tokens[0].address == "0xtokenabc"
    assert tokens[0].socials.get("twitter") == "https://twitter.com/pepe2coin"


def test_invalid_rows_are_skipped():
    assert geckoterminal.normalize_pool({"attributes": {}}, {}, "eth") is None
    assert rugcheck.normalize_mint({"symbol": "X"}) is None
    assert dexscreener.normalize_profile({"chainId": "eth"}) is None


def test_dedup_key_is_lowercased():
    rows = load_fixture("rugcheck_new_tokens.json")
    t = rugcheck.normalize_mint(rows[0])
    assert t.dedup_key == "solana:so11111solmintaaa"
