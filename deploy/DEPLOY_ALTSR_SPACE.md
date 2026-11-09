# Деплой ALTSR на altsr.space (Hostinger KVM VPS)

Пошагово. Всё, что в блоках `bash`, выполняется на сервере (терминал Hostinger или SSH).

## 0. DNS (в панели, где куплен домен)
Создайте A-записи на **IP вашего VPS** (его видно в hPanel → VPS → Overview):
```
A   @     <IP_сервера>
A   www   <IP_сервера>
```
Подождите 5–30 минут, пока DNS применится.

## 1. Подготовить сервер
```bash
# под root или sudo
apt update && apt -y upgrade
apt -y install docker.io docker-compose-plugin git
systemctl enable --now docker

# firewall: наружу только SSH + web
apt -y install ufw
ufw allow 22 && ufw allow 80 && ufw allow 443
ufw --force enable
```

## 2. Залить проект
Вариант А — через git (если выложите репозиторий):
```bash
cd /opt && git clone <URL_репозитория> altsr && cd altsr
```
Вариант Б — загрузить zip (из hPanel File Manager или scp), затем:
```bash
cd /opt && unzip altsr_*.zip && cd altsr
```

## 3. Настроить .env
```bash
cp deploy/.env.altsr.space .env
nano .env     # заполнить JWT_SECRET, ADMIN_IDENTIFIERS, AI_API_KEY и ключи сервисов
```
Сгенерировать JWT_SECRET: `openssl rand -hex 32`

## 4. Поднять
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec backend alembic upgrade head
```
Caddy сам выпустит HTTPS-сертификат для altsr.space (нужно, чтобы DNS уже указывал на сервер).

## 5. Проверить
```bash
bash scripts/smoke.sh http://localhost:8000
docker compose logs -f discovery screener signals paper ai   # первые минуты — смотрим на живые API
```
Откройте https://altsr.space — лендинг с галактикой; https://altsr.space/app — дашборд;
https://altsr.space/admin — админка (ваш ADMIN_IDENTIFIERS).

## 6. Внешние сервисы (callback-URL уже прописаны под altsr.space)
- **Google OAuth** (console.cloud.google.com): Authorized redirect URI =
  `https://altsr.space/api/auth/google/callback`. Client ID/Secret → в .env.
- **Telegram**: @BotFather → создать бота, `TELEGRAM_BOT_TOKEN` → .env, `NEXT_PUBLIC_TELEGRAM_BOT` = username бота;
  в BotFather `/setdomain` → altsr.space.
- **NOWPayments**: кабинет → API key + IPN secret → .env; IPN callback = `https://altsr.space/api/billing/ipn`.

## Обновление позже
```bash
cd /opt/altsr && git pull   # или перезалить zip
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec backend alembic upgrade head
```

## Если что-то не так
- `docker compose ps` — статус сервисов; `docker compose logs <service>` — логи.
- HTTPS не выпустился → проверьте, что A-записи указывают на сервер и порт 80 открыт (ufw).
- Фронт бьёт в localhost → значит `.env` с `NEXT_PUBLIC_*` не был на месте при сборке; пересоберите:
  `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build frontend`.
Присылайте вывод команды — подскажу следующий шаг.
