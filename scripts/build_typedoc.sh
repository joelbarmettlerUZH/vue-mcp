#!/bin/bash
# Generate the TypeDoc API reference pages for one upstream docs repo.
#
# Used by the Dockerfile `typedoc` stage, which holds no secrets: pnpm install and TypeDoc
# (plus its plugins) are third-party code. A failure must not block a deploy, so it only warns
# and leaves an empty output directory; the ingestion image then falls back to seed entities.
#
# Usage: build_typedoc.sh <name> <git-url> [ref]    (output: /out/<name>/api)
set -uo pipefail

name="$1"
url="$2"
ref="${3:-HEAD}"
out="/out/$name/api"
mkdir -p "$out"

git init -q "/src/$name" \
  && cd "/src/$name" \
  && git remote add origin "$url" \
  && git fetch -q --depth 1 origin "$ref" \
  && git checkout -q FETCH_HEAD \
  && echo "TypeDoc source for $name: $(git rev-parse HEAD)" \
  && npx -y pnpm@12 install --frozen-lockfile --ignore-scripts \
  && (cd packages/docs && node run-typedoc.mjs) \
  && cp -r packages/docs/api/. "$out"/ \
  || echo "WARNING: TypeDoc generation failed for $name; the image will carry no API pages for it" >&2

echo "TypeDoc pages for $name: $(find "$out" -name '*.md' | wc -l)"
