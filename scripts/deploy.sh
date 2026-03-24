#!/bin/bash
set -euo pipefail

# Deploy latest images to production server.
# Usage: DEPLOY_HOST=your-vm.example.com ./scripts/deploy.sh

REMOTE_HOST="${DEPLOY_HOST:?Set DEPLOY_HOST env var}"
REMOTE_USER="${DEPLOY_USER:-deploy}"
REMOTE_DIR="${DEPLOY_DIR:-/opt/vue-mcp}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Deploying to ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}"

# Sync compose file and helper scripts
echo "Syncing configuration files..."
scp -q \
  "$PROJECT_ROOT/docker-compose.prod.yml" \
  "$PROJECT_ROOT/scripts/backup.sh" \
  "$PROJECT_ROOT/scripts/restore.sh" \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

ssh "${REMOTE_USER}@${REMOTE_HOST}" <<COMMANDS
  set -euo pipefail
  cd "${REMOTE_DIR}"
  docker compose --env-file .env.production -f docker-compose.prod.yml pull
  docker compose --env-file .env.production -f docker-compose.prod.yml up -d --remove-orphans
  docker image prune -f
  echo "Deploy complete. Services:"
  docker compose --env-file .env.production -f docker-compose.prod.yml ps --format "table {{.Name}}\t{{.Status}}"
COMMANDS
