#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Vue Docs MCP Bootstrap ==="

# Clone Vue docs if not present
if [ ! -d "$PROJECT_ROOT/data/vue-docs" ]; then
    echo "Cloning Vue.js documentation..."
    git clone --depth 1 https://github.com/vuejs/docs.git "$PROJECT_ROOT/data/vue-docs"
else
    echo "Vue docs already cloned, pulling latest..."
    git -C "$PROJECT_ROOT/data/vue-docs" pull
fi

# Install dependencies
echo "Installing dependencies with uv..."
cd "$PROJECT_ROOT"
uv sync

echo "=== Bootstrap complete ==="
