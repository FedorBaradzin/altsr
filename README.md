# ALTSR — Early Token Radar

Платформа раннего обнаружения новых криптотокенов с анти-скам скринингом и
**бумажной** симуляцией сигналов. Строится итерациями по фазам из мастер-промта.

> ⚠️ **Не инвест-рекомендация.** Торговля новыми токенами — крайне высокий риск
> полной потери средств. ~98% новых токенов обнуляются. Проект про скрининг и
> симуляцию, а не про прогноз прибыли. Реальных денег в коде нет: исполнение —
> только бумажное, живая торговля — отдельная фаза под фиче-флагом (ещё не здесь).

## Что готово

### Админ-панель `/admin`
Доступ только администратору (`ADMIN_IDENTIFIERS` — ваш кошелёк/google-sub/telegram-id или email).
- **Обзор:** счётчики (пользователи, оплаты, токены, сигналы, позиции, статьи, новости) + бумажный P&L.
- **Пользователи:** список + **ручная выдача тарифа** (free/pro/trader/team).
- **Платежи:** последние счёта NOWPayments и их статусы.
- **Флаги:** текущее состояние (live OFF, AI, Metricool, Telegram/Google/NOWPayments настроены ли).
API `/api/admin/*` под `require_admin`.

### Онлайн-консультант, онбординг-тур и соц-постинг
- **Консультант 24/7:** чат-виджет на всех страницах (`/api/assistant/chat`). Отвечает про
  скрининг, сигналы, бумагу, тарифы — на нашем LLM, **с FAQ-фолбэком без ключа**. Жёсткие
  правила: никаких инвест-рекомендаций и прогнозов цены, всегда дисклеймер.
- **Онбординг:** при первом входе в `/app` — приветствие и **опциональный тур** по интерфейсу
  (подсветка: аккаунт, бумажный счёт, лента, вердикты, сигналы, консультант). Кнопка «🧭 Тур»
  перезапускает в любой момент.
- **Metricool (OFF по умолчанию):** авто-постинг SEO-статей в соцсети по API (инвойс/расписание),
  `METRICOOL_ENABLED=true` + токен включают. Это не консультант — Metricool только про соцсети.

### Аккаунты и биллинг (платный вход)
- **Вход:** кошелёк (EVM personal_sign, nonce → подпись → сессия), Google OAuth, Telegram Login
  (проверка HMAC). Сессии — подписанные токены (HMAC-SHA256, срок).
- **Тарифы:** Free / Pro $29 / Trader $79 / Team-API $199 (`/api/billing/tiers`).
- **Оплата:** NOWPayments (крипто). `POST /api/billing/checkout` → инвойс; `POST /api/billing/ipn`
  (вебхук) с проверкой подписи HMAC-SHA512 → апгрейд тарифа.
- **Гейтинг:** `require_tier(...)` по рангу тарифа с учётом срока. `/api/me` — профиль + тариф.
- **Фронт:** `/login` (три кнопки входа), `/pricing` (тарифы + оплата криптой), в дашборде —
  состояние аккаунта и подхват токена из редиректа.

### Фронтенд «Crypto Neural Universe» (Next.js, на живых данных)
- `/` — иммерсивный лендинг с **живой 3D-галактикой** (Three.js, параллакс, фолбэки
  reduced-motion / без WebGL) + копия и пайплайн.
- `/app` — космический дашборд на **живых данных** из `/api/*`: лента токенов с вердиктами и
  сигналами, панели Сигналы/Новости, строка бумажного P&L, drawer Token Intelligence
  (risk-ring + red flags из `/api/tokens/{id}/safety`), кнопки «купить».
- `/blog`, `/blog/{slug}` — SEO-блог (см. ниже). Единый glass-стиль, адаптив, доступность.

### SEO + контент-движок + блог
- **Контент-движок:** новости → **оригинальные** SEO-статьи (не копия источника; с ссылкой-
  атрибуцией и дисклеймером). LLM + офлайн-фолбэк. Дневная планка (`ARTICLES_PER_DAY=5`). API
  `GET /api/articles`, `GET /api/articles/{slug}`.
- **SEO фронта (Next.js):** английские title/description, Open Graph/Twitter, `robots.txt`,
  динамический `sitemap.xml` (с блогом), hreflang en/ru, JSON-LD NewsArticle. Блог `/blog` и
  `/blog/{slug}` рендерят статьи с полным SEO.
- Тарифы/платный вход — предложение в `pricing.md` (проект).

### Деплой + рилсы + каркас live (OFF)
- **Готово к серверу:** `DEPLOY.md` (пошаговый подъём на VPS, HTTPS, мониторинг) +
  `scripts/smoke.sh` (проверка health/ленты/сигналов/бумаги/новостей после старта).
- **Депозит $100 000**, постоянная бумажная торговля (воркеры работают 24/7).
- **Рилсы:** `GET /api/paper/positions/{id}/reel` — вертикальный анимированный ролик по
  сделке/позиции в фирменном стиле (как запись экрана: токен, вход→выход, count-up P&L,
  вердикт, причина выхода, частицы). Для mp4 — рендер HTML headless-браузером (см. DEPLOY.md §6).
