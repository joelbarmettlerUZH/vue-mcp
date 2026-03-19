#!/bin/bash
set -euo pipefail

# Backup PostgreSQL and Qdrant data.
# Usage: ./scripts/backup.sh [backup_dir]
# Schedule via cron: 0 3 * * * /opt/vue-mcp/scripts/backup.sh

BACKUP_DIR="${1:-/opt/backups/vue-mcp}"
DATE=$(date +%Y%m%d-%H%M%S)
COMPOSE_DIR="${COMPOSE_DIR:-/opt/vue-mcp}"

mkdir -p "$BACKUP_DIR"

echo "=== Backup started at $(date) ==="

# 1. PostgreSQL dump
echo "Dumping PostgreSQL..."
docker compose -f "$COMPOSE_DIR/docker-compose.yml" exec -T postgres \
  pg_dump -U vue_mcp vue_mcp | gzip > "$BACKUP_DIR/pg-$DATE.sql.gz"
echo "  Saved: pg-$DATE.sql.gz ($(du -h "$BACKUP_DIR/pg-$DATE.sql.gz" | cut -f1))"

# 2. Qdrant snapshot
echo "Creating Qdrant snapshot..."
SNAP_RESPONSE=$(curl -sf -X POST "http://localhost:6333/collections/vue_docs/snapshots" 2>/dev/null || true)
if [ -n "$SNAP_RESPONSE" ]; then
  SNAP_NAME=$(echo "$SNAP_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['name'])" 2>/dev/null || true)
  if [ -n "$SNAP_NAME" ]; then
    curl -sf "http://localhost:6333/collections/vue_docs/snapshots/$SNAP_NAME" \
      -o "$BACKUP_DIR/qdrant-$DATE.snapshot"
    echo "  Saved: qdrant-$DATE.snapshot ($(du -h "$BACKUP_DIR/qdrant-$DATE.snapshot" | cut -f1))"
  else
    echo "  [WARN] Could not parse snapshot name"
  fi
else
  echo "  [WARN] Qdrant snapshot failed (is Qdrant running?)"
fi

# 3. Rotate: keep last 7 backups
echo "Rotating old backups (keeping 7)..."
ls -t "$BACKUP_DIR"/pg-*.sql.gz 2>/dev/null | tail -n +8 | xargs -r rm -v
ls -t "$BACKUP_DIR"/qdrant-*.snapshot 2>/dev/null | tail -n +8 | xargs -r rm -v

echo "=== Backup complete at $(date) ==="
