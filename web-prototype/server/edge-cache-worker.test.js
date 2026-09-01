import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import test from "node:test";
import { validRomSession } from "../infra/cloudflare-engine-worker.js";

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
