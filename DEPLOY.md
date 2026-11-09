# ALTSR — деплой на сервер

Пошаговый подъём на VPS. По умолчанию — **постоянная бумажная торговля** (депозит $100 000).
Живая торговля реальными деньгами выключена (`LIVE_TRADING_ENABLED=false`) и включается
отдельно, только после живого прогона и бумажного трека.

## 1. Требования
- VPS (2 vCPU / 4 GB+), Docker + Docker Compose, домен (для HTTPS).
- Ключи: Helius/Solana RPC, EVM RPC, Etherscan/Basescan/BscScan, Birdeye (опц.), LLM (опц.),
  Telegram bot token + chat id (опц.). Discovery/safety работают и без платных ключей
  (GeckoTerminal/DexScreener/GoPlus/RugCheck/honeypot.is — без ключа, с rate-limit).

## 2. Подъём
```bash
git clone <repo> && cd altsr
cp .env.example .env            # заполнить ключи; PAPER_START_BALANCE уже 100000
docker compose up -d --build    # postgres, redis, backend, worker, screener, signals, paper, ai, frontend
docker compose exec backend alembic upgrade head
```
Сервисы:
- backend (FastAPI) :8000 · frontend (Next.js) :3000
- воркеры: **discovery** (лента), **screener** (анти-скам), **signals** (BUY + Telegram),
  **paper** (постоянная бумажная торговля), **ai** (новости).

## 3. HTTPS и домен
Поставить reverse-proxy (Caddy/Traefik/nginx) перед backend:8000 и frontend:3000, выпустить
TLS (Let's Encrypt). CORS в `.env` (`CORS_ORIGINS`) указать на домен фронта.

## 4. Smoke-тест (после старта)
```bash
bash scripts/smoke.sh http://localhost:8000
```
Проверяет health, что лента и вердикты наполняются, сигналы и бумажные позиции доступны.
Первый живой прогон против внешних API может вскрыть нюансы форматов — смотреть логи воркеров:
```bash
docker compose logs -f discovery screener signals paper ai
```

## 5. Эксплуатация
- **Бумажный P&L:** `GET /api/paper/summary`, позиции `GET /api/paper/positions`.
- **Рилс по позиции:** `GET /api/paper/positions/{id}/reel` — вертикальный анимированный HTML.
  Для mp4 — отрендерить этот HTML headless-браузером (см. §6).
- Мониторинг: healthcheck `GET /health`; следить за рестартами воркеров; бэкап Postgres
  (`pg_dump`) по расписанию; алерты на падения (Telegram/почта).

## 6. Рилсы в mp4 (опц.)
HTML рилса самодостаточен. Чтобы получить видео-файл на сервере:
```bash
# пример: headless-запись экрана через Playwright (установить отдельно)
#  1) открыть /api/paper/positions/{id}/reel
#  2) record_video или кадры → ffmpeg в mp4 1080x1920
```
(Ролик длится ~2.5 c анимации; записывать 3–6 c.)

## 7. Включение живой торговли (ТОЛЬКО после тестов)
Живое исполнение — Фаза 5, под фиче-флагом. По умолчанию OFF. Чтобы подготовить (не раньше,
чем накоплен бумажный трек):
1. Прогнать систему на живых API минимум несколько дней в бумаге, проверить честный P&L.
2. Подключить swap-адаптер (Jupiter/0x/1inch) в `app/live/executor.py:submit_swap` — он
   намеренно оставлен заглушкой, чтобы код не двигал реальные средства без осознанного подключения.
3. В `.env`: `LIVE_TRADING_ENABLED=true`, `LIVE_WALLET_ADDRESS`, `LIVE_PRIVATE_RPC`,
   `LIVE_MAX_TRADE_USD`, `LIVE_DAILY_CAP_USD`, `LIVE_REQUIRE_CONFIRMATION=true`.
4. Предохранители (safety PASS + honeypot-симуляция + лимиты + подтверждение + tx-симуляция)
   проверяются перед каждой сделкой; любой непройденный — отказ.

> ⚠️ Автозакуп реальными деньгами на новых токенах — крайне высокий риск полной потери
> средств (~98% новых токенов обнуляются). Не инвест-рекомендация. Решение и риск — на владельце.
```
```
