#!/bin/bash
set -euo pipefail

# Restore PostgreSQL and Qdrant from backup.
# Usage: ./scripts/restore.sh <pg_dump.sql.gz> [qdrant_snapshot]

PG_DUMP="${1:?Usage: restore.sh <pg_dump.sql.gz> [qdrant_snapshot]}"
QDRANT_SNAPSHOT="${2:-}"
COMPOSE_DIR="${COMPOSE_DIR:-/opt/vue-mcp}"

echo "=== Restore started at $(date) ==="

# 1. Restore PostgreSQL
echo "Restoring PostgreSQL from $PG_DUMP..."
gunzip -c "$PG_DUMP" | docker compose -f "$COMPOSE_DIR/docker-compose.prod.yml" exec -T postgres \
  psql -U vue_mcp -d vue_mcp
echo "  PostgreSQL restored."

# 2. Restore Qdrant (optional)
if [ -n "$QDRANT_SNAPSHOT" ]; then
  echo "Restoring Qdrant from $QDRANT_SNAPSHOT..."
  # Delete existing collection first
  curl -sf -X DELETE "http://localhost:6333/collections/vue_ecosystem" || true
  # Upload snapshot
  curl -sf -X POST "http://localhost:6333/collections/vue_ecosystem/snapshots/upload" \
    -H "Content-Type: multipart/form-data" \
    -F "snapshot=@$QDRANT_SNAPSHOT"
  echo "  Qdrant restored."
fi

# 3. Restart server to reload data
echo "Restarting MCP server..."
docker compose -f "$COMPOSE_DIR/docker-compose.prod.yml" restart mcp-server
echo "  Server restarted."

echo "=== Restore complete at $(date) ==="
