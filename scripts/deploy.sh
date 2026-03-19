#!/bin/bash
set -euo pipefail

# Deploy latest images to production server.
# Usage: DEPLOY_HOST=your-vm.example.com ./scripts/deploy.sh

REMOTE_HOST="${DEPLOY_HOST:?Set DEPLOY_HOST env var}"
REMOTE_USER="${DEPLOY_USER:-deploy}"
REMOTE_DIR="${DEPLOY_DIR:-/opt/vue-mcp}"

echo "Deploying to ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}"

ssh "${REMOTE_USER}@${REMOTE_HOST}" <<COMMANDS
  set -euo pipefail
  cd "${REMOTE_DIR}"
  docker compose pull
  docker compose up -d --remove-orphans
  docker image prune -f
  echo "Deploy complete. Services:"
  docker compose ps --format "table {{.Name}}\t{{.Status}}"
COMMANDS
