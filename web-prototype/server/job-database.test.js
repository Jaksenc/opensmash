import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { createJobDatabase } from "./job-database.js";

async function withDatabase(run) {
  const root = await mkdtemp(path.join(os.tmpdir(), "opensmash-jobdb-test-"));
  const database = createJobDatabase({ jobsRoot: root });
  await database.init();
  try {
    await run(database);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

const past = new Date(Date.now() - 60_000).toISOString();
const future = new Date(Date.now() + 60_000).toISOString();

test("claim refuses running and retrying jobs even when their lease looks expired", async () => {
  await withDatabase(async (database) => {
    await database.insert({ id: "j1", slug: "one", ownerId: "a", status: "running", createdAt: past,
      lease: { executionId: "exec-a", expiresAt: past } });
    assert.equal((await database.claim("j1", "exec-b", 60)).claimed, false);
    // The same execution may re-claim idempotently.
    assert.equal((await database.claim("j1", "exec-a", 60)).claimed, true);

    await database.insert({ id: "j2", slug: "two", ownerId: "a", status: "retrying", createdAt: past, lease: null });
    assert.equal((await database.claim("j2", "exec-b", 60)).claimed, false);
  });
});

test("claim accepts queued jobs and jobs whose reconciled lease was cleared", async () => {
  await withDatabase(async (database) => {
    await database.insert({ id: "j1", slug: "one", ownerId: "a", status: "queued", createdAt: past,
      lease: { executionId: "exec-old", expiresAt: past } });
    const claim = await database.claim("j1", "exec-new", 60);
    assert.equal(claim.claimed, true);
    assert.equal(claim.job.lease.executionId, "exec-new");
    assert.ok(Date.parse(claim.job.lease.expiresAt) > Date.now());

    await database.insert({ id: "j2", slug: "two", ownerId: "a", status: "queued", createdAt: past,
      lease: { executionId: "exec-live", expiresAt: future } });
    assert.equal((await database.claim("j2", "exec-new", 60)).claimed, false);
  });
});

test("saves conditional on the lease fail once another owner holds the job", async () => {
  await withDatabase(async (database) => {
    await database.insert({ id: "j1", slug: "one", ownerId: "a", status: "queued", createdAt: past });
    const { job } = await database.claim("j1", "exec-a", 60);
    await database.save({ ...job, progress: 10 }, { executionId: "exec-a" });

    // The API reconciles the job: lease cleared, status failed.
    await database.save({ ...job, status: "failed", lease: null });
    await assert.rejects(
      database.save({ ...job, progress: 20 }, { executionId: "exec-a" }),
      (error) => error.code === "LEASE_LOST",
    );
    const stored = await database.get("j1");
    assert.equal(stored.status, "failed");
    assert.equal(stored.lease, null);
    assert.equal(stored.progress, undefined);
  });
});

test("insert enforces the quota against stored jobs", async () => {
  await withDatabase(async (database) => {
    const quota = { maxActivePerOwner: 1, maxDailyPerOwner: 3, maxGlobalActive: 20 };
    const now = new Date().toISOString();
    await database.insert({ id: "j1", slug: "one", ownerId: "a", status: "running", createdAt: now }, { quota });
    await assert.rejects(
      database.insert({ id: "j2", slug: "two", ownerId: "a", status: "queued", createdAt: now }, { quota }),
      (error) => error.code === "QUOTA_EXCEEDED" && error.reason === "active",
    );
    await database.insert({ id: "j3", slug: "three", ownerId: "b", status: "queued", createdAt: now }, { quota });
    await assert.rejects(
      database.insert({ id: "j4", slug: "one", ownerId: "c", status: "queued", createdAt: now }, { quota }),
      (error) => error.code === "DUPLICATE_SLUG",
    );
  });
});
