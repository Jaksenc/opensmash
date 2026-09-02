import assert from "node:assert/strict";
import test from "node:test";
import {
  cacheControlForEnvironment,
  edgeCacheHeaders,
} from "./cache-policy.js";

test("development responses are never stored by the browser or an edge cache", () => {
  assert.equal(
    cacheControlForEnvironment("public, max-age=31536000, immutable", false),
    "no-store",
  );
  assert.deepEqual(
    edgeCacheHeaders("public, max-age=300", false),
    {},
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
