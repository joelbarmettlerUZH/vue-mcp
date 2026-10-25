#!/usr/bin/env python3
"""End-to-end smoke test for a running Vue MCP server.

Checks /health, then exercises the MCP endpoint twice: once as a legacy-handshake client
(raw JSON-RPC, no session id) and once as a modern client (fastmcp, 2026-07-28 spec). Covers
search across several frameworks, API lookup, related topics, cross-framework search,
resources, a prompt, and input validation.

Requests are paced because the production proxy rate-limits to 60 requests per minute.

Usage:
    uv run python scripts/smoke_test.py                      # https://mcp.vue-mcp.org
    uv run python scripts/smoke_test.py http://localhost:8000
    uv run python scripts/smoke_test.py --delay 0            # no pacing (local server)

Exit code is 0 when every check passes, 1 otherwise.
"""

import argparse
import asyncio
import json
import logging
import re
import sys
import time

import httpx
from fastmcp import Client

DEFAULT_URL = "https://mcp.vue-mcp.org"
EXPECTED_TOOLS = ["api_lookup", "docs_search", "ecosystem_search", "get_related"]
EXPECTED_PROMPTS = ["compare_apis", "debug_issue", "migrate_pattern"]
JSON_RPC_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

# (framework, query, word that must appear in a relevant answer)
SEARCHES = [
    ("vue", "how do I use computed properties", "computed"),
    ("vue-router", "navigation guards", "guard"),
    ("pinia", "define a store", "store"),
    ("vueuse", "debounce a ref", "debounce"),
    ("nuxt", "data fetching useFetch", "fetch"),
    ("vite", "environment variables", "env"),
    ("formkit", "validation rules", "valid"),
]

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {label} {detail}".rstrip())
    if not ok:
        failures.append(label)


def rpc(mcp_url: str, body: dict) -> dict | None:
    """Send one JSON-RPC request and return the last event of the response."""
    response = httpx.post(mcp_url, headers=JSON_RPC_HEADERS, json=body, timeout=60)
    events = [
        json.loads(line[5:]) for line in response.text.splitlines() if line.startswith("data:")
    ]
    return events[-1] if events else None


def check_health(base: str) -> None:
    print("== health endpoint")
    response = httpx.get(f"{base}/health", timeout=15)
    body = response.json()
    check("GET /health status", response.status_code == 200, f"HTTP {response.status_code}")
    check("health checks", all(v == "ok" for v in body["checks"].values()), str(body["checks"]))
    check("indexed data", body["sources"] > 0 and body["pages"] > 0, f"{body['pages']} pages")


def check_legacy_client(mcp_url: str, delay: float) -> None:
    print("== legacy handshake client (raw JSON-RPC, no session id)")
    listing = rpc(mcp_url, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = sorted(t["name"] for t in listing["result"]["tools"])
    check("tools/list", names == EXPECTED_TOOLS, str(names))
    time.sleep(delay)
    result = rpc(
        mcp_url,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "docs_search",
                "arguments": {"framework": "vue", "query": "computed properties"},
            },
        },
    )["result"]
    check("docs_search", not result.get("isError"), f"{len(result['content'][0]['text'])} chars")


async def check_modern_client(mcp_url: str, delay: float) -> None:
    print("== modern client (fastmcp, 2026-07-28 spec)")
    async with Client(mcp_url) as client:
        check("protocol version", client.protocol_version == "2026-07-28", client.protocol_version)
        tools = sorted(t.name for t in await client.list_tools())
        check("tools", tools == EXPECTED_TOOLS, str(tools))
        prompts = sorted(p.name for p in await client.list_prompts())
        check("prompts", prompts == EXPECTED_PROMPTS, str(prompts))

        async def call(name: str, arguments: dict) -> str:
            await asyncio.sleep(delay)
            try:
                return (await client.call_tool(name, arguments)).content[0].text
            except Exception as e:
                return f"ERROR: {str(e)[:120]}"

        for framework, query, needle in SEARCHES:
            out = await call("docs_search", {"framework": framework, "query": query})
            ok = not out.startswith("ERROR") and needle in out.lower()
            check(f"docs_search {framework}", ok, f"{len(out)} chars")

        out = await call("api_lookup", {"framework": "vue", "api_name": "computed"})
        check("api_lookup vue computed", "computed" in out.lower())
        out = await call("get_related", {"framework": "vue-router", "topic": "useRouter"})
        check("get_related vue-router", not out.startswith("ERROR"))
        out = await call("ecosystem_search", {"query": "form validation"})
        check("ecosystem_search", not out.startswith("ERROR"), f"{len(out)} chars")
        out = await call("docs_search", {"framework": "angular", "query": "x"})
        check("unknown framework rejected", out.startswith("ERROR"))

        await asyncio.sleep(delay)
        toc = (await client.read_resource("vue://topics"))[0].text
        page_uris = re.findall(r"vue://pages/[^\s)\]`]+", toc)[::10]
        unreadable = 0
        for uri in page_uris:
            await asyncio.sleep(delay)
            try:
                await client.read_resource(uri)
            except Exception:
                unreadable += 1
        check("TOC page links readable", unreadable == 0, f"{len(page_uris)} sampled")

        for uri in ("vue://api/entities/computed", "vue://topics/guide", "ecosystem://sources"):
            await asyncio.sleep(delay)
            try:
                await client.read_resource(uri)
                check(f"resource {uri}", True)
            except Exception as e:
                check(f"resource {uri}", False, str(e)[:80])

        await asyncio.sleep(delay)
        prompt = await client.get_prompt(
            "debug_issue", {"framework": "pinia", "symptom": "store state resets"}
        )
        text = " ".join(m.content.text for m in prompt.messages)
        check("prompt debug_issue", "Pinia" in text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test a running Vue MCP server")
    parser.add_argument(
        "url", nargs="?", default=DEFAULT_URL, help=f"server base URL ({DEFAULT_URL})"
    )
    parser.add_argument(
        "--delay", type=float, default=2.0, help="seconds between requests (default 2)"
    )
    args = parser.parse_args()
    base = args.url.rstrip("/")

    logging.disable(logging.INFO)  # the client logs every server progress notification
    print(f"Smoke testing {base}\n")
    check_health(base)
    check_legacy_client(f"{base}/mcp", args.delay)
    asyncio.run(check_modern_client(f"{base}/mcp", args.delay))

    print(f"\n{'ALL OK' if not failures else f'FAILED: {failures}'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
