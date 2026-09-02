import test from "node:test";
import assert from "node:assert/strict";

import { prewarmEngineArchive } from "./rom-store.js";

test("prewarmEngineArchive skips the optional extractor when the archive is packaged", async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (...args) => {
    requests.push(args);
    return {
      async json() {
        return {
          files: [
            { path: "/BattleShip.o2r", url: "files/BattleShip.o2r" },
            { path: "/config.yml", url: "files/config.yml" },
          ],
        };
      },
    };
  };

  try {
    assert.equal(await prewarmEngineArchive(), null);
    assert.deepEqual(requests, [["/engine/manifest.json", { cache: "no-cache" }]]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
