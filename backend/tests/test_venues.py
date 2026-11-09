"""Venues: ссылки «как купить» для разных сетей."""
from __future__ import annotations

from app.signals.venues import build_buy_options


def _by_name(options):
    return {o.name: o.url for o in options}


def test_solana_uses_jupiter():
    opts = build_buy_options("solana", "So1Mint", None)
    names = _by_name(opts)
    assert "Jupiter" in names and names["Jupiter"].endswith("SOL-So1Mint")
    assert "DexScreener" in names
    assert "Explorer" in names and "solscan.io" in names["Explorer"]


def test_ethereum_uses_uniswap_mainnet():
    opts = build_buy_options("ethereum", "0xabc", "0xpair")
    names = _by_name(opts)
    assert "Uniswap" in names and "chain=mainnet" in names["Uniswap"]
    assert "outputCurrency=0xabc" in names["Uniswap"]
    # Пара известна → ссылка на пул GeckoTerminal.
    assert "GeckoTerminal" in names and "0xpair" in names["GeckoTerminal"]
    assert "etherscan.io" in names["Explorer"]


def test_bsc_uses_pancakeswap():
    names = _by_name(build_buy_options("bsc", "0xdef"))
    assert "PancakeSwap" in names and "pancakeswap.finance" in names["PancakeSwap"]


def test_options_are_serializable():
    opts = build_buy_options("base", "0xabc", "0xpair")
    d = opts[0].as_dict()
    assert {"type", "name", "url"} <= set(d.keys())
