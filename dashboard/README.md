# Usage dashboard

Small read-only dashboard over the server's `usage_events` table: requests per day, tools (calls, p50/p95, errors),
frameworks, top searches and recent errors. Bun API (`server/`, no dependencies, Bun's built-in Postgres client) plus a
Vue 3 + Vite page (`web/`).

"Requests" means logged events: tool calls and resource reads. Protocol traffic such as `initialize` and `tools/list` is
not logged by the server.

## Run locally

```bash
make docker-dev-up                       # from the repo root: local Postgres on :5432
cd dashboard && bun install
bun run seed                             # synthetic traffic, LOCAL ONLY (truncates usage_events)
bun run dev                              # API on :3100, Vite on :5173 (proxies /api)
```

Or `bun run build && bun run start` and open http://127.0.0.1:3100.

Environment: `DATABASE_URL` (default `postgres://vue_mcp:vue_mcp@localhost:5432/vue_mcp`), `PORT` (3100),
`HOST` (127.0.0.1), `DASHBOARD_USER` (admin) and `DASHBOARD_PASSWORD`.

The page shows raw search queries. With a password set, every route except `/healthz` requires HTTP Basic auth, and
the server refuses to bind beyond loopback without a password of at least 12 characters. Every query runs in a
`READ ONLY` transaction; in production it also connects as a role that can only `SELECT` from `usage_events`.

Tests: `bun run test`, `bun run typecheck`. Production wiring (image, compose service, role, secrets) is described in
the repo's `CLAUDE.md` under "Usage Dashboard".
