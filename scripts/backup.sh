#!/bin/bash
set -euo pipefail

# Backup PostgreSQL and Qdrant data.
# Works with any compose file (prod, local, dev) by routing all calls through
# Docker exec instead of assuming localhost port access.
#
# Usage: ./scripts/backup.sh [backup_dir] [compose_file] [env_file]
# Schedule via cron: 0 3 * * * /opt/vue-mcp/scripts/backup.sh

BACKUP_DIR="${1:-/opt/backups/vue-mcp}"
COMPOSE_FILE="${2:-docker-compose.prod.yml}"
ENV_FILE="${3:-.env.production}"
DATE=$(date +%Y%m%d-%H%M%S)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# When deployed flat to /opt/vue-mcp/, SCRIPT_DIR == COMPOSE_DIR.
# When run from repo, scripts/ is one level down from the compose files.
if [ -f "$SCRIPT_DIR/$COMPOSE_FILE" ]; then
  COMPOSE_DIR="${COMPOSE_DIR:-$SCRIPT_DIR}"
else
  COMPOSE_DIR="${COMPOSE_DIR:-$(dirname "$SCRIPT_DIR")}"
fi
ERRORS=0

# Build compose command with optional env file
COMPOSE_CMD="docker compose -f $COMPOSE_DIR/$COMPOSE_FILE"
if [ -f "$COMPOSE_DIR/$ENV_FILE" ]; then
  COMPOSE_CMD="$COMPOSE_CMD --env-file $COMPOSE_DIR/$ENV_FILE"
fi

mkdir -p "$BACKUP_DIR"

echo "=== Backup started at $(date) ==="
echo "  Compose: $COMPOSE_FILE, env: $ENV_FILE"

# 1. PostgreSQL dump
echo "Dumping PostgreSQL..."
PG_FILE="$BACKUP_DIR/pg-$DATE.sql.gz"
$COMPOSE_CMD exec -T postgres pg_dump -U vue_mcp vue_mcp | gzip > "$PG_FILE"

if [ ! -s "$PG_FILE" ]; then
  echo "  [ERROR] PostgreSQL dump is empty or failed"
  rm -f "$PG_FILE"
  ERRORS=$((ERRORS + 1))
else
  echo "  Saved: pg-$DATE.sql.gz ($(du -h "$PG_FILE" | cut -f1))"
fi

# 2. Qdrant snapshot (via mcp-server container which can reach qdrant)
echo "Creating Qdrant snapshot..."
QDRANT_FILE="$BACKUP_DIR/qdrant-$DATE.snapshot"
SNAP_NAME=$($COMPOSE_CMD exec -T mcp-server python3 -c "
import urllib.request, json
req = urllib.request.Request('http://qdrant:6333/collections/vue_ecosystem/snapshots', method='POST')
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
print(data['result']['name'])
" 2>/dev/null || true)

if [ -n "$SNAP_NAME" ]; then
  $COMPOSE_CMD exec -T mcp-server python3 -c "
import urllib.request, sys
resp = urllib.request.urlopen('http://qdrant:6333/collections/vue_ecosystem/snapshots/$SNAP_NAME')
sys.stdout.buffer.write(resp.read())
" > "$QDRANT_FILE" 2>/dev/null

  if [ ! -s "$QDRANT_FILE" ]; then
    echo "  [ERROR] Qdrant snapshot is empty"
    rm -f "$QDRANT_FILE"
    ERRORS=$((ERRORS + 1))
  else
    echo "  Saved: qdrant-$DATE.snapshot ($(du -h "$QDRANT_FILE" | cut -f1))"
  fi
else
  echo "  [ERROR] Qdrant snapshot failed (is mcp-server running?)"
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
