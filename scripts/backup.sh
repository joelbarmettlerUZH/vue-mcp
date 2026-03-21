#!/bin/bash
set -euo pipefail

# Backup PostgreSQL and Qdrant data.
# Usage: ./scripts/backup.sh [backup_dir]
# Schedule via cron: 0 3 * * * /opt/vue-mcp/scripts/backup.sh

BACKUP_DIR="${1:-/opt/backups/vue-mcp}"
DATE=$(date +%Y%m%d-%H%M%S)
COMPOSE_DIR="${COMPOSE_DIR:-/opt/vue-mcp}"
ERRORS=0

mkdir -p "$BACKUP_DIR"

echo "=== Backup started at $(date) ==="

# 1. PostgreSQL dump
echo "Dumping PostgreSQL..."
PG_FILE="$BACKUP_DIR/pg-$DATE.sql.gz"
docker compose -f "$COMPOSE_DIR/docker-compose.prod.yml" exec -T postgres \
  pg_dump -U vue_mcp vue_mcp | gzip > "$PG_FILE"

if [ ! -s "$PG_FILE" ]; then
  echo "  [ERROR] PostgreSQL dump is empty or failed"
  rm -f "$PG_FILE"
  ERRORS=$((ERRORS + 1))
else
  echo "  Saved: pg-$DATE.sql.gz ($(du -h "$PG_FILE" | cut -f1))"
fi

# 2. Qdrant snapshot
echo "Creating Qdrant snapshot..."
QDRANT_FILE="$BACKUP_DIR/qdrant-$DATE.snapshot"
SNAP_RESPONSE=$(curl -sf -X POST "http://localhost:6333/collections/vue_docs/snapshots" 2>/dev/null || true)
if [ -n "$SNAP_RESPONSE" ]; then
  SNAP_NAME=$(echo "$SNAP_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['name'])" 2>/dev/null || true)
  if [ -n "$SNAP_NAME" ]; then
    curl -sf "http://localhost:6333/collections/vue_docs/snapshots/$SNAP_NAME" \
      -o "$QDRANT_FILE"
    if [ ! -s "$QDRANT_FILE" ]; then
      echo "  [ERROR] Qdrant snapshot is empty"
      rm -f "$QDRANT_FILE"
      ERRORS=$((ERRORS + 1))
    else
      echo "  Saved: qdrant-$DATE.snapshot ($(du -h "$QDRANT_FILE" | cut -f1))"
    fi
  else
    echo "  [ERROR] Could not parse Qdrant snapshot name"
    ERRORS=$((ERRORS + 1))
  fi
else
  echo "  [ERROR] Qdrant snapshot failed (is Qdrant running?)"
  ERRORS=$((ERRORS + 1))
fi

# 3. Rotate: keep last 7 backups
echo "Rotating old backups (keeping 7)..."
ls -t "$BACKUP_DIR"/pg-*.sql.gz 2>/dev/null | tail -n +8 | xargs -r rm -v
ls -t "$BACKUP_DIR"/qdrant-*.snapshot 2>/dev/null | tail -n +8 | xargs -r rm -v

if [ "$ERRORS" -gt 0 ]; then
  echo "=== Backup completed with $ERRORS error(s) at $(date) ==="
  exit 1
fi

echo "=== Backup complete at $(date) ==="
