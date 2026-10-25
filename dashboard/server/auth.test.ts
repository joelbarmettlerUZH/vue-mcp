import { describe, expect, test } from "bun:test";
import { assertSafeBinding, hasValidCredentials } from "./auth";
import { parseDays } from "./params";

const basic = (value: string) =>
  new Request("http://x/", { headers: { authorization: `Basic ${btoa(value)}` } });

describe("hasValidCredentials", () => {
  test("accepts the right user and password", () => {
    expect(hasValidCredentials(basic("admin:s3cret-pass-123"), "admin", "s3cret-pass-123")).toBe(true);
  });
  test("passwords may contain colons", () => {
    expect(hasValidCredentials(basic("admin:a:b:c"), "admin", "a:b:c")).toBe(true);
  });
  test("rejects wrong password, wrong user, empty and prefix guesses", () => {
    expect(hasValidCredentials(basic("admin:nope"), "admin", "s3cret-pass-123")).toBe(false);
    expect(hasValidCredentials(basic("root:s3cret-pass-123"), "admin", "s3cret-pass-123")).toBe(false);
    expect(hasValidCredentials(basic("admin:"), "admin", "s3cret-pass-123")).toBe(false);
    expect(hasValidCredentials(basic("admin:s3cret"), "admin", "s3cret-pass-123")).toBe(false);
  });
  test("rejects missing, non-basic and malformed headers", () => {
    expect(hasValidCredentials(new Request("http://x/"), "a", "b")).toBe(false);
    const bearer = new Request("http://x/", { headers: { authorization: "Bearer abc" } });
    expect(hasValidCredentials(bearer, "a", "b")).toBe(false);
    const garbage = new Request("http://x/", { headers: { authorization: "Basic !!!not-base64" } });
    expect(hasValidCredentials(garbage, "a", "b")).toBe(false);
    expect(hasValidCredentials(basic("no-colon-here"), "a", "b")).toBe(false);
  });
});

describe("assertSafeBinding", () => {
  test("loopback needs no password", () => {
    expect(() => assertSafeBinding("127.0.0.1", "")).not.toThrow();
    expect(() => assertSafeBinding("localhost", "")).not.toThrow();
  });
  test("a public bind without a strong password refuses to start", () => {
    expect(() => assertSafeBinding("0.0.0.0", "")).toThrow();
    expect(() => assertSafeBinding("0.0.0.0", "short")).toThrow();
  });
  test("a public bind with a strong password is fine", () => {
    expect(() => assertSafeBinding("0.0.0.0", "a-long-enough-password")).not.toThrow();
  });
});

describe("parseDays", () => {
  test("defaults to 30 and accepts 1 to 365", () => {
    expect(parseDays(null)).toBe(30);
    expect(parseDays("1")).toBe(1);
    expect(parseDays("365")).toBe(365);
  });
  test("rejects everything else", () => {
    for (const bad of ["0", "366", "-1", "1.5", "abc", "", "1;drop", "007x", "1e2", " 7"]) {
      expect(parseDays(bad)).toBeNull();
    }
  });
});
