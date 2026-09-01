import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { createJobDatabase } from "./job-database.js";
import { createObjectStore } from "./object-store.js";

test("local database and object storage survive a fresh instance", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "opensmash-storage-test-"));
  context.after(() => rm(root, { recursive: true, force: true }));

  const jobsRoot = path.join(root, "jobs");
  const database = createJobDatabase({ jobsRoot });
  await database.init();
  await database.save({ id: "job-1", status: "queued", revision: 1 });
  assert.deepEqual(await database.list(), [{ id: "job-1", status: "queued", revision: 1 }]);

  const source = path.join(root, "source.bin");
  await writeFile(source, "fighter-data");
  process.env.OBJECT_STORE_ROOT = path.join(root, "objects");
  const store = createObjectStore({ appRoot: root });
  await store.init();
  const artifact = await store.putFile("characters/test/versions/job-1-1/injection/test.osb", source, { public: true });
  assert.match(artifact.url, /^\/objects\//);
  assert.equal(await readFile(store.localPath(artifact.key), "utf8"), "fighter-data");
  assert.equal((await store.read(artifact.key)).toString("utf8"), "fighter-data");
  const latest = await store.putJson(
    "characters/test/latest.json",
    { version: "job-1-1", manifest: artifact.url },
    { public: true, immutable: false },
  );
  assert.equal(latest.immutable, false);
  assert.deepEqual(JSON.parse(await readFile(store.localPath(latest.key), "utf8")), {
    version: "job-1-1",
    manifest: artifact.url,
  });
  delete process.env.OBJECT_STORE_ROOT;
});

test("local database rejects duplicate slugs and protects active leases", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "opensmash-database-test-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const database = createJobDatabase({ jobsRoot: path.join(root, "jobs") });
  await database.init();
  await database.insert({ id: "first", slug: "fighter", status: "queued", createdAt: new Date().toISOString() });
  await assert.rejects(
    database.insert({ id: "second", slug: "fighter", status: "queued", createdAt: new Date().toISOString() }),
    (error) => error.code === "DUPLICATE_SLUG",
  );

  const firstClaim = await database.claim("first", "execution-a", 60);
  assert.equal(firstClaim.claimed, true);
  const competingClaim = await database.claim("first", "execution-b", 60);
  assert.equal(competingClaim.claimed, false);
  const retryClaim = await database.claim("first", "execution-a", 60);
  assert.equal(retryClaim.claimed, true);
});
