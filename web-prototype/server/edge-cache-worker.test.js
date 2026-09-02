import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import test from "node:test";
import {
  browserCacheControl,
  cacheLookupFor,
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

test("cache lookups keep the client's validators but the key does not", () => {
  const request = new Request("https://smashtheweights.com/engine/torch/torch.js", {
    headers: { "If-None-Match": '"abc"', Cookie: "opensmash_rom_v4=x" },
  });
  const lookup = cacheLookupFor(request);
  assert.equal(lookup.url, "https://smashtheweights.com/engine/torch/torch.js");
  assert.equal(lookup.headers.get("If-None-Match"), '"abc"');
  assert.equal(lookup.headers.get("Cookie"), null);
  assert.equal(cacheRequestFor(request).headers.get("If-None-Match"), null);
});

test("versioned shared runtime files are immutable; unversioned ones always revalidate", () => {
  assert.equal(
    browserCacheControl("/engine/files/BattleShip.o2r", true),
    "private, max-age=31536000, immutable",
  );
  assert.equal(browserCacheControl("/engine/manifest.json", true), "private, max-age=31536000, immutable");
  assert.equal(browserCacheControl("/engine/manifest.json", false), "private, no-cache");
  assert.equal(browserCacheControl("/engine/torch/torch.js", false), "private, no-cache");
  assert.equal(browserCacheControl("/engine/", false), "private, no-cache");
  assert.equal(browserCacheControl("/engine/index.html", true), "private, no-cache");
  assert.equal(browserCacheControl("/engine/bundles/private.zip", true), "private, no-cache");
  assert.equal(sharedCacheAllowed("/engine/files/BattleShip.o2r"), true);
  assert.equal(sharedCacheAllowed("/engine/bundles/private.zip"), false);
});

test("bundles enter the shared cache only when the origin marks them public", () => {
  assert.equal(sharedCacheAllowed("/engine/bundles/cleopatra.osb6", "public, max-age=3600"), true);
  assert.equal(sharedCacheAllowed("/engine/bundles/mine.osb6", "private, max-age=300"), false);
  assert.equal(sharedCacheAllowed("/engine/bundles/mine.osb6", null), false);
  assert.equal(sharedCacheAllowed("/engine/bundles/mine.osb6", "no-store"), false);
  assert.equal(sharedCacheAllowed("/engine/files/x.o2r", "private, max-age=3600"), true);
  assert.equal(
    browserCacheControl("/engine/bundles/cleopatra.osb6", false, "public, no-cache"),
    "public, no-cache",
  );
  assert.equal(
    browserCacheControl("/engine/bundles/mine.osb6", false, "private, no-store"),
    "private, no-cache",
  );
});

test("edge responses carry the engine security headers", async () => {
  const { ENGINE_SECURITY_HEADERS } = await import("../infra/cloudflare-engine-worker.js");
  assert.equal(ENGINE_SECURITY_HEADERS["Content-Security-Policy"], "frame-ancestors 'self'");
  assert.equal(ENGINE_SECURITY_HEADERS["X-Frame-Options"], "SAMEORIGIN");
  assert.equal(ENGINE_SECURITY_HEADERS["X-Content-Type-Options"], "nosniff");
});