- **Live-исполнение (Фаза 5): каркас готов, ВЫКЛЮЧЕН** (`LIVE_TRADING_ENABLED=false`).
  Многослойные предохранители (safety PASS + honeypot-симуляция + лимиты + подтверждение +
  tx-симуляция); реальный swap намеренно оставлен заглушкой. Включать только после тестов.

### Фаза 4 — ИИ-слой (прогон новостей)
- Ингест новостей из RSS-фидов (`NEWS_FEEDS`) → дедуп по url → классификация.
- **Классификатор катализаторов**: тип (listing/partnership/audit/unlock/exploit/delisting/other),
  тональность (−1..+1), срочность (low/med/high), статус достоверности. LLM-путь при
  `AI_ENABLED`+ключе; **без ключа — детерминированный фолбэк по правилам** (система работает и офлайн).
- Строгий JSON от LLM с валидацией схемы; при любой ошибке — откат на правила.
- API `GET /api/news` (фильтры urgency/catalyst). Воркер `ai`.

### Фаза 3 — paper_executor (бумажная покупка + выходы)
- По BUY-сигналу открывается **бумажная** позиция (реальных денег нет).
- **Цепочка выходов** по приоритету: hard stop → trailing от пика (после арминга +X%) →
  take-profit (частичный) → stall (нет хая N мин) → time exit. Это и есть «выход при
  падении» — от пика, с армингом и учётом издержек круга (`cost_pct`), чтобы не сливать на шуме.
- Дневной лимит убытка (→ стоп новых покупок), лимит числа позиций, прайс-фид DexScreener.
- **Честная сводка P&L**: equity, return %, realized/unrealized, win-rate, avg win/loss.
- **Прогноз-план** (НЕ прогноз прибыли): что бот сделает с позицией — в сводке и Telegram-алерте.
- API: `GET /api/paper/summary`, `GET /api/paper/positions`. Воркер `paper`. На фронте — панель счёта.

### Фаза 2 — signal_engine + «где и как купить»
- Движок входа: ворота fail-fast (safety PASS → risk ≤ порог → ликвидность ≥ мин →
  возраст в окне → холдеры) → **BUY-сигнал** с причинами и **уверенностью** 0–1.
- Для каждого сигнала — блок **«Где и как купить»**: прямые swap-ссылки (Jupiter для
  Solana, Uniswap для EVM, PancakeSwap для BSC), страница пары DexScreener/GeckoTerminal,
  эксплорер; опц. live-список DEX-площадок из DexScreener.
- **Telegram-алерты** на новые BUY-сигналы с ссылками «как купить» и дисклеймером
  (без токена/чата — тихо отключены).
- API: `GET /api/signals` (фильтры chain/min_confidence), `GET /api/tokens/{id}/venues`
  (`?live=true` — подтянуть площадки). В ленте — значок `⚡ BUY NN%` и кнопка «купить».
- Отдельный воркер `signals`; сигнал один на токен (антидубль).

### Фаза 1 — safety_screen (анти-скам)
Каждый новый токен автоматически скринится и получает вердикт **PASS / REVIEW / BLOCK**
+ `risk_score` (0–100) + список `red_flags[]`.
- **EVM:** GoPlus (honeypot, buy/sell tax, mint authority, owner-привилегии, blacklist,
  proxy, holders) + honeypot.is (симуляция buy/sell).
- **Solana:** GoPlus (mint/freeze authority) + RugCheck (LP-lock, концентрация, rugged).
- **HARD-BLOCK** правила: honeypot, sell_tax>15%, активная mint authority, владелец может
  менять балансы, топ-1 холдер >50%, LP не залочен, rugged.
- **SOFT-FLAG** с весами копятся в `risk_score`; нет данных → не PASS (честно: REVIEW).
- Отдельный воркер `screener` берёт неоскоренные токены батчами и пишет `safety_reports`.
- API: вердикт в ленте (`/api/tokens`, фильтры `verdict`, `max_risk`) + полный отчёт
  `GET /api/tokens/{id}/safety`. На фронте — цветной бейдж вердикта и фильтр.

### Фаза 0 — discovery
Лента «только что появившихся» токенов: сбор из нескольких источников →
нормализация в единую модель → дедуп → PostgreSQL → REST + WebSocket → экран.

- **discovery-воркер** 24/7 поллит источники, идемпотентно пишет в БД, публикует
  новинки в Redis pub/sub.
- **Источники:** GeckoTerminal `new_pools` (EVM + Solana, без ключа),
  RugCheck `stats/new_tokens` (Solana), DexScreener `token-profiles` (обогащение).
- **Дедуп в два слоя:** быстрый Redis `SET NX EX` + `UNIQUE(chain,address)` в БД
  как источник истины (повторный прогон обновляет строку, а не плодит дубли).
- **API:** `GET /api/tokens` (фильтры chain / min_liquidity / пагинация),
  `GET /health`, `WS /ws/tokens` (живая лента, первым сообщением — дисклеймер).
