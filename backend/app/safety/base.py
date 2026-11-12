"""Единая модель находок безопасности.

Каждый провайдер (GoPlus / RugCheck / honeypot.is) заполняет ЧАСТЬ полей
SafetyFindings; затем находки сливаются (merge) и скорятся (scoring.py).
Поля — Optional: None означает «провайдер не дал данных», и это не то же
самое, что False. Это важно для честного вердикта (нет данных → REVIEW, а не PASS).
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any


@dataclass
class SafetyFindings:
    chain: str = ""
    address: str = ""

    # On-chain безопасность
    is_honeypot: bool | None = None
    buy_tax: float | None = None            # доля 0..1
    sell_tax: float | None = None           # доля 0..1
    is_open_source: bool | None = None      # контракт верифицирован
    mint_authority_active: bool | None = None
    freeze_authority_active: bool | None = None
    owner_can_change_balance: bool | None = None
    owner_can_take_ownership: bool | None = None  # hidden owner / reclaim
    can_blacklist: bool | None = None
    is_proxy: bool | None = None

    # Ликвидность и держатели
    lp_locked: bool | None = None
    lp_locked_pct: float | None = None      # доля залоченного LP 0..1
    top_holder_pct: float | None = None     # доля топ-1 (без пула/burn) 0..1
    holder_count: int | None = None

    # Явные сигналы «вредоносный/скам» от провайдеров (то, по чему GeckoTerminal/Coinbase
    # ставят метку «скам-токен»). None = провайдер не дал данных.
    is_airdrop_scam: bool | None = None          # помечен как airdrop-скам
    honeypot_same_creator: bool | None = None    # создатель уже делал ханипоты
    cannot_sell_all: bool | None = None          # нельзя продать весь баланс (ханипот-подобно)
    cannot_buy: bool | None = None               # нельзя купить
    is_fake_token: bool | None = None            # поддельный/копия токена
    tax_modifiable: bool | None = None           # владелец может менять налог/slippage (→100%)
    trading_cooldown: bool | None = None         # задержка между сделками

    # Прочее
    rugged: bool | None = None
    is_true_token: bool | None = None

    # Репутация площадки-агрегатора (GeckoTerminal gt_score, 0..100; выше = надёжнее).
    # Низкий балл → soft-риск. None = провайдер не дал данных.
    reputation_score: float | None = None

    sources: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def merge(self, other: SafetyFindings) -> SafetyFindings:
        """Слить находки другого провайдера: не затираем уже известное не-None."""
        for f in fields(self):
            if f.name in ("chain", "address", "sources", "raw"):
                continue
            if getattr(self, f.name) is None and getattr(other, f.name) is not None:
                setattr(self, f.name, getattr(other, f.name))
        for s in other.sources:
            if s not in self.sources:
                self.sources.append(s)
        self.raw.update(other.raw)
        return self


@dataclass
class RedFlag:
    code: str
    severity: str      # "hard" | "soft" | "info"
    message: str
    weight: int = 0    # вклад в risk_score (для soft/info)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "weight": self.weight,
        }


@dataclass
class SafetyResult:
    chain: str
    address: str
    risk_score: int            # 0..100, выше = рискованнее
    verdict: str               # PASS | REVIEW | BLOCK
    red_flags: list[RedFlag]
    findings: SafetyFindings

    def red_flags_as_dicts(self) -> list[dict[str, Any]]:
        return [f.as_dict() for f in self.red_flags]

    # Коды, по которым показываем явную метку «скам-токен» (как GeckoTerminal/Coinbase).
    MALICIOUS_CODES = frozenset({
        "honeypot", "airdrop_scam", "honeypot_same_creator",
        "cannot_sell_all", "fake_token", "rugged",
    })

    @property
    def is_malicious(self) -> bool:
        """True → в UI красная плашка «Помечен как скам-токен, можете потерять средства»."""
        return any(f.code in self.MALICIOUS_CODES for f in self.red_flags)
