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
TOP_HOLDER_CRITICAL = 0.90  # топ-1 > 90% (почти весь объём у одного) → HARD BLOCK
TOP_HOLDER_HARD = 0.50      # 50–90% → сильное ПРЕДУПРЕЖДЕНИЕ (soft), не авто-BLOCK
TOP_HOLDER_SOFT = 0.25      # 25–50% → предупреждение (soft)

# Веса предупреждений (soft). Концентрация 50–90% и незалоченный LP — это риск, но у
# свежих bonding-curve токенов часто структурный (кривая/пул), а не злой умысел. Поэтому
# они дают REVIEW (жёлтое предупреждение), а BLOCK — только в сумме или с HARD-флагом.
CONCENTRATION_CRIT_WEIGHT = 55   # топ-1 > 90% (почти весь объём) — сильное предупреждение
CONCENTRATION_HIGH_WEIGHT = 45   # топ-1 50–90%
CONCENTRATION_MID_WEIGHT = 20    # топ-1 25–50%
LP_UNLOCKED_WEIGHT = 30
LOW_HOLDERS = 50

PASS_MAX = 30               # risk < 30 → PASS
BLOCK_MIN = 70              # risk ≥ 70 → BLOCK


def evaluate(
    f: SafetyFindings,
    *,
    require_lp_lock_solana: bool = False,
    gecko_min_score: float | None = None,
) -> SafetyResult:
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
    # Концентрация холдеров и незалоченный LP — это ПРЕДУПРЕЖДЕНИЯ (soft, ниже), а не
    # авто-BLOCK: у свежих токенов топ-холдер — это почти всегда бондинг-кривая/пул
    # (держит ~весь объём до «graduation»), а не злой кит. Красный BLOCK даём за доказанный
    # скам (honeypot / mint authority / rugged / fake / owner-change), а высокую концентрацию
    # показываем как «высокий риск — будь осторожен» (REVIEW). В сумме с LP → всё равно BLOCK.
    if f.rugged is True:
        red.append(RedFlag("rugged", "hard", "Помечен как rugged источником данных"))
        hard = True
    # ---- Явные сигналы «вредоносный/скам» от провайдеров (parity с GeckoTerminal/Coinbase) ----
    if f.is_airdrop_scam is True:
        red.append(RedFlag("airdrop_scam", "hard", "Помечен как airdrop-скам"))
        hard = True
    if f.honeypot_same_creator is True:
        red.append(RedFlag("honeypot_same_creator", "hard",
                           "Создатель уже выпускал ханипоты"))
        hard = True
    if f.cannot_sell_all is True:
        red.append(RedFlag("cannot_sell_all", "hard",
                           "Нельзя продать весь баланс (ханипот-подобно)"))
        hard = True
    if f.is_fake_token is True:
        red.append(RedFlag("fake_token", "hard", "Поддельный токен (копия известного)"))
        hard = True

    # ---------- SOFT-FLAG (вес в risk_score) ----------
    risk = 0
    behavioral_risk = 0
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
        if f.tax_modifiable is True:
            red.append(RedFlag("tax_modifiable", "soft",
                              "Владелец может менять налог/slippage (риск налога до 100%)", 25))
        if f.cannot_buy is True:
            red.append(RedFlag("cannot_buy", "soft", "Покупка заблокирована контрактом", 18))
        if f.trading_cooldown is True:
            red.append(RedFlag("trading_cooldown", "soft",
                              "Задержка между сделками (может мешать продаже)", 10))
        if f.is_true_token is False:
            red.append(RedFlag("fake_token", "soft",
                              "Признан не настоящим токеном (is_true_token=false)", 20))
        # Концентрация холдеров — предупреждение, не авто-BLOCK (у свежих токенов топ-холдер
        # это бондинг-кривая/пул). Три уровня: почти весь объём > высокая > повышенная.
        if f.top_holder_pct is not None and f.top_holder_pct > TOP_HOLDER_CRITICAL:
            red.append(RedFlag("holder_concentration_extreme", "soft",
                              f"Топ-1 адрес держит {f.top_holder_pct*100:.0f}% — почти весь объём "
                              f"(типично для совсем новых токенов; высокий риск дампа)",
                              CONCENTRATION_CRIT_WEIGHT, category="newness"))
        elif f.top_holder_pct is not None and f.top_holder_pct > TOP_HOLDER_HARD:
            red.append(RedFlag("holder_concentration_extreme", "soft",
                              f"Топ-1 холдер держит {f.top_holder_pct*100:.0f}% (>50%) — "
                              f"высокий риск дампа", CONCENTRATION_HIGH_WEIGHT, category="newness"))
        elif f.top_holder_pct is not None and TOP_HOLDER_SOFT < f.top_holder_pct <= TOP_HOLDER_HARD:
            red.append(RedFlag("holder_concentration", "soft",
                              f"Высокая концентрация: топ-1 {f.top_holder_pct*100:.0f}%",
                              CONCENTRATION_MID_WEIGHT, category="newness"))
        # Ликвидность не залочена — предупреждение (риск вытаскивания LP).
        if f.lp_locked is False:
            red.append(RedFlag("lp_unlocked", "soft",
                              "Ликвидность не залочена (риск вытаскивания LP)",
                              LP_UNLOCKED_WEIGHT, category="newness"))
        # Налоги (не критичные)
        if f.sell_tax is not None and TAX_SOFT < f.sell_tax <= SELL_TAX_HARD:
            red.append(RedFlag("sell_tax", "soft", f"Налог на продажу {f.sell_tax*100:.0f}%", 15))
        if f.buy_tax is not None and f.buy_tax > BUY_TAX_SOFT:
            red.append(RedFlag("buy_tax", "soft", f"Налог на покупку {f.buy_tax*100:.0f}%", 12))
        # LP частично залочен — тоже структурный признак (newness).
        if f.lp_locked is True and f.lp_locked_pct is not None and f.lp_locked_pct < 0.5:
            red.append(RedFlag("lp_partial_lock", "soft",
                              f"LP залочен лишь на {f.lp_locked_pct*100:.0f}%", 15,
                              category="newness"))
        # Мало холдеров — у свежих токенов нормально (newness).
        if f.holder_count is not None and f.holder_count < LOW_HOLDERS:
            red.append(RedFlag("few_holders", "soft", f"Мало холдеров: {f.holder_count}", 10,
                              category="newness"))
        # Низкая репутация площадки (GeckoTerminal gt_score) — у новых токенов низкая по
        # определению (newness).
        if (
            gecko_min_score is not None
            and f.reputation_score is not None
            and f.reputation_score < gecko_min_score
        ):
            red.append(RedFlag(
                "low_reputation", "soft",
                f"Низкий gt_score GeckoTerminal: {f.reputation_score:.0f} < {gecko_min_score:.0f}",
                25, category="newness",
            ))

        # Полный risk_score — для отображения (все soft-флаги).
        risk = sum(flag.weight for flag in red if flag.severity == "soft")
        # «Поведенческий» риск — только НЕ-newness soft-флаги. Красный BLOCK по сумме даём
        # лишь за него: признаки новизны (концентрация/мало холдеров/низкая репутация/
        # незалоченный LP) сами по себе → максимум REVIEW, а не красный «скам».
        behavioral_risk = sum(
            flag.weight for flag in red
            if flag.severity == "soft" and flag.category != "newness"
        )

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
        if behavioral_risk >= BLOCK_MIN:
            verdict = "BLOCK"               # доказанно-поведенческий скам по сумме
        elif risk >= PASS_MAX:
            verdict = "REVIEW"              # есть риск (в т.ч. признаки новизны) → предупреждение
        else:
            # Нет данных по честной оценке honeypot/authority → не ставим PASS.
            verdict = "REVIEW" if _cannot_clear(f, require_lp_lock_solana) else "PASS"

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


def _cannot_clear(f: SafetyFindings, require_lp_lock_solana: bool = False) -> bool:
    """Нельзя ставить PASS, если не смогли оценить honeypot/налоги/authority вообще.

    require_lp_lock_solana: для Solana не ставить PASS, пока LP-lock не подтверждён
    залоченным (lp_locked is not True). Закрывает дыру, когда GoPlus(solana) даёт
    только authority, а honeypot.is недоступен (EVM-only) и RugCheck выключен —
    незалоченный/непроверенный LP это главный вектор раг-пула.
    """
    evm_honeypot_unknown = f.is_honeypot is None and f.sell_tax is None
    authority_unknown = f.mint_authority_active is None
    if evm_honeypot_unknown and authority_unknown:
        return True
    if require_lp_lock_solana and f.chain == "solana" and f.lp_locked is not True:
        return True
    return False
