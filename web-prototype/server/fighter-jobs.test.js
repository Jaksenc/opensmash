import assert from "node:assert/strict";
import test from "node:test";
import { automaticRetryPlan, parseProgressEvent } from "./fighter-jobs.js";

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
