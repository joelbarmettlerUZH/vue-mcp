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

# Clone Vue Router docs if not present
if [ ! -d "$PROJECT_ROOT/data/vue-router-docs" ]; then
    echo "Cloning Vue Router documentation..."
    git clone --depth 1 https://github.com/vuejs/router.git "$PROJECT_ROOT/data/vue-router-docs"
else
    echo "Vue Router docs already cloned, pulling latest..."
    git -C "$PROJECT_ROOT/data/vue-router-docs" pull
fi

# Clone VueUse docs if not present
if [ ! -d "$PROJECT_ROOT/data/vueuse-docs" ]; then
    echo "Cloning VueUse documentation..."
    git clone --depth 1 https://github.com/vueuse/vueuse.git "$PROJECT_ROOT/data/vueuse-docs"
else
    echo "VueUse docs already cloned, pulling latest..."
    git -C "$PROJECT_ROOT/data/vueuse-docs" pull
fi

# Install dependencies
echo "Installing dependencies with uv..."
cd "$PROJECT_ROOT"
uv sync

echo "=== Bootstrap complete ==="
