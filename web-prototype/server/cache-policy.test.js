import assert from "node:assert/strict";
import test from "node:test";
import {
  cacheControlForEnvironment,
  edgeCacheHeaders,
  engineCacheControl,
} from "./cache-policy.js";

test("development responses are never stored by the browser or an edge cache", () => {
  assert.equal(
    cacheControlForEnvironment("public, max-age=300", false),
    "no-store",
  );
  assert.deepEqual(
    edgeCacheHeaders("public, max-age=300", false),
    {},
  );
});

test("build-versioned engine files stay cacheable in development", () => {
  assert.equal(
    cacheControlForEnvironment("public, max-age=31536000, immutable", false),
    "public, max-age=31536000, immutable",
  );
});

test("generic engine files are public and immutable only under their matching build URL", () => {
  assert.equal(
    engineCacheControl("BattleShip.wasm", new URLSearchParams("v=build-123")),
    "public, max-age=31536000, immutable",
  );
  assert.equal(
    engineCacheControl("torch/recipe.json", new URLSearchParams("v=build-123")),
    "public, max-age=31536000, immutable",
  );
  assert.equal(
    engineCacheControl("manifest.json", new URLSearchParams()),
    "public, no-cache",
  );
  assert.equal(
    engineCacheControl("index.html", new URLSearchParams("v=build-123")),
    "public, no-cache",
  );
  assert.equal(
    engineCacheControl("bundles/private.osb6", new URLSearchParams("v=build-123")),
    "private, no-store",
  );
});

test("production responses preserve their configured cache policy", () => {
  assert.equal(
    cacheControlForEnvironment("private, max-age=300", true),
    "private, max-age=300",
  );
  assert.deepEqual(
    edgeCacheHeaders("public, max-age=300", true),
    { "Cloudflare-CDN-Cache-Control": "public, max-age=300" },
  );
});
