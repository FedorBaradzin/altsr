#!/usr/bin/env bash
# Smoke-тест развёрнутого ALTSR. Использование: bash scripts/smoke.sh http://localhost:8000
set -euo pipefail
BASE="${1:-http://localhost:8000}"
pass=0; fail=0

check() {
  local name="$1"; local url="$2"; local jqf="${3:-}"
  local body
  if ! body=$(curl -fsS "$url" 2>/dev/null); then
    echo "  ✗ $name — запрос не удался ($url)"; fail=$((fail+1)); return
  fi
  if [ -n "$jqf" ] && command -v jq >/dev/null; then
    if echo "$body" | jq -e "$jqf" >/dev/null 2>&1; then
      echo "  ✓ $name"; pass=$((pass+1))
    else
      echo "  ✗ $name — ответ не прошёл проверку ($jqf)"; fail=$((fail+1))
    fi
  else
    echo "  ✓ $name"; pass=$((pass+1))
  fi
}

echo "ALTSR smoke-тест → $BASE"
check "health"            "$BASE/health"                     '.status=="ok"'
check "лента токенов"     "$BASE/api/tokens?limit=5"         '.items|type=="array"'
check "сигналы"           "$BASE/api/signals?limit=5"        '.items|type=="array"'
check "бумажная сводка"   "$BASE/api/paper/summary"          '.start_balance>=100000'
check "позиции"           "$BASE/api/paper/positions?limit=5" '.items|type=="array"'
check "новости"           "$BASE/api/news?limit=5"           '.items|type=="array"'

echo "Итог: $pass ok, $fail ошибок"
[ "$fail" -eq 0 ] || exit 1
