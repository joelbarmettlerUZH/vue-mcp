import { createHash, timingSafeEqual } from "node:crypto";

const digest = (value: string) => createHash("sha256").update(value).digest();

/** Constant-time comparison (hashing first makes the buffers equal length). */
function safeEqual(a: string, b: string): boolean {
  return timingSafeEqual(digest(a), digest(b));
}

/** True when the request carries valid HTTP Basic credentials. */
export function hasValidCredentials(req: Request, user: string, password: string): boolean {
  const header = req.headers.get("authorization") ?? "";
  if (!header.startsWith("Basic ")) return false;
  let decoded: string;
  try {
    decoded = atob(header.slice(6));
  } catch {
    return false;
  }
  const split = decoded.indexOf(":");
  if (split < 0) return false;
  // Evaluate both so the time taken does not reveal which part was wrong.
  const userOk = safeEqual(decoded.slice(0, split), user);
  const passOk = safeEqual(decoded.slice(split + 1), password);
  return userOk && passOk;
}

export const challenge = () =>
  new Response("Authentication required", {
    status: 401,
    headers: { "www-authenticate": 'Basic realm="Vue MCP usage", charset="UTF-8"' },
  });

const LOOPBACK = new Set(["127.0.0.1", "localhost", "::1"]);

/** Refuse to serve raw search queries beyond loopback without a password. */
export function assertSafeBinding(host: string, password: string): void {
  if (!LOOPBACK.has(host) && password.length < 12) {
    throw new Error(
      "DASHBOARD_PASSWORD (at least 12 characters) is required when HOST is not loopback",
    );
  }
}
