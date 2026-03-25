#!/bin/bash
set -euo pipefail

# Restore PostgreSQL and Qdrant from backup.
# Routes all calls through Docker exec instead of assuming localhost port access.
#
# Usage: ./scripts/restore.sh <pg_dump.sql.gz> [qdrant_snapshot] [compose_file] [env_file]

PG_DUMP="${1:?Usage: restore.sh <pg_dump.sql.gz> [qdrant_snapshot] [compose_file] [env_file]}"
QDRANT_SNAPSHOT="${2:-}"
COMPOSE_FILE="${3:-docker-compose.prod.yml}"
ENV_FILE="${4:-.env.production}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# When deployed flat to /opt/vue-mcp/, SCRIPT_DIR == COMPOSE_DIR.
# When run from repo, scripts/ is one level down from the compose files.
if [ -f "$SCRIPT_DIR/$COMPOSE_FILE" ]; then
  COMPOSE_DIR="${COMPOSE_DIR:-$SCRIPT_DIR}"
else
  COMPOSE_DIR="${COMPOSE_DIR:-$(dirname "$SCRIPT_DIR")}"
fi

# Build compose command with optional env file
COMPOSE_CMD="docker compose -f $COMPOSE_DIR/$COMPOSE_FILE"
if [ -f "$COMPOSE_DIR/$ENV_FILE" ]; then
  COMPOSE_CMD="$COMPOSE_CMD --env-file $COMPOSE_DIR/$ENV_FILE"
fi

echo "=== Restore started at $(date) ==="
echo "  Compose: $COMPOSE_FILE, env: $ENV_FILE"

# 1. Restore PostgreSQL
echo "Restoring PostgreSQL from $PG_DUMP..."
# Drop and recreate to avoid conflicts with existing data
$COMPOSE_CMD exec -T postgres psql -U vue_mcp -d postgres -c "
  SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'vue_mcp' AND pid <> pg_backend_pid();
" > /dev/null 2>&1 || true
$COMPOSE_CMD exec -T postgres dropdb -U vue_mcp --if-exists vue_mcp
$COMPOSE_CMD exec -T postgres createdb -U vue_mcp vue_mcp
gunzip -c "$PG_DUMP" | $COMPOSE_CMD exec -T postgres psql -U vue_mcp -d vue_mcp > /dev/null
echo "  PostgreSQL restored."

# Verify
ENTITY_COUNT=$($COMPOSE_CMD exec -T postgres psql -U vue_mcp -d vue_mcp -t -c "SELECT count(*) FROM entities;" 2>/dev/null | tr -d ' ')
echo "  Entities: $ENTITY_COUNT"

# 2. Restore Qdrant (optional)
if [ -n "$QDRANT_SNAPSHOT" ]; then
  echo "Restoring Qdrant from $QDRANT_SNAPSHOT..."

  # Copy snapshot into mcp-server container
  CONTAINER_NAME=$($COMPOSE_CMD ps -q mcp-server)
  docker cp "$QDRANT_SNAPSHOT" "$CONTAINER_NAME:/tmp/restore.snapshot"

  # Upload snapshot via mcp-server (which can reach qdrant on the Docker network)
  $COMPOSE_CMD exec -T mcp-server python3 -c "
import httpx
print('Uploading snapshot...', flush=True)
with open('/tmp/restore.snapshot', 'rb') as f:
    resp = httpx.post(
        'http://qdrant:6333/collections/vue_ecosystem/snapshots/upload?priority=snapshot',
        files={'snapshot': ('restore.snapshot', f, 'application/octet-stream')},
        timeout=300.0,
    )
print(f'Status: {resp.status_code}')
if resp.status_code != 200:
    print(f'Error: {resp.text}')
    exit(1)

# Verify
import urllib.request, json
resp = urllib.request.urlopen('http://qdrant:6333/collections/vue_ecosystem')
data = json.loads(resp.read())
print(f\"Points: {data['result']['points_count']}, Status: {data['result']['status']}\")
"
  echo "  Qdrant restored."
fi

# 3. Restart server to reload data
echo "Restarting MCP server..."
$COMPOSE_CMD restart mcp-server
echo "  Server restarted."

echo "=== Restore complete at $(date) ==="
