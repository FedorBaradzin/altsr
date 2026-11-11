FROM caddy:2-alpine
# Пекём Caddyfile в образ, чтобы не зависеть от bind-mount (managed Docker его не поддерживает).
COPY Caddyfile /etc/caddy/Caddyfile
# Статические юридические страницы (/privacy, /terms) — тоже в образ.
COPY legal /srv/legal
