import assert from "node:assert/strict";
import test from "node:test";
import { assertQuota, quotaUsage } from "./job-quota.js";

const now = Date.parse("2026-09-01T12:00:00Z");
const hoursAgo = (hours) => new Date(now - hours * 60 * 60 * 1000).toISOString();

test("daily usage counts created jobs and manual retries inside 24 hours", () => {
  const jobs = [
    { ownerId: "a", status: "failed", createdAt: hoursAgo(30), retry: { manualRetriesAt: [hoursAgo(2), hoursAgo(26)] } },
    { ownerId: "a", status: "queued", createdAt: hoursAgo(1) },
    { ownerId: "b", status: "running", createdAt: hoursAgo(1) },
  ];
  assert.deepEqual(quotaUsage(jobs, "a", { now }), { activeForOwner: 1, dailyForOwner: 2, globalActive: 2 });
});

test("pending reservations count as active, daily, and global usage", () => {
  const pending = { owners: new Map([["a", 2]]), global: 3 };
  assert.deepEqual(quotaUsage([], "a", { now, pending }), { activeForOwner: 2, dailyForOwner: 2, globalActive: 3 });
});

test("assertQuota reports the first exceeded limit", () => {
  const limits = { maxActivePerOwner: 1, maxDailyPerOwner: 3, maxGlobalActive: 20 };
  assert.doesNotThrow(() => assertQuota({ activeForOwner: 0, dailyForOwner: 2, globalActive: 19 }, limits));
  assert.throws(
    () => assertQuota({ activeForOwner: 1, dailyForOwner: 0, globalActive: 0 }, limits),
    (error) => error.code === "QUOTA_EXCEEDED" && error.status === 429 && error.reason === "active",
  );
  assert.throws(
    () => assertQuota({ activeForOwner: 0, dailyForOwner: 3, globalActive: 0 }, limits),
    (error) => error.reason === "daily",
  );
  assert.throws(
    () => assertQuota({ activeForOwner: 0, dailyForOwner: 0, globalActive: 20 }, limits),
    (error) => error.status === 503 && error.reason === "global",
  );
});
