"""Кросс-проверка двух независимых safety-провайдеров (T10).

Идея: совпадение вердиктов двух независимых источников (напр. GoPlus +
honeypot.is, или GoPlus + RugCheck) повышает доверие; расхождение по решающему
сигналу — повод снизить уверенность и поднять вердикт до REVIEW. «Нет данных» у
одного провайдера (таймаут / None) НЕ ломает батч: кросс-проверка просто
деградирует до single_source без штрафа.

Всё здесь — чистые функции без сети/БД, полностью покрываются unit-тестами.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .base import RedFlag, SafetyFindings, SafetyResult

# Решающие булевы сигналы, которые сравниваем между провайдерами.
# Берём те, что реально выдаёт больше одного источника (honeypot, authority, LP, ...).
_BOOL_SIGNALS = (
    "is_honeypot",
    "mint_authority_active",
    "freeze_authority_active",
    "owner_can_change_balance",
    "owner_can_take_ownership",
    "can_blacklist",
    "is_open_source",
    "lp_locked",
    "rugged",
    "is_true_token",
)

# Числовые налоги: расхождение считаем значимым, если разница больше допуска (в долях).
_NUM_SIGNALS = ("buy_tax", "sell_tax")
_NUM_TOLERANCE = 0.03  # 3 процентных пункта

# Штраф уверенности по умолчанию при расхождении источников (доля 0..1).
DEFAULT_CONFIDENCE_PENALTY = 0.25

# Статусы результата кросс-проверки.
AGREE = "agree"
DIVERGE = "diverge"
SINGLE_SOURCE = "single_source"


@dataclass
class AgreementResult:
    """Результат сверки двух провайдеров."""

    status: str                                 # agree | diverge | single_source
    diverging_signals: list[str] = field(default_factory=list)
    confidence_penalty: float = 0.0             # сколько вычесть из уверенности (0..1)
    force_review: bool = False                  # поднять вердикт минимум до REVIEW
    sources: list[str] = field(default_factory=list)

    @property
    def agreed(self) -> bool:
        return self.status == AGREE


def _has_data(f: SafetyFindings | None) -> bool:
    """Есть ли у провайдера хоть какие-то данные (иначе — считать его отсутствующим)."""
    if f is None:
        return False
    if f.sources:
        return True
    return any(getattr(f, name) is not None for name in (*_BOOL_SIGNALS, *_NUM_SIGNALS))


def _diverging_signals(a: SafetyFindings, b: SafetyFindings) -> list[str]:
    """Сигналы, по которым оба провайдера высказались, но разошлись."""
    out: list[str] = []
    for name in _BOOL_SIGNALS:
        va, vb = getattr(a, name), getattr(b, name)
        if va is not None and vb is not None and va != vb:
            out.append(name)
    for name in _NUM_SIGNALS:
        va, vb = getattr(a, name), getattr(b, name)
        if va is not None and vb is not None and abs(va - vb) > _NUM_TOLERANCE:
            out.append(name)
    return out


def cross_check(
    a: SafetyFindings | None,
    b: SafetyFindings | None,
    *,
    penalty: float = DEFAULT_CONFIDENCE_PENALTY,
) -> AgreementResult:
    """Сверить находки двух провайдеров.

    - Оба с данными и совпали → AGREE, штрафа нет.
    - Оба с данными, но разошлись по решающему сигналу → DIVERGE: штраф уверенности
      и force_review=True.
    - Один (или оба) без данных / None → SINGLE_SOURCE: без штрафа (деградация, а не сбой).
    """
    a_ok, b_ok = _has_data(a), _has_data(b)
    sources: list[str] = []
    for f in (a, b):
        if f is not None:
            for s in f.sources:
                if s not in sources:
                    sources.append(s)

    if not (a_ok and b_ok):
        return AgreementResult(status=SINGLE_SOURCE, sources=sources)

    assert a is not None and b is not None  # для type-checker: _has_data это гарантирует
    diverging = _diverging_signals(a, b)
    if diverging:
        return AgreementResult(
            status=DIVERGE,
            diverging_signals=diverging,
            confidence_penalty=penalty,
            force_review=True,
            sources=sources,
        )
    return AgreementResult(status=AGREE, sources=sources)


def apply_agreement(result: SafetyResult, agreement: AgreementResult) -> SafetyResult:
    """Наложить итог кросс-проверки на вердикт безопасности (чистая мутация-обёртка).

    При расхождении источников: добавляем info/soft-флаг и поднимаем PASS → REVIEW
    (BLOCK не трогаем — он и так строже). Совпадение/один источник — без изменений.
    """
    if agreement.status == DIVERGE:
        result.red_flags.append(
            RedFlag(
                "source_divergence",
                "soft",
                "Источники разошлись по: " + ", ".join(agreement.diverging_signals),
                weight=0,
            )
        )
        if result.verdict == "PASS":
            result.verdict = "REVIEW"
    elif agreement.status == SINGLE_SOURCE:
        result.red_flags.append(
            RedFlag(
                "single_source",
                "info",
                "Кросс-проверка недоступна: данные лишь одного провайдера",
                weight=0,
            )
        )
    return result
