import path from "node:path";
import { fileURLToPath } from "node:url";
import { createFighterJobs } from "./fighter-jobs.js";
import { createJobDatabase } from "./job-database.js";
import { createObjectStore } from "./object-store.js";

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(APP_ROOT, "..", "..");
const ENGINE_ROOT = path.join(REPO_ROOT, "BattleShip", "web-dist");
const PIPELINE_UI_ROOT = path.join(REPO_ROOT, "pipeline", "play", "ui");
const jobsRoot = path.resolve(
  process.env.FIGHTER_JOBS_ROOT || path.join(APP_ROOT, "data", "fighter-jobs"),
);

const jobId = process.env.JOB_ID;
if (!jobId) throw new Error("JOB_ID is required");

const executionId = process.env.CLOUD_RUN_EXECUTION ||
  `manual-${process.pid}-${process.env.CLOUD_RUN_TASK_ATTEMPT || "0"}`;
const objectStore = createObjectStore({ appRoot: APP_ROOT });
const jobDatabase = createJobDatabase({ jobsRoot });
const fighterJobs = createFighterJobs({
  appRoot: APP_ROOT,
  repoRoot: REPO_ROOT,
  engineRoot: ENGINE_ROOT,
  pipelineUiRoot: PIPELINE_UI_ROOT,
  objectStore,
  jobDatabase,
  dispatcher: { driver: "external" },
});

await objectStore.init();
await jobDatabase.init();
await fighterJobs.init({ loadAll: false });

const result = await fighterJobs.runSingle(jobId, executionId);
if (!result) throw new Error(`Fighter job '${jobId}' does not exist`);
console.log(JSON.stringify({
  jobId,
  executionId,
  status: result.status,
  revision: result.revision,
}));
