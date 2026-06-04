#!/bin/bash

# Backend + Supabase cleanup validation.
# This validates the current FastAPI + Supabase clean-baseline structure.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

errors=0

ok() {
  echo -e "${GREEN}[ok]${NC} $1"
}

warn() {
  echo -e "${YELLOW}[warn]${NC} $1"
}

fail() {
  echo -e "${RED}[fail]${NC} $1"
  errors=$((errors + 1))
}

check_file() {
  local path="$1"
  if [ -f "$path" ]; then
    ok "file exists: $path"
  else
    fail "missing file: $path"
  fi
}

check_dir() {
  local path="$1"
  if [ -d "$path" ]; then
    ok "directory exists: $path"
  else
    fail "missing directory: $path"
  fi
}

echo "Starting Backend + Supabase validation"

check_dir "backend"
check_dir "frontend"
check_dir "supabase/migrations"

check_file "backend/web.py"
check_file "backend/apis/activities.py"
check_file "backend/core/activities/repo.py"
check_file "backend/core/activities/service.py"
check_file "backend/core/activities/agent.py"
check_file "backend/schemas/activities.py"
check_file "supabase/migrations/20241120_initial_schema.sql"
check_file "supabase/migrations/20241120_rls_policies.sql"
check_file "supabase/config_managements_seed.sql"
check_file "supabase/README.md"
check_file "backend/README.md"
check_file "backend/requirements.txt"
check_file "docker-compose.yaml"

echo ""
echo "Checking Supabase SQL text"

if grep -q "create table.*public.events" supabase/migrations/*.sql; then
  fail "old public.events table creation still exists"
else
  ok "no public.events table creation"
fi

if grep -q "create table.*public.auth_sessions" supabase/migrations/*.sql; then
  fail "old public.auth_sessions table creation still exists"
else
  ok "no old auth_sessions table creation"
fi

if grep -q "create table if not exists public.activities" supabase/migrations/20241120_initial_schema.sql; then
  ok "activities table exists in baseline"
else
  fail "activities table missing from baseline"
fi

if grep -q "wechat_auth_sessions" supabase/migrations/20241120_initial_schema.sql; then
  ok "wechat auth session tables exist in baseline"
else
  fail "wechat auth session tables missing from baseline"
fi

if grep -q "'article-images'" supabase/migrations/20241120_initial_schema.sql; then
  ok "article-images bucket default exists"
else
  fail "article-images bucket default missing"
fi

echo ""
echo "Checking backend naming"

if [ -d "backend/core/events" ] || [ -f "backend/apis/events.py" ] || [ -f "backend/schemas/events.py" ]; then
  fail "old events backend modules still exist"
else
  ok "old events backend modules are removed"
fi

if grep -R "core\.events\|apis\.events\|schemas\.events\|EVENT_TABLE = \"events\"" backend --exclude-dir=.venv --exclude-dir=__pycache__ >/dev/null 2>&1; then
  fail "old events imports/table references still exist"
else
  ok "no old events imports/table references"
fi

if grep -R "is_gathered\|profiles\.avatar_url" backend supabase --exclude-dir=.venv --exclude-dir=__pycache__ >/dev/null 2>&1; then
  fail "old article/profile fields still referenced in backend or Supabase SQL"
else
  ok "no old is_gathered/profile avatar_url references"
fi

echo ""
echo "Checking Python compilation"

if python -m compileall -q backend/apis backend/core backend/driver backend/jobs backend/schemas backend/init_sys.py backend/web.py; then
  ok "backend Python compilation passed"
else
  fail "backend Python compilation failed"
fi

echo ""
echo "Checking FastAPI route registration"

if [ -x "backend/.venv/bin/python" ]; then
  ROUTE_OUTPUT=$(backend/.venv/bin/python -c "import sys; sys.path.insert(0, 'backend'); from web import app; paths=sorted({r.path for r in app.routes if hasattr(r,'path')}); print([p for p in paths if '/activities' in p]); print([p for p in paths if '/events' in p])" 2>/dev/null || true)
  if echo "$ROUTE_OUTPUT" | grep -q "/activities" && ! echo "$ROUTE_OUTPUT" | grep -q "/events"; then
    ok "FastAPI registers /activities and no /events"
  else
    fail "FastAPI route registration check failed"
  fi
else
  warn "backend/.venv/bin/python not found; skipped FastAPI import check"
fi

echo ""
echo "Checking requirements and package manager drift"

if grep -q "^psycopg2-binary=[^=]" backend/requirements.txt; then
  fail "backend/requirements.txt has invalid psycopg2-binary pin syntax"
else
  ok "backend/requirements.txt psycopg2-binary pin syntax is valid"
fi

lockfiles=0
[ -f "frontend/package-lock.json" ] && lockfiles=$((lockfiles + 1))
[ -f "frontend/pnpm-lock.yaml" ] && lockfiles=$((lockfiles + 1))
[ -f "frontend/yarn.lock" ] && lockfiles=$((lockfiles + 1))

if [ "$lockfiles" -gt 1 ]; then
  warn "frontend has multiple lockfiles; cleanup spec recommends keeping one package manager"
else
  ok "frontend lockfile count is consistent"
fi

echo ""
echo "Validation summary"
echo "=================="

if [ "$errors" -eq 0 ]; then
  ok "validation passed"
  exit 0
fi

fail "$errors validation error(s)"
exit 1
