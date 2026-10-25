import { existsSync } from "node:fs";
import { join, normalize } from "node:path";
import { assertSafeBinding, challenge, hasValidCredentials } from "./auth";
import { parseDays } from "./params";
import { connect, overview } from "./queries";

const DATABASE_URL = process.env.DATABASE_URL ?? "postgres://vue_mcp:vue_mcp@localhost:5432/vue_mcp";
const PORT = Number(process.env.PORT ?? 3100);
// Loopback by default: the dashboard shows raw search queries.
const HOST = process.env.HOST ?? "127.0.0.1";
const USER = process.env.DASHBOARD_USER ?? "admin";
const PASSWORD = process.env.DASHBOARD_PASSWORD ?? "";
const DIST = join(import.meta.dir, "..", "web", "dist");

assertSafeBinding(HOST, PASSWORD);
const sql = connect(DATABASE_URL);

const SECURITY_HEADERS = {
  "cache-control": "no-store",
  "x-content-type-options": "nosniff",
  "x-frame-options": "DENY",
  "referrer-policy": "no-referrer",
  "content-security-policy":
    "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'",
};

function withHeaders(res: Response): Response {
  for (const [k, v] of Object.entries(SECURITY_HEADERS)) res.headers.set(k, v);
  return res;
}

const json = (body: unknown, status = 200) => Response.json(body, { status });

async function serveStatic(pathname: string): Promise<Response> {
  const safe = normalize(pathname).replace(/^(\.\.[/\\])+/, "");
  const file = Bun.file(join(DIST, safe === "/" ? "index.html" : safe));
  if (existsSync(DIST) && (await file.exists())) return new Response(file);
  const index = Bun.file(join(DIST, "index.html"));
  if (await index.exists()) return new Response(index); // SPA fallback
  return new Response("Frontend not built. Run `bun run build`, or use `bun run dev`.", { status: 404 });
}

async function route(req: Request): Promise<Response> {
  const url = new URL(req.url);
  // Liveness for the container healthcheck: no auth, no database.
  if (url.pathname === "/healthz") return new Response("ok");

  if (PASSWORD && !hasValidCredentials(req, USER, PASSWORD)) return challenge();
  if (req.method !== "GET") return json({ error: "method not allowed" }, 405);

  if (url.pathname === "/api/overview") {
    const days = parseDays(url.searchParams.get("days"));
    if (days === null) return json({ error: "days must be an integer from 1 to 365" }, 400);
    try {
      return json(await overview(sql, days));
    } catch (err) {
      console.error("overview failed:", err);
      return json({ error: "query failed" }, 500);
    }
  }
  if (url.pathname.startsWith("/api/")) return json({ error: "not found" }, 404);
  return serveStatic(url.pathname);
}

Bun.serve({
  hostname: HOST,
  port: PORT,
  fetch: async (req) => withHeaders(await route(req)),
});

console.log(`Usage dashboard on http://${HOST}:${PORT} (auth ${PASSWORD ? "on" : "off, loopback only"})`);
