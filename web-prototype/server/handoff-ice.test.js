import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_STUN, createIceServerProvider } from "./handoff-ice.js";

test("unconfigured deploys hand out STUN only", async () => {
  const provider = createIceServerProvider({ env: {}, fetchImpl: () => { throw new Error("must not fetch"); } });
  assert.equal(provider.driver, "stun");
  const result = await provider.iceServers();
  assert.deepEqual(result.iceServers, [...DEFAULT_STUN]);
  assert.equal(result.relay, false);
});

test("static TURN credentials are appended after STUN", async () => {
  const provider = createIceServerProvider({
    env: { TURN_URLS: "turn:relay.example:3478, turns:relay.example:5349", TURN_USERNAME: "u", TURN_CREDENTIAL: "p" },
  });
  assert.equal(provider.driver, "static");
  const { iceServers, relay } = await provider.iceServers();
  assert.equal(relay, true);
  assert.deepEqual(iceServers.at(-1), { urls: ["turn:relay.example:3478", "turns:relay.example:5349"], username: "u", credential: "p" });
});

test("Cloudflare TURN mints credentials and caches them", async () => {
  let calls = 0;
  let time = 1_000_000;
  const fetchImpl = async (url, init) => {
    calls += 1;
    assert.match(url, /\/turn\/keys\/key-1\/credentials\/generate-ice-servers$/);
    assert.equal(init.headers.Authorization, "Bearer tok");
    assert.equal(JSON.parse(init.body).ttl, 900);
    return { ok: true, json: async () => ({ iceServers: [{ urls: ["turn:turn.cloudflare.com:3478"], username: "cf", credential: "secret" }] }) };
  };
  const provider = createIceServerProvider({
    env: { CLOUDFLARE_TURN_KEY_ID: "key-1", CLOUDFLARE_TURN_KEY_API_TOKEN: "tok" },
    fetchImpl,
    now: () => time,
  });
  assert.equal(provider.driver, "cloudflare");
  const first = await provider.iceServers();
  assert.equal(first.relay, true);
  assert.equal(first.iceServers.at(-1).username, "cf");
  await provider.iceServers();
  assert.equal(calls, 1, "second call within the cache window reuses credentials");
  time += 6 * 60 * 1000;
  await provider.iceServers();
  assert.equal(calls, 2, "credentials are re-minted after the cache expires");
});

test("a Cloudflare failure degrades to STUN instead of throwing", async () => {
  const provider = createIceServerProvider({
    env: { CLOUDFLARE_TURN_KEY_ID: "key-1", CLOUDFLARE_TURN_KEY_API_TOKEN: "tok" },
    fetchImpl: async () => ({ ok: false, status: 503 }),
  });
  const warn = console.warn;
  console.warn = () => {};
  try {
    const result = await provider.iceServers();
    assert.deepEqual(result.iceServers, [...DEFAULT_STUN]);
    assert.equal(result.relay, false);
  } finally {
    console.warn = warn;
  }
});
