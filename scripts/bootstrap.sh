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

# Clone Vite docs if not present
if [ ! -d "$PROJECT_ROOT/data/vite-docs" ]; then
    echo "Cloning Vite documentation..."
    git clone --depth 1 https://github.com/vitejs/vite.git "$PROJECT_ROOT/data/vite-docs"
else
    echo "Vite docs already cloned, pulling latest..."
    git -C "$PROJECT_ROOT/data/vite-docs" pull
fi

# Clone Vue DevTools docs if not present
if [ ! -d "$PROJECT_ROOT/data/vue-devtools-docs" ]; then
    echo "Cloning Vue DevTools documentation..."
    git clone --depth 1 https://github.com/vuejs/devtools.git "$PROJECT_ROOT/data/vue-devtools-docs"
else
    echo "Vue DevTools docs already cloned, pulling latest..."
    git -C "$PROJECT_ROOT/data/vue-devtools-docs" pull
fi

# Clone Pinia docs if not present
if [ ! -d "$PROJECT_ROOT/data/pinia-docs" ]; then
    echo "Cloning Pinia documentation..."
    git clone --depth 1 -b v4 https://github.com/vuejs/pinia.git "$PROJECT_ROOT/data/pinia-docs"
else
    echo "Pinia docs already cloned, pulling latest..."
    git -C "$PROJECT_ROOT/data/pinia-docs" pull
fi

# Clone Nuxt docs if not present
if [ ! -d "$PROJECT_ROOT/data/nuxt-docs" ]; then
    echo "Cloning Nuxt documentation..."
    git clone --depth 1 https://github.com/nuxt/nuxt.git "$PROJECT_ROOT/data/nuxt-docs"
else
    echo "Nuxt docs already cloned, pulling latest..."
    git -C "$PROJECT_ROOT/data/nuxt-docs" pull
fi

# Clone Vitest docs if not present
if [ ! -d "$PROJECT_ROOT/data/vitest-docs" ]; then
    echo "Cloning Vitest documentation..."
    git clone --depth 1 https://github.com/vitest-dev/vitest.git "$PROJECT_ROOT/data/vitest-docs"
else
    echo "Vitest docs already cloned, pulling latest..."
    git -C "$PROJECT_ROOT/data/vitest-docs" pull
fi

# Install dependencies
echo "Installing dependencies with uv..."
cd "$PROJECT_ROOT"
uv sync

echo "=== Bootstrap complete ==="
