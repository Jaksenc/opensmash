import assert from "node:assert/strict";
import test from "node:test";
import { TURNSTILE_FIELD, createTurnstileVerifier } from "./turnstile.js";

function fakeFetch(payload, calls = []) {
  return async (url, init) => {
    calls.push({ url, body: Object.fromEntries(init.body) });
    return { json: async () => payload };
  };
}

test("disabled outside production when no secret is configured", async () => {
  const verifier = createTurnstileVerifier({ secretKey: "", isProduction: false });
  assert.equal(verifier.enabled, false);
  assert.equal(verifier.siteKey, null);
  assert.deepEqual(await verifier.verify(undefined), { success: true, skipped: true });
});

test("production refuses to start without a secret", () => {
  assert.throws(() => createTurnstileVerifier({ secretKey: "", isProduction: true }), /TURNSTILE_SECRET_KEY/);
  assert.throws(() => createTurnstileVerifier({ secretKey: "s", siteKey: "", isProduction: true }), /TURNSTILE_SITE_KEY/);
});

test("posts the token and remote ip to siteverify", async () => {
  const calls = [];
  const verifier = createTurnstileVerifier({
    secretKey: "secret", siteKey: "site", fetchImpl: fakeFetch({ success: true, hostname: "smash.fun" }, calls),
  });
  assert.equal(verifier.siteKey, "site");
  assert.deepEqual(await verifier.verify("tok", "203.0.113.9"), { success: true, hostname: "smash.fun" });
  assert.deepEqual(calls[0].body, { secret: "secret", response: "tok", remoteip: "203.0.113.9" });
  assert.equal(TURNSTILE_FIELD, "cf-turnstile-response");
});

test("missing, rejected, and expired tokens surface as 403 with a player-facing message", async () => {
  const verifier = createTurnstileVerifier({ secretKey: "secret", siteKey: "site", fetchImpl: fakeFetch({ success: true }) });
  await assert.rejects(verifier.verify(""), (error) => error.status === 403 && /human check/.test(error.message));
  const rejected = createTurnstileVerifier({
    secretKey: "secret", siteKey: "site", fetchImpl: fakeFetch({ success: false, "error-codes": ["invalid-input-response"] }),
  });
  await assert.rejects(rejected.verify("tok"), (error) => error.status === 403 && /failed/.test(error.message));
  const expired = createTurnstileVerifier({
    secretKey: "secret", siteKey: "site", fetchImpl: fakeFetch({ success: false, "error-codes": ["timeout-or-duplicate"] }),
  });
  await assert.rejects(expired.verify("tok"), (error) => /expired/.test(error.message));
});

test("siteverify outage fails closed with a retry message", async () => {
  const verifier = createTurnstileVerifier({
    secretKey: "secret", siteKey: "site", fetchImpl: async () => { throw new Error("ECONNRESET"); },
  });
  await assert.rejects(verifier.verify("tok"), (error) => error.status === 403 && /unavailable/.test(error.message));
});
