#!/bin/bash
# start.sh — Launch backend + dashboard in one shot
set -e

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
DASHBOARD_DIR="$REPO_ROOT/dashboard"

# ── 1. Start backend (detached) ─────────────────────────────────────────────
echo "▶ Starting backend (DB + LocalStack + API)..."
cd "$REPO_ROOT"
docker compose up --build -d

# ── 2. Wait for API to be ready ──────────────────────────────────────────────
echo "⏳ Waiting for API to be healthy..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/healthz > /dev/null 2>&1; then
    echo "✅ API is ready."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "❌ API did not start in time. Check logs: docker compose logs app"
    exit 1
  fi
  sleep 3
done

# ── 3. Seed demo tenant + admin user (idempotent) ───────────────────────────
echo "🌱 Seeding demo data..."
# Run on host Python — DB is exposed on localhost:5433
DATABASE_URL="postgresql+asyncpg://mdm:mdm@localhost:5433/mdmdb" \
  python3 "$REPO_ROOT/scripts/seed_db.py"

# ── 4. Start Next.js dashboard in foreground ────────────────────────────────
echo "▶ Starting dashboard on http://localhost:3000 ..."
cd "$DASHBOARD_DIR"
npm run dev