- **Frontend:** Next.js 14, лента с фильтрами, live-индикатор, ссылки на эксплореры.

## Стек

Backend — Python 3.12 + FastAPI + SQLAlchemy 2.x (async) + Pydantic v2 + httpx;
PostgreSQL (asyncpg, Alembic) + Redis. Frontend — Next.js 14 + TypeScript +
Tailwind. Инфра — Docker Compose + GitHub Actions.

## Быстрый старт

```bash
cp .env.example .env          # ключи/урлы; реальные значения не коммитить
docker compose up --build     # postgres, redis, backend, worker, frontend
```

- Фронтенд: http://localhost:3000
- API-дока (Swagger): http://localhost:8000/docs
- Воркер начинает наполнять ленту сам, с интервалом `POLL_INTERVAL_SECONDS`.

### Локально без Docker (backend)

```bash
cd backend
pip install ".[dev]"
export DATABASE_URL=postgresql+asyncpg://altsr:altsr@localhost:5432/altsr
export REDIS_URL=redis://localhost:6379/0
alembic upgrade head
uvicorn app.main:app --reload          # API
python -m app.worker                   # discovery-воркер (в отдельном терминале)
```

## Тесты

```bash
cd backend && pytest -q
```

Тесты идут на записанных фикстурах (`tests/fixtures/*.json`), без обращения к живым
API, и покрывают критерий приёмки Фазы 0: нормализация источников, дедуп в пачке,
дедуп между источниками, дедуп между прогонами, устойчивость тика к падению одного
источника, REST-фильтры.

## Структура

```
altsr/
├── backend/
│   ├── app/
│   │   ├── config.py           настройки (.env), секретов в коде нет
│   │   ├── db.py / models.py    async-БД + модель tokens (UNIQUE chain,address)
│   │   ├── schemas.py           Pydantic-схемы ответа
│   │   ├── api/tokens.py        REST-лента + отчёт безопасности
│   │   ├── main.py              FastAPI + WebSocket живой ленты
│   │   ├── worker.py            entrypoint discovery-воркера
│   │   ├── screen_worker.py     entrypoint safety-воркера
│   │   ├── discovery/
│   │   │   ├── base.py          NormalizedToken + HTTP-клиент с ретраями/backoff
│   │   │   ├── geckoterminal.py / rugcheck.py / dexscreener.py
│   │   │   ├── dedup.py         идемпотентный upsert
│   │   │   └── runner.py        тик поллинга + pub/sub
│   │   ├── safety/
│   │   │   ├── base.py          SafetyFindings / RedFlag / SafetyResult
│   │   │   ├── goplus.py / rugcheck.py / honeypot_is.py
│   │   │   ├── scoring.py       HARD-BLOCK/SOFT-FLAG → risk_score + вердикт
│   │   │   ├── screener.py      оркестратор + запись отчёта
│   │   │   └── runner.py        тик скрининга + pub/sub
│   │   ├── signals/
│   │   │   ├── engine.py        ворота входа → BUY + уверенность
│   │   │   ├── venues.py        «где и как купить» (ссылки + live DEX)
│   │   │   └── runner.py        воркер сигналов + Telegram
│   │   ├── notify/              Telegram + формат алерта
│   │   └── paper/
│   │       ├── exits.py         цепочка выходов + план (чистая логика)
│   │       ├── executor.py      открытие/ведение позиций, лимиты
│   │       ├── pricing.py       прайс-фид DexScreener
│   │       └── runner.py        тик бумажного исполнения
│   ├── alembic/                 миграции
│   └── tests/                   pytest + фикстуры
├── frontend/                    Next.js 14 лента
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## Честные рамки (закодированы в UI и дисклеймерах)

- Анти-скам снижает риск **кражи**, а не риск **обнуления**. «Не скам» ≠ «вырастет».
- Детекция ловит часть схем, не все; slow-rug и новые паттерны проскакивают.
- «Реальный проект vs скам» автоматизируется лишь частично.

## Дорожная карта

- **Фаза 0 (готово):** лента + дедуп + БД + экран.
- **Фаза 1 (готово):** `safety_screen` — GoPlus / RugCheck / Honeypot.is → `risk_score` +
  `red_flags[]` + вердикт PASS/REVIEW/BLOCK, HARD-BLOCK правила, тесты.
- **Фаза 2 (готово):** `signal_engine` — BUY-сигналы + «где и как купить» + Telegram-алерты.
- **Фаза 3 (готово):** `paper_executor` — бумажные позиции, цепочка выходов, дневные лимиты, P&L.
- **Фаза 4 (готово):** ИИ-слой — прогон новостей, классификация катализаторов (LLM + фолбэк).
- **Фаза 5 (каркас, OFF):** live-исполнение под фиче-флагом с предохранителями; рилсы сделок; deploy.

Дизайн платформы и моушн-интро — отдельными артефактами в этом же чате.
- **Фаза 3:** `paper_executor` — бумажные позиции, TP/SL/trailing/stall, дневные
  лимиты, честная сводка P&L.
- **Позже (OFF по умолчанию):** реальное исполнение под фиче-флагом.
