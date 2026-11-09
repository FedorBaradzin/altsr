"""Скоринг безопасности: SafetyFindings → risk_score + red_flags + вердикт.

Чистые функции, без сети — полностью покрываются unit-тестами.

Вердикт:
- Любой HARD-флаг → BLOCK (risk ≥ 90).
- Иначе risk считается из SOFT-весов (0..100):
    risk ≥ 70 → BLOCK, risk ≥ 30 → REVIEW, иначе PASS.
- Честность: если ключевые сигналы безопасности отсутствуют (None), PASS не ставим —
  максимум REVIEW. «Нет данных» ≠ «безопасно».

ЧЕСТНОЕ ОГРАНИЧЕНИЕ (в UI): детекция ловит ЧАСТЬ схем, не все; slow-rug и новые
паттерны проскакивают. Вердикт PASS ≠ «безопасно» и тем более ≠ «вырастет».
"""
from __future__ import annotations

from .base import RedFlag, SafetyFindings, SafetyResult

# Пороги (вынесены ради тестов/конфигурации).
SELL_TAX_HARD = 0.15        # >15% налога на продажу → HARD
TAX_SOFT = 0.05             # 5–15% → SOFT
BUY_TAX_SOFT = 0.10
TOP_HOLDER_HARD = 0.50      # топ-1 > 50% → HARD
TOP_HOLDER_SOFT = 0.25      # 25–50% → SOFT
LOW_HOLDERS = 50

PASS_MAX = 30               # risk < 30 → PASS
BLOCK_MIN = 70              # risk ≥ 70 → BLOCK


def evaluate(f: SafetyFindings) -> SafetyResult:
    red: list[RedFlag] = []
    hard = False

    # ---------- HARD-BLOCK ----------
    if f.is_honeypot is True:
        red.append(RedFlag("honeypot", "hard", "Ханипот: продажа невозможна"))
        hard = True
    if f.sell_tax is not None and f.sell_tax > SELL_TAX_HARD:
        red.append(RedFlag("sell_tax_extreme", "hard",
                           f"Налог на продажу {f.sell_tax*100:.0f}% (>{SELL_TAX_HARD*100:.0f}%)"))
        hard = True
    if f.mint_authority_active is True:
        red.append(RedFlag("mint_authority", "hard", "Активна mint authority (можно допечатать)"))
        hard = True
    if f.owner_can_change_balance is True:
        red.append(RedFlag("owner_change_balance", "hard",
                           "Владелец может менять балансы кошельков"))
        hard = True
    if f.top_holder_pct is not None and f.top_holder_pct > TOP_HOLDER_HARD:
        red.append(RedFlag("holder_concentration_extreme", "hard",
                           f"Топ-1 холдер держит {f.top_holder_pct*100:.0f}% (>50%)"))
        hard = True
    if f.lp_locked is False:
        red.append(RedFlag("lp_unlocked", "hard", "Ликвидность не залочена (риск вытаскивания LP)"))
        hard = True
    if f.rugged is True:
        red.append(RedFlag("rugged", "hard", "Помечен как rugged источником данных"))
        hard = True

    # ---------- SOFT-FLAG (вес в risk_score) ----------
    risk = 0
    if not hard:
        if f.owner_can_take_ownership is True:
            red.append(RedFlag("takeable_ownership", "soft",
                              "Возможен возврат владения (hidden owner)", 30))
        if f.freeze_authority_active is True:
            red.append(RedFlag("freeze_authority", "soft",
                              "Активна freeze authority (можно заморозить)", 20))
        if f.can_blacklist is True:
            red.append(RedFlag("blacklist", "soft",
                              "Контракт может блокировать переводы/блэклист", 18))
        if f.is_open_source is False:
            red.append(RedFlag("unverified_contract", "soft", "Контракт не верифицирован", 25))
        if f.is_proxy is True:
            red.append(RedFlag("proxy", "soft", "Upgradeable/proxy-контракт", 12))
        if f.is_true_token is False:
            red.append(RedFlag("fake_token", "soft",
                              "Признан не настоящим токеном (is_true_token=false)", 20))
        # Концентрация холдеров (не критичная)
        if f.top_holder_pct is not None and TOP_HOLDER_SOFT < f.top_holder_pct <= TOP_HOLDER_HARD:
            red.append(RedFlag("holder_concentration", "soft",
                              f"Высокая концентрация: топ-1 {f.top_holder_pct*100:.0f}%", 20))
        # Налоги (не критичные)
        if f.sell_tax is not None and TAX_SOFT < f.sell_tax <= SELL_TAX_HARD:
            red.append(RedFlag("sell_tax", "soft", f"Налог на продажу {f.sell_tax*100:.0f}%", 15))
        if f.buy_tax is not None and f.buy_tax > BUY_TAX_SOFT:
            red.append(RedFlag("buy_tax", "soft", f"Налог на покупку {f.buy_tax*100:.0f}%", 12))
        # LP частично залочен
        if f.lp_locked is True and f.lp_locked_pct is not None and f.lp_locked_pct < 0.5:
            red.append(RedFlag("lp_partial_lock", "soft",
                              f"LP залочен лишь на {f.lp_locked_pct*100:.0f}%", 15))
        # Мало холдеров
        if f.holder_count is not None and f.holder_count < LOW_HOLDERS:
            red.append(RedFlag("few_holders", "soft", f"Мало холдеров: {f.holder_count}", 10))

        risk = sum(flag.weight for flag in red if flag.severity == "soft")

    # ---------- Неполнота данных ----------
    unknown = _unknown_signals(f)
    if unknown:
        red.append(RedFlag("insufficient_data", "info",
                          f"Нет данных по: {', '.join(unknown)}", 0))

    # ---------- Вердикт ----------
    if hard:
        verdict = "BLOCK"
        risk = max(risk, 90)
    else:
        risk = min(risk, 100)
        if risk >= BLOCK_MIN:
            verdict = "BLOCK"
        elif risk >= PASS_MAX:
            verdict = "REVIEW"
        else:
            # Нет данных по честной оценке honeypot/authority → не ставим PASS.
            verdict = "REVIEW" if _cannot_clear(f) else "PASS"

    return SafetyResult(
        chain=f.chain, address=f.address, risk_score=int(risk),
        verdict=verdict, red_flags=red, findings=f,
    )


def _unknown_signals(f: SafetyFindings) -> list[str]:
    checks = {
        "honeypot": f.is_honeypot,
        "sell_tax": f.sell_tax,
        "mint_authority": f.mint_authority_active,
        "holders": f.top_holder_pct,
        "lp_lock": f.lp_locked,
    }
    return [k for k, v in checks.items() if v is None]


def _cannot_clear(f: SafetyFindings) -> bool:
    """Нельзя ставить PASS, если не смогли оценить honeypot/налоги/authority вообще."""
    evm_honeypot_unknown = f.is_honeypot is None and f.sell_tax is None
    authority_unknown = f.mint_authority_active is None
    return evm_honeypot_unknown and authority_unknown
