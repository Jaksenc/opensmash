import assert from "node:assert/strict";
import test from "node:test";
import { jobSnapshot, publicJob } from "./job-protocol.js";

const completeJob = {
  id: "5a4d1d48-112f-47fb-b690-a78872f630ee",
  revision: 7,
  name: "Test Fighter",
  slug: "testfighter",
  emblem: "",
  status: "complete",
  stage: "complete",
  stageLabel: "Fighter ready",
  progress: 100,
  attempt: 2,
  createdAt: "2026-08-31T10:00:00.000Z",
  updatedAt: "2026-08-31T10:05:00.000Z",
  completedAt: "2026-08-31T10:05:00.000Z",
  artifacts: {
    portrait: { key: "portrait.png", url: "https://cdn.example/portrait.png" },
    announcer: { key: "announcer.wav", url: "https://cdn.example/announcer.wav" },
    bundle: { key: "fighter.osb", url: "https://cdn.example/fighter.osb" },
    ui: { key: "fighter.osbui", url: "https://cdn.example/fighter.osbui" },
  },
};

test("public job snapshots expose protocol and immutable artifact URLs", () => {
  const result = publicJob({ ...completeJob, ownerId: "private-owner" });
  assert.equal(result.protocolVersion, 1);
  assert.equal(result.revision, 7);
  assert.equal(result.character.portrait, completeJob.artifacts.portrait.url);
  assert.equal(result.character.bundleUrl, completeJob.artifacts.bundle.url);
  assert.equal(result.character.uiUrl, completeJob.artifacts.ui.url);
  assert.equal("ownerId" in result, false);
});

test("SSE payloads are versioned snapshots", () => {
  const event = jobSnapshot(completeJob);
  assert.equal(event.type, "job.snapshot");
  assert.equal(event.protocolVersion, 1);
  assert.equal(event.job.status, "complete");
});

test("existing private jobs are backfilled with cacheable capability URLs", () => {
  const result = publicJob({
    ...completeJob,
    visibility: "private",
    ownerId: "firebase-uid",
    uploader: {
      uid: "firebase-uid",
      displayName: "Uploader",
      email: "private@example.com",
    },
    artifacts: Object.fromEntries(
      Object.entries(completeJob.artifacts).map(([name, artifact]) => [name, { ...artifact, url: null }]),
    ),
  });

  assert.equal(result.visibility, "private");
  assert.deepEqual(result.uploader, { displayName: "Uploader" });
  assert.match(result.character.bundleUrl, /^\/engine\/bundles\/testfighter-[A-Za-z0-9]{16}\.osb6$/);
  assert.match(result.character.portraitFull, /^\/engine\/fighters\/testfighter-[A-Za-z0-9]{16}\/portrait\.png$/);
  assert.equal("ownerId" in result, false);
  assert.equal(JSON.stringify(result).includes("private@example.com"), false);
  assert.equal(JSON.stringify(result).includes("firebase-uid"), false);
});

test("private jobs with an asset capability expose conventional immutable bundle names", () => {
  const result = publicJob({
    ...completeJob,
    visibility: "private",
    ownerId: "firebase-uid",
    assetCapability: "Ab3Def4Gh5Jk6Lm7",
    artifacts: Object.fromEntries(
      Object.entries(completeJob.artifacts).map(([name, artifact]) => [name, { ...artifact, url: null }]),
    ),
  });

  assert.equal(
    result.character.bundleUrl,
    "/engine/bundles/testfighter-Ab3Def4Gh5Jk6Lm7.osb6",
  );
  assert.equal(
    result.character.uiUrl,
    "/engine/bundles/testfighter-Ab3Def4Gh5Jk6Lm7.osbui",
  );
  assert.equal(
    result.character.voiceUrl,
    "/engine/bundles/testfighter-Ab3Def4Gh5Jk6Lm7.wav",
  );
  assert.equal(
    result.character.portraitFull,
    "/engine/fighters/testfighter-Ab3Def4Gh5Jk6Lm7/portrait.png",
  );
});
