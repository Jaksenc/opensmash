import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import test from "node:test";
import {
  browserCacheControl,
  cacheRequestFor,
  sharedCacheAllowed,
  validRomSession,
} from "../infra/cloudflare-engine-worker.js";

function signedCookie(session, secret) {
  const payload = Buffer.from(JSON.stringify(session)).toString("base64url");
  const signature = createHmac("sha256", secret).update(payload).digest("base64url");
  return `${payload}.${signature}`;
}

test("edge validation accepts the server ROM session format", async () => {
  const secret = "test-secret";
  const cookie = signedCookie({
    version: 2,
    subject: "12345678-1234-1234-1234-123456789012",
    hash: "a".repeat(40),
    expires: 2_000,
  }, secret);
  assert.equal(await validRomSession(cookie, secret, 1_000), true);
  assert.equal(await validRomSession(cookie, "wrong-secret", 1_000), false);
  assert.equal(await validRomSession(cookie, secret, 3_000), false);
});

test("edge validation accepts the previous secret during rotation", async () => {
  const cookie = signedCookie({
    version: 2,
    subject: "12345678-1234-1234-1234-123456789012",
    hash: "a".repeat(40),
    expires: 2_000,
  }, "previous-secret");
  assert.equal(await validRomSession(cookie, ["current-secret", "previous-secret"], 1_000), true);
});

test("version is the only query component in a shared cache key", () => {
  const request = new Request("https://smashtheweights.com/engine/files/BattleShip.o2r?v=abc&private=ignored");
  assert.equal(cacheRequestFor(request).url, "https://smashtheweights.com/engine/files/BattleShip.o2r?v=abc");
});

test("all versioned shared runtime files are immutable, but bundles are not", () => {
  assert.equal(
    browserCacheControl("/engine/files/BattleShip.o2r", true),
    "private, max-age=31536000, immutable",
  );
  assert.equal(browserCacheControl("/engine/manifest.json", true), "private, max-age=31536000, immutable");
  assert.equal(browserCacheControl("/engine/bundles/private.zip", true), "private, max-age=300");
  assert.equal(sharedCacheAllowed("/engine/files/BattleShip.o2r"), true);
  assert.equal(sharedCacheAllowed("/engine/bundles/private.zip"), false);
});

test("edge responses carry the engine security headers", async () => {
  const { ENGINE_SECURITY_HEADERS } = await import("../infra/cloudflare-engine-worker.js");
  assert.equal(ENGINE_SECURITY_HEADERS["Content-Security-Policy"], "frame-ancestors 'self'");
  assert.equal(ENGINE_SECURITY_HEADERS["X-Frame-Options"], "SAMEORIGIN");
  assert.equal(ENGINE_SECURITY_HEADERS["X-Content-Type-Options"], "nosniff");
});
