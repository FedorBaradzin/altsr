"""Allowlist проверенных активов (стейблкоины / блу-чипы).

Централизованные стейблкоины (USDC, USDT, DAI…) по своему устройству имеют активную
mint/freeze authority и высокую концентрацию у эмитента/пулов. Наши честные правила
справедливо считают это HARD-риском — но это НЕ скам, а ожидаемое свойство
регулируемого стейбла. Поэтому точные, захардкоженные контрактные адреса таких
активов получают вердикт PASS напрямую, минуя скоринг.

Матчим ТОЛЬКО по точному адресу контракта — символ подделать легко, адрес нет.
EVM-адреса хранятся в нижнем регистре (как нормализует discovery), Solana-миниты —
с сохранением регистра (base58 чувствителен к регистру).
"""
from __future__ import annotations

# name -> адрес в канонической форме (EVM lower-case, Solana — как есть).
_VERIFIED: dict[str, str] = {
    # ---- Solana ----
    "USDC (Solana)": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT (Solana)": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "PYUSD (Solana)": "2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo",
    # ---- Ethereum ----
    "USDC (Ethereum)": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    "USDT (Ethereum)": "0xdac17f958d2ee523a2206206994597c13d831ec7",
    "DAI (Ethereum)": "0x6b175474e89094c44da98b954eedeac495271d0f",
    "BUSD (Ethereum)": "0x4fabb145d64652a948d72533023f6e7a623c7c53",
    "TUSD (Ethereum)": "0x0000000000085d4780b73119b644ae5ecd22b376",
    "PYUSD (Ethereum)": "0x6c3ea9036406852006290770bedfcaba0e23a0e8",
    "USDe (Ethereum)": "0x4c9edd5852cd905f086c759e8383e09bff1e68b3",
    # ---- BSC ----
    "USDT (BSC)": "0x55d398326f99059ff775485246999027b3197955",
    "USDC (BSC)": "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",
    "BUSD (BSC)": "0xe9e7cea3dedca5984780bafc599bd69add087d56",
    "DAI (BSC)": "0x1af3f329e8be154074d8769d1ffa4ee058b1dbc3",
    # ---- Base ----
    "USDC (Base)": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    "USDbC (Base)": "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca",
}


def _norm(address: str) -> str:
    a = (address or "").strip()
    return a.lower() if a[:2].lower() == "0x" else a


# норм.адрес -> человекочитаемое имя
_BY_ADDRESS: dict[str, str] = {_norm(a): n for n, a in _VERIFIED.items()}


def verified_name(address: str) -> str | None:
    """Имя проверенного актива, если адрес в allowlist, иначе None."""
    if not address:
        return None
    return _BY_ADDRESS.get(_norm(address))


def is_verified(address: str) -> bool:
    return bool(address) and _norm(address) in _BY_ADDRESS
