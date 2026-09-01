import assert from "node:assert/strict";
import test from "node:test";
import {
  automaticRetryPlan,
  isJobAccessible,
  parseProgressEvent,
  submissionSettings,
} from "./fighter-jobs.js";

test("output moderation retries are bounded", () => {
  const log = `provider error: {'code': 'moderation_blocked', 'moderation_stage': 'output'}`;
  assert.equal(automaticRetryPlan(log, "portrait", {}).kind, "moderation");
  assert.equal(automaticRetryPlan(log, "portrait", { moderation: 2 }), null);
});

test("transient retries skip expensive mesh stages", () => {
  assert.equal(automaticRetryPlan("HTTP 503 server_error", "portrait", {}).kind, "transient");
  assert.equal(automaticRetryPlan("HTTP 503 server_error", "mesh-build", {}), null);
});

test("structured pipeline progress is validated", () => {
  const line = '@@opensmash {"protocolVersion":1,"type":"job.progress","stage":"portrait","label":"Painting character-select art","progress":75}';
  assert.deepEqual(parseProgressEvent(line), {
    key: "portrait",
    label: "Painting character-select art",
    progress: 75,
  });
  assert.equal(parseProgressEvent("@@opensmash not-json"), null);
});

test("submission visibility defaults public and requires rights attestation", () => {
  assert.deepEqual(submissionSettings({ rightsAttested: "true" }), { visibility: "public" });
  assert.deepEqual(
    submissionSettings({ rightsAttested: "true", visibility: "private" }),
    { visibility: "private" },
  );
  assert.throws(
    () => submissionSettings({ visibility: "public" }),
    (error) => error.status === 400 && /rights or permission/.test(error.message),
  );
});

test("private fighter assets are only accessible to their uploader", () => {
  const privateJob = { visibility: "private", ownerId: "owner-1" };
  assert.equal(isJobAccessible(privateJob, "owner-1"), true);
  assert.equal(isJobAccessible(privateJob, "owner-2"), false);
  assert.equal(isJobAccessible(privateJob), false);
  assert.equal(isJobAccessible({ visibility: "public", ownerId: "owner-1" }), true);
});
