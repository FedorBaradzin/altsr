"""Конфигурация приложения (Pydantic v2 settings).

Все ключи и параметры берутся из окружения/.env. В коде секретов нет.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Инфраструктура ---
    # Для прода: postgresql+asyncpg://user:pass@postgres:5432/altsr
    # Для тестов по умолчанию используется in-memory sqlite.
    database_url: str = Field(
        default="postgresql+asyncpg://altsr:altsr@localhost:5432/altsr",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # --- Discovery: источники ---
    # Какие сети тянуть из GeckoTerminal new_pools (EVM-подобные + solana).
    gecko_networks: str = Field(default="eth,base,bsc,solana", alias="GECKO_NETWORKS")
    gecko_base_url: str = Field(
        default="https://api.geckoterminal.com/api/v2", alias="GECKO_BASE_URL"
    )
    dexscreener_base_url: str = Field(
        default="https://api.dexscreener.com", alias="DEXSCREENER_BASE_URL"
    )
    rugcheck_base_url: str = Field(
        default="https://api.rugcheck.xyz/v1", alias="RUGCHECK_BASE_URL"
    )
    rugcheck_enabled: bool = Field(default=False, alias="RUGCHECK_ENABLED")
    # Моментум-движок (DexScreener): входим только в растущие токены.
    momentum_enabled: bool = Field(default=True, alias="MOMENTUM_ENABLED")
    momentum_require_data: bool = Field(default=True, alias="MOMENTUM_REQUIRE_DATA")
    momentum_min_change_m5: float = Field(default=0.0, alias="MOMENTUM_MIN_CHANGE_M5")
    momentum_min_change_h1: float = Field(default=0.0, alias="MOMENTUM_MIN_CHANGE_H1")
    momentum_min_buy_sell: float = Field(default=1.2, alias="MOMENTUM_MIN_BUY_SELL")

    # --- Технические индикаторы (T1, рычаги ①③) ---
    # Гейт входа по индикаторам. Консервативно выключен: включается, когда есть
    # ряды цен/свечей (приходят из OHLCV-источника, T10). Пороги — примеры, не рекомендация.
    indicators_enabled: bool = Field(default=False, alias="INDICATORS_ENABLED")
    # Нет данных для индикатора → блокировать (True) или пропускать его проверку (False).
    indicators_require_data: bool = Field(default=False, alias="INDICATORS_REQUIRE_DATA")
    indicator_roc_period: int = Field(default=1, alias="INDICATOR_ROC_PERIOD")
    indicator_roc_min: float = Field(default=0.0, alias="INDICATOR_ROC_MIN")
    indicator_buy_sell_min: float = Field(default=1.3, alias="INDICATOR_BUY_SELL_MIN")
    indicator_aroon_period: int = Field(default=14, alias="INDICATOR_AROON_PERIOD")
    indicator_aroon_osc_min: float = Field(default=0.0, alias="INDICATOR_AROON_OSC_MIN")
    indicator_atr_period: int = Field(default=14, alias="INDICATOR_ATR_PERIOD")
    # Движение (ATR, % от цены) должно перекрывать издержки fee+spread+slippage.
    indicator_cost_floor_pct: float = Field(default=2.0, alias="INDICATOR_COST_FLOOR_PCT")
    indicator_require_vol_rising: bool = Field(
        default=True, alias="INDICATOR_REQUIRE_VOL_RISING"
    )

    # --- Safety / анти-скам (Фаза 1) ---
    goplus_base_url: str = Field(
        default="https://api.gopluslabs.io/api/v1", alias="GOPLUS_BASE_URL"
    )
    honeypot_base_url: str = Field(
        default="https://api.honeypot.is/v2", alias="HONEYPOT_BASE_URL"
    )
    # Сколько токенов скринить за один тик screener-воркера.
    screen_batch_size: int = Field(default=20, alias="SCREEN_BATCH_SIZE")
    screen_interval_seconds: int = Field(default=15, alias="SCREEN_INTERVAL_SECONDS")

    # --- Signal engine (Фаза 2) ---
    signal_min_liquidity_usd: float = Field(default=5000.0, alias="SIGNAL_MIN_LIQUIDITY_USD")
    signal_min_age_minutes: int = Field(default=0, alias="SIGNAL_MIN_AGE_MINUTES")
    signal_max_age_minutes: int = Field(default=1440, alias="SIGNAL_MAX_AGE_MINUTES")
    signal_min_holders: int = Field(default=0, alias="SIGNAL_MIN_HOLDERS")
    signal_require_pass: bool = Field(default=True, alias="SIGNAL_REQUIRE_PASS")
    signal_max_risk: int = Field(default=30, alias="SIGNAL_MAX_RISK")
    # Минимальная уверенность сигнала для входа (0..1). Выше порог → меньше,
    # но качественнее входов, меньше просадок.
    signal_min_confidence: float = Field(default=0.0, alias="SIGNAL_MIN_CONFIDENCE")
    signal_batch_size: int = Field(default=30, alias="SIGNAL_BATCH_SIZE")
    signal_interval_seconds: int = Field(default=20, alias="SIGNAL_INTERVAL_SECONDS")

    # --- Обучение на исходах (T3, рычаг ④) ---
    # confidence из обученных весов (при наличии) вместо эвристики.
    calibration_enabled: bool = Field(default=False, alias="CALIBRATION_ENABLED")
    # Горизонт фиксации исхода сигнала (вырос/упал), минут.
    outcome_horizon_minutes: int = Field(default=30, alias="OUTCOME_HORIZON_MIN")
    # Минимум размеченных примеров для калибровки; иначе fallback на эвристику.
    calibration_min_samples: int = Field(default=50, alias="CALIBRATION_MIN_SAMPLES")

    # --- Paper executor (Фаза 3) — ТОЛЬКО бумага, реальных денег нет ---
    paper_start_balance: float = Field(default=100_000.0, alias="PAPER_START_BALANCE")
    paper_position_size_usd: float = Field(default=500.0, alias="PAPER_POSITION_SIZE_USD")
    paper_max_positions: int = Field(default=10, alias="PAPER_MAX_POSITIONS")
    paper_daily_loss_limit_usd: float = Field(default=500.0, alias="PAPER_DAILY_LOSS_LIMIT_USD")
    paper_hard_stop_pct: float = Field(default=0.25, alias="PAPER_HARD_STOP_PCT")
    paper_arm_after_profit_pct: float = Field(default=0.20, alias="PAPER_ARM_AFTER_PROFIT_PCT")
    paper_trailing_stop_pct: float = Field(default=0.08, alias="PAPER_TRAILING_STOP_PCT")
    paper_take_profit_x: float = Field(default=2.0, alias="PAPER_TAKE_PROFIT_X")
    paper_take_profit_fraction: float = Field(default=0.5, alias="PAPER_TAKE_PROFIT_FRACTION")
    paper_stall_minutes: int = Field(default=15, alias="PAPER_STALL_MINUTES")
    paper_max_hold_minutes: int = Field(default=240, alias="PAPER_MAX_HOLD_MINUTES")
    paper_cost_pct: float = Field(default=0.01, alias="PAPER_COST_PCT")  # издержки на сторону
    paper_interval_seconds: int = Field(default=10, alias="PAPER_INTERVAL_SECONDS")
    # --- Тренд ликвидности + быстрый выход (T2, рычаги ②⑤) ---
    # Падение ликвидности между срезами больше порога → не входить / немедленный выход.
    paper_liq_drop_pct: float = Field(default=0.15, alias="PAPER_LIQ_DROP_PCT")
    # Ускоренный опрос цены/ликвидности для ОТКРЫТЫХ позиций (вместо paper_interval).
    paper_open_poll_seconds: int = Field(default=5, alias="PAPER_OPEN_POLL_SECONDS")
    # Рост налога на продажу (абсолютные проценты) считается критическим изменением.
    paper_sell_tax_jump_pct: float = Field(default=5.0, alias="PAPER_SELL_TAX_JUMP_PCT")

    # --- Live-исполнение (Фаза 5). ВЫКЛЮЧЕНО по умолчанию. Реальные деньги. ---
    live_trading_enabled: bool = Field(default=False, alias="LIVE_TRADING_ENABLED")
    live_require_confirmation: bool = Field(default=True, alias="LIVE_REQUIRE_CONFIRMATION")
    live_daily_cap_usd: float = Field(default=0.0, alias="LIVE_DAILY_CAP_USD")  # 0 = трат нет
    live_max_trade_usd: float = Field(default=0.0, alias="LIVE_MAX_TRADE_USD")
    live_wallet_address: str = Field(default="", alias="LIVE_WALLET_ADDRESS")
    live_private_rpc: str = Field(default="", alias="LIVE_PRIVATE_RPC")

    # --- Аккаунты и сессии ---
    jwt_secret: str = Field(default="dev-insecure-change-me", alias="JWT_SECRET")
    # Админы: список идентификаторов (subject кошелька/google/telegram ИЛИ email), через запятую.
    admin_identifiers: str = Field(default="", alias="ADMIN_IDENTIFIERS")
    session_ttl_hours: int = Field(default=720, alias="SESSION_TTL_HOURS")  # 30 дней
    # Google OAuth
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(default="", alias="GOOGLE_REDIRECT_URI")
    # Telegram login использует telegram_bot_token (ниже).

    # --- Биллинг: NOWPayments (крипто) ---
    nowpayments_api_key: str = Field(default="", alias="NOWPAYMENTS_API_KEY")
    nowpayments_ipn_secret: str = Field(default="", alias="NOWPAYMENTS_IPN_SECRET")
    nowpayments_base_url: str = Field(
        default="https://api.nowpayments.io/v1", alias="NOWPAYMENTS_BASE_URL"
    )

    # --- ИИ-слой новостей (Фаза 4) ---
    ai_enabled: bool = Field(default=False, alias="AI_ENABLED")  # без ключа → фолбэк по правилам
    ai_base_url: str = Field(default="https://api.openai.com/v1", alias="AI_BASE_URL")
    ai_api_key: str = Field(default="", alias="AI_API_KEY")
    ai_model: str = Field(default="gpt-4o-mini", alias="AI_MODEL")
    news_feeds: str = Field(default="", alias="NEWS_FEEDS")  # запятая-разделённые RSS-URL
    news_batch_size: int = Field(default=25, alias="NEWS_BATCH_SIZE")
    news_interval_seconds: int = Field(default=120, alias="NEWS_INTERVAL_SECONDS")

    # --- Контент-движок: SEO-статьи из новостей (оригинальный разбор, не копия) ---
    content_enabled: bool = Field(default=True, alias="CONTENT_ENABLED")
    articles_per_day: int = Field(default=5, alias="ARTICLES_PER_DAY")  # тем/день
    content_lang: str = Field(default="en", alias="CONTENT_LANG")
    # Языки SEO-статей: на каждую тему генерируем версию на каждом языке.
    content_langs_raw: str = Field(default="en,ru", alias="CONTENT_LANGS")
    site_url: str = Field(default="https://altsr.app", alias="SITE_URL")

    @property
    def content_langs(self) -> list[str]:
        seen: list[str] = []
        for x in self.content_langs_raw.split(","):
            v = x.strip().lower()
            if v and v not in seen:
                seen.append(v)
        return seen or [self.content_lang]

    # --- Metricool: авто-постинг статей в соцсети (OFF по умолчанию) ---
    metricool_enabled: bool = Field(default=False, alias="METRICOOL_ENABLED")
    metricool_base_url: str = Field(
        default="https://app.metricool.com/api", alias="METRICOOL_BASE_URL"
    )
    metricool_user_token: str = Field(default="", alias="METRICOOL_USER_TOKEN")
    metricool_user_id: str = Field(default="", alias="METRICOOL_USER_ID")
    metricool_blog_id: str = Field(default="", alias="METRICOOL_BLOG_ID")
    metricool_networks: str = Field(default="twitter,telegram", alias="METRICOOL_NETWORKS")
    social_posts_per_run: int = Field(default=3, alias="SOCIAL_POSTS_PER_RUN")

    @property
    def metricool_network_list(self) -> list[str]:
        return [n.strip() for n in self.metricool_networks.split(",") if n.strip()]

    @property
    def news_feed_list(self) -> list[str]:
        return [u.strip() for u in self.news_feeds.split(",") if u.strip()]

    # --- Telegram (уведомления) ---
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    telegram_api_base: str = Field(
        default="https://api.telegram.org", alias="TELEGRAM_API_BASE"
    )

    # Интервал поллинга discovery в секундах.
    poll_interval_seconds: int = Field(default=30, alias="POLL_INTERVAL_SECONDS")
    # TTL ключа дедупа в Redis (сек). За это время повторная вставка не плодит дубли.
    dedup_ttl_seconds: int = Field(default=86_400, alias="DEDUP_TTL_SECONDS")
    # Таймаут HTTP-запросов к внешним API.
    http_timeout_seconds: float = Field(default=15.0, alias="HTTP_TIMEOUT_SECONDS")
    # Макс. ретраев с backoff на внешние API.
    http_max_retries: int = Field(default=3, alias="HTTP_MAX_RETRIES")

    # Необязательные ключи (Фаза 1+). Пустые по умолчанию.
    birdeye_api_key: str = Field(default="", alias="BIRDEYE_API_KEY")
    helius_api_key: str = Field(default="", alias="HELIUS_API_KEY")

    # --- Birdeye: ранний discovery (new_listing). Ключ — только в .env/env. ---
    birdeye_enabled: bool = Field(default=False, alias="BIRDEYE_ENABLED")
    birdeye_base_url: str = Field(
        default="https://public-api.birdeye.so", alias="BIRDEYE_BASE_URL"
    )
    # Сети Birdeye для new_listing (их имена: solana, ethereum, base, bsc, ...).
    birdeye_chains: str = Field(default="solana", alias="BIRDEYE_CHAINS")
    birdeye_new_listing_limit: int = Field(default=20, alias="BIRDEYE_NEW_LISTING_LIMIT")

    @property
    def birdeye_chain_list(self) -> list[str]:
        return [c.strip().lower() for c in self.birdeye_chains.split(",") if c.strip()]

    @property
    def birdeye_active(self) -> bool:
        """Birdeye включается явным флагом ИЛИ самим наличием ключа (удобнее в настройке)."""
        return self.birdeye_enabled or bool(self.birdeye_api_key)

    # CORS для фронтенда.
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    @property
    def admin_identifier_list(self) -> list[str]:
        return [x.strip().lower() for x in self.admin_identifiers.split(",") if x.strip()]

    @property
    def gecko_network_list(self) -> list[str]:
        return [n.strip() for n in self.gecko_networks.split(",") if n.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
