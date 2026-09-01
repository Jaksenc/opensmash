import Busboy from "busboy";
import { randomUUID } from "node:crypto";
import { createWriteStream } from "node:fs";
import {
  access,
  appendFile,
  mkdir,
  open,
  readFile,
  readdir,
  rm,
  stat,
} from "node:fs/promises";
import path from "node:path";
import { execFile, spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import { promisify } from "node:util";
import { ACTIVE_JOB_STATUSES, jobSnapshot, publicJob } from "./job-protocol.js";

const execFileAsync = promisify(execFile);

const MAX_PHOTO_BYTES = 12 * 1024 * 1024;
const PHOTO_TYPES = new Map([
  ["image/jpeg", { extension: ".jpg", magic: (bytes) => bytes[0] === 0xff && bytes[1] === 0xd8 }],
  ["image/png", { extension: ".png", magic: (bytes) => bytes.subarray(0, 8).equals(Buffer.from("89504e470d0a1a0a", "hex")) }],
  ["image/webp", { extension: ".webp", magic: (bytes) => bytes.subarray(0, 4).toString() === "RIFF" && bytes.subarray(8, 12).toString() === "WEBP" }],
]);

const STAGES = [
  { match: "expand:", key: "expand", label: "Describing the fighter", progress: 6 },
  { match: "character:", key: "character", label: "Fighter concept ready", progress: 12 },
  { match: "tpose:", key: "tpose", label: "Generating the model sheet", progress: 18 },
  { match: "mesh: uploading", key: "mesh-upload", label: "Starting the 3D model", progress: 27 },
  { match: "mesh: img3d", key: "mesh-build", label: "Building the 3D model", progress: 36 },
  { match: "mesh: rig task", key: "mesh-rig", label: "Rigging the fighter", progress: 45 },
  { match: "mesh:", key: "mesh", label: "3D model ready", progress: 50 },
  { match: "convert:", key: "convert", label: "Converting for the game", progress: 56 },
  { match: "variants:", key: "variants", label: "Building moveset variants", progress: 66 },
  { match: "portrait:", key: "portrait", label: "Painting character-select art", progress: 75 },
  { match: "stock:", key: "stock", label: "Drawing the stock icon", progress: 81 },
  { match: "emblem:", key: "emblem", label: "Designing the emblem", progress: 86 },
  { match: "ui:", key: "ui", label: "Packing game UI", progress: 91 },
  { match: "voice:", key: "voice", label: "Recording the announcer", progress: 95 },
  { match: "staged into", key: "publish", label: "Publishing the fighter", progress: 98 },
  { match: "done:", key: "complete", label: "Fighter ready", progress: 100 },
];

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function slugFor(name) {
  return name.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 16);
}

export function automaticRetryPlan(log, stage, retryCounts = {}) {
  const moderationRetries = retryCounts.moderation || 0;
  const isOutputModeration =
    log.includes("moderation_blocked") &&
    /["']moderation_stage["']\s*:\s*["']output["']/i.test(log);
  if (isOutputModeration && moderationRetries < 2) {
    const subject =
      stage === "portrait" ? "Portrait" :
        stage === "stock" ? "Stock icon" :
          stage === "emblem" ? "Emblem" : "Generated art";
    return {
      kind: "moderation",
      delayMs: 1_500,
      label: `${subject} was blocked; rerolling automatically (${moderationRetries + 1}/2)`,
    };
  }

  const transientRetries = retryCounts.transient || 0;
  const expensiveMeshStage = new Set(["mesh-upload", "mesh-build", "mesh-rig", "mesh"]).has(stage);
  const isTransient = /HTTP (?:429|5\d\d)\b|rate[_ -]?limit|server_error|ETIMEDOUT|ECONNRESET|TimeoutError|timed out/i.test(log);
  if (isTransient && !expensiveMeshStage && transientRetries < 3) {
    return {
      kind: "transient",
      delayMs: 2_000 * (2 ** transientRetries),
      label: `Provider temporarily unavailable; retrying automatically (${transientRetries + 1}/3)`,
    };
  }
  return null;
}

export function parseProgressEvent(line) {
  if (!line.startsWith("@@opensmash ")) return null;
  try {
    const event = JSON.parse(line.slice("@@opensmash ".length));
    if (
      event.protocolVersion !== 1 ||
      event.type !== "job.progress" ||
      typeof event.stage !== "string" ||
      typeof event.label !== "string" ||
      !Number.isInteger(event.progress) ||
      event.progress < 0 ||
      event.progress > 100
    ) return null;
    return { key: event.stage, label: event.label, progress: event.progress };
  } catch {
    return null;
  }
}

async function readMagic(filePath) {
  const handle = await open(filePath, "r");
  try {
    const bytes = Buffer.alloc(16);
    const { bytesRead } = await handle.read(bytes, 0, bytes.length, 0);
    return bytes.subarray(0, bytesRead);
  } finally {
    await handle.close();
  }
}

async function receiveForm(req, jobRoot) {
  const contentType = req.headers["content-type"] || "";
  if (!contentType.startsWith("multipart/form-data")) {
    throw new HttpError(415, "Use a multipart form with a photo.");
  }

  await mkdir(jobRoot, { recursive: false });
  const fields = {};
  let photo = null;
  let uploadError = null;
  const writes = [];

  await new Promise((resolve, reject) => {
    let parser;
    try {
      parser = Busboy({
        headers: req.headers,
        limits: { files: 1, fileSize: MAX_PHOTO_BYTES, fields: 3, fieldSize: 512, parts: 4 },
      });
    } catch (error) {
      reject(new HttpError(400, error.message || "Could not read that form."));
      return;
    }

    parser.on("field", (name, value) => {
      if (name === "name" || name === "emblem") fields[name] = value;
    });
    parser.on("file", (fieldName, stream, info) => {
      if (fieldName !== "photo" || photo) {
        uploadError ||= new HttpError(400, "Upload exactly one fighter photo.");
        stream.resume();
        return;
      }
      const type = PHOTO_TYPES.get(info.mimeType);
      if (!type) {
        uploadError ||= new HttpError(415, "Use a JPEG, PNG, or WebP photo.");
        stream.resume();
        return;
      }

      const filePath = path.join(jobRoot, `photo${type.extension}`);
      photo = { path: filePath, type, mimeType: info.mimeType, originalName: info.filename || "photo" };
      const destination = createWriteStream(filePath, { flags: "wx", mode: 0o600 });
      stream.on("limit", () => {
        uploadError ||= new HttpError(413, "The photo must be 12 MB or smaller.");
      });
      const finished = new Promise((writeResolve, writeReject) => {
        destination.on("close", writeResolve);
        destination.on("error", writeReject);
        stream.on("error", writeReject);
      });
      writes.push(finished);
      stream.pipe(destination);
    });
    parser.on("filesLimit", () => {
      uploadError ||= new HttpError(400, "Upload exactly one fighter photo.");
    });
    parser.on("partsLimit", () => {
      uploadError ||= new HttpError(400, "That form has too many fields.");
    });
    parser.on("error", reject);
    parser.on("finish", resolve);
    req.on("aborted", () => reject(new HttpError(400, "Upload interrupted.")));
    req.pipe(parser);
  });

  await Promise.all(writes);
  if (uploadError) throw uploadError;
  if (!photo) throw new HttpError(400, "Choose a fighter photo.");

  const info = await stat(photo.path);
  if (!info.size) throw new HttpError(400, "The uploaded photo is empty.");
  const bytes = await readMagic(photo.path);
  if (!photo.type.magic(bytes)) throw new HttpError(415, "The uploaded file is not a valid photo.");

  return { fields, photo };
}

export function createFighterJobs({ appRoot, repoRoot, engineRoot, pipelineUiRoot, objectStore, jobDatabase, dispatcher }) {
  const jobsRoot = path.resolve(process.env.FIGHTER_JOBS_ROOT || path.join(appRoot, "data", "fighter-jobs"));
  const pipelineRoot = path.join(repoRoot, "pipeline");
  const pipelineScript = path.join(pipelineRoot, "pipeline", "run_character.py");
  const normalizeImageScript = path.join(appRoot, "server", "normalize-image.py");
  const jobs = new Map();
  const queue = [];
  const events = new EventEmitter();
  events.setMaxListeners(0);
  const localExecution = dispatcher.driver === "local";
  const leaseSeconds = Number(process.env.FIGHTER_LEASE_SECONDS || 15 * 60);
  const maxActivePerOwner = Number(process.env.MAX_ACTIVE_JOBS_PER_OWNER || 1);
  const maxDailyPerOwner = Number(process.env.MAX_DAILY_JOBS_PER_OWNER || 3);
  const maxGlobalActive = Number(process.env.MAX_GLOBAL_ACTIVE_JOBS || 20);
  let stopDatabaseWatch = null;
  let workerBusy = false;

  function jobRoot(id) {
    return path.join(jobsRoot, id);
  }

  async function saveJob(job, { bumpRevision = true } = {}) {
    if (bumpRevision) {
      job.revision = (job.revision || 0) + 1;
      job.updatedAt = new Date().toISOString();
    }
    if (job.lease?.executionId) {
      job.lease.expiresAt = new Date(Date.now() + leaseSeconds * 1000).toISOString();
    }
    await jobDatabase.save(job);
    events.emit(job.id, jobSnapshot(job));
  }

  async function insertJob(job) {
    job.revision = (job.revision || 0) + 1;
    job.updatedAt = new Date().toISOString();
    await jobDatabase.insert(job);
    events.emit(job.id, jobSnapshot(job));
  }

  function normalizeStoredJob(job) {
    job.revision ||= 0;
    job.protocolVersion ||= 1;
    job.updatedAt ||= job.createdAt;
    job.attempt ||= 0;
    job.retry ||= {
      automaticCounts: job.automaticRetryCounts || { moderation: 0, transient: 0 },
      nextAttemptAt: job.nextAttemptAt || null,
      label: job.retryLabel || null,
    };
    delete job.automaticRetryCounts;
    delete job.nextAttemptAt;
    delete job.retryLabel;
    return job;
  }

  async function loadJobs() {
    await mkdir(jobsRoot, { recursive: true });
    const storedJobs = await jobDatabase.list();
    for (const job of storedJobs) {
      try {
        if (!job.id) continue;
        normalizeStoredJob(job);
        if (localExecution && (job.status === "running" || job.status === "retrying")) {
          job.status = "queued";
          job.stage = "queued";
          job.stageLabel = "Recovered after server restart";
          job.progress = Math.min(job.progress || 0, 95);
          job.error = null;
          job.retry.nextAttemptAt = null;
          await saveJob(job);
        }
        if (
          job.status === "failed" &&
          (job.logTail || []).some((line) => line.includes("invalid_image_file"))
        ) {
          job.error = "The image provider rejected the reference photo. Resume to retry with a normalized copy.";
          await saveJob(job);
        }
        if (
          job.status === "failed" &&
          (job.logTail || []).some((line) => line.includes("moderation_blocked"))
        ) {
          if ((job.progress || 0) >= 75) {
            job.stageLabel = "Generated portrait was blocked";
            job.error = "The image provider blocked its generated portrait. The model and moveset variants are saved; reroll only the portrait to continue.";
            job.retry.label = "Reroll portrait";
          } else {
            job.stageLabel = "Generated art was blocked";
            job.error = "The image provider blocked generated art. Retry to reroll the missing stage.";
            job.retry.label = "Reroll art";
          }
          await saveJob(job);
        }
        jobs.set(job.id, job);
        if (localExecution && job.status === "queued") queue.push(job.id);
      } catch (error) {
        console.warn(`Skipping fighter job '${job.id || "unknown"}': ${error.message}`);
      }
    }
    queue.sort((left, right) => jobs.get(left).createdAt.localeCompare(jobs.get(right).createdAt));
  }

  async function restoreCheckpoint(job) {
    for (const file of job.checkpoint?.files || []) {
      const destination = file.scope === "play"
        ? path.join(pipelineRoot, "play", file.name)
        : path.join(pipelineUiRoot, job.slug, file.name);
      await objectStore.getFile(file.key, destination);
    }
  }

  async function saveFailureCheckpoint(job) {
    const outputRoot = path.join(pipelineUiRoot, job.slug);
    const checkpointRoot = `characters/${job.slug}/checkpoints/${job.id}`;
    const candidates = [
      "character.json", "cost.json", "tpose.png", "rigged.glb", "bundle.json",
      "portrait_raw.png", "stock_raw.png", "emblem_raw.png", `${job.slug}.osbui`,
      "announcer.wav",
    ];
    const files = [];
    for (const name of candidates) {
      const source = path.join(outputRoot, name);
      try {
        await access(source);
        const artifact = await objectStore.putFile(
          `${checkpointRoot}/output/${name}`, source, { public: false },
        );
        files.push({ ...artifact, scope: "output", name });
      } catch {
        // Missing files simply mean that stage had not completed yet.
      }
    }
    const playRoot = path.join(pipelineRoot, "play");
    try {
      const bundles = (await readdir(playRoot))
        .filter((name) => (name === `${job.slug}.osb` || name.startsWith(`${job.slug}-`)) && name.endsWith(".osb"));
      for (const name of bundles) {
        const artifact = await objectStore.putFile(
          `${checkpointRoot}/play/${name}`, path.join(playRoot, name), { public: false },
        );
        files.push({ ...artifact, scope: "play", name });
      }
    } catch {
      // The play directory may not exist if generation failed very early.
    }
    if (files.length) {
      job.checkpoint = { savedAt: new Date().toISOString(), files };
    }
  }

  async function finishJob(job, code, signal, attemptLog = "") {
    if (code === 0) {
      try {
        const outputRoot = path.join(pipelineUiRoot, job.slug);
        await Promise.all([
          access(path.join(outputRoot, "portrait_raw.png")),
          access(path.join(engineRoot, "bundles", `${job.slug}.osb`)),
          access(path.join(engineRoot, "bundles", `${job.slug}.osbui`)),
          access(path.join(engineRoot, "bundles", `${job.slug}.wav`)),
        ]);
        const metadata = JSON.parse(await readFile(path.join(outputRoot, "character.json"), "utf8"));
        let cost = null;
        try {
          cost = JSON.parse(await readFile(path.join(outputRoot, "cost.json"), "utf8"));
        } catch {
          // Cost reporting is helpful but not required to play the fighter.
        }
        job.displayName = metadata.display || job.name;
        job.short = metadata.short || job.displayName;
        job.costUsd = cost?.total_usd ?? null;
        const version = `${job.id}-${job.attempt}`;
        const versionRoot = `characters/${job.slug}/versions/${version}`;
        const bundleRoot = path.join(engineRoot, "bundles");
        const variantFiles = (await readdir(bundleRoot))
          .filter((name) => name.startsWith(`${job.slug}-`) && name.endsWith(".osb"))
          .sort();
        const variants = {};
        for (const fileName of variantFiles) {
          const fighter = fileName.slice(job.slug.length + 1, -4);
          variants[fighter] = await objectStore.putFile(
            `${versionRoot}/injection/${fileName}`,
            path.join(bundleRoot, fileName),
            { contentType: "application/octet-stream", public: true },
          );
        }
        job.artifacts = {
          portrait: await objectStore.putFile(
            `${versionRoot}/portrait.png`,
            path.join(outputRoot, "portrait_raw.png"),
            { contentType: "image/png", public: true },
          ),
          announcer: await objectStore.putFile(
            `${versionRoot}/announcer.wav`,
            path.join(bundleRoot, `${job.slug}.wav`),
            { contentType: "audio/wav", public: true },
          ),
          bundle: await objectStore.putFile(
            `${versionRoot}/injection/${job.slug}.osb`,
            path.join(bundleRoot, `${job.slug}.osb`),
            { contentType: "application/octet-stream", public: true },
          ),
          ui: await objectStore.putFile(
            `${versionRoot}/injection/${job.slug}.osbui`,
            path.join(bundleRoot, `${job.slug}.osbui`),
            { contentType: "application/octet-stream", public: true },
          ),
          character: await objectStore.putFile(
            `${versionRoot}/character.json`,
            path.join(outputRoot, "character.json"),
            { contentType: "application/json", public: true },
          ),
          variants,
        };
        for (const [key, fileName] of [["stock", "stock_raw.png"], ["emblem", "emblem_raw.png"]]) {
          try {
            await access(path.join(outputRoot, fileName));
            job.artifacts[key] = await objectStore.putFile(
              `${versionRoot}/${key}.png`,
              path.join(outputRoot, fileName),
              { contentType: "image/png", public: true },
            );
          } catch {
            // Optional art is omitted from the manifest if the pipeline did not produce it.
          }
        }
        const manifest = {
          protocolVersion: 1,
          character: {
            slug: job.slug,
            name: metadata.display || job.name,
            short: metadata.short || metadata.display || job.name,
          },
          version,
          generatedAt: new Date().toISOString(),
          artifacts: job.artifacts,
        };
        job.artifacts.manifest = await objectStore.putJson(
          `${versionRoot}/manifest.json`, manifest, { public: true },
        );
        job.artifacts.latest = await objectStore.putJson(
          `characters/${job.slug}/latest.json`,
          {
            protocolVersion: 1,
            slug: job.slug,
            version,
            manifest: job.artifacts.manifest,
            updatedAt: new Date().toISOString(),
          },
          { public: true, immutable: false },
        );
        job.status = "complete";
        job.stage = "complete";
        job.stageLabel = "Fighter ready";
        job.progress = 100;
        job.completedAt = new Date().toISOString();
        job.retry.nextAttemptAt = null;
        job.error = null;
      } catch (error) {
        job.status = "failed";
        job.stage = "failed";
        job.stageLabel = "Generation finished without playable files";
        job.error = error.message;
      }
    } else {
      const failedStage = job.stage;
      job.status = "failed";
      job.stage = "failed";
      job.stageLabel = "Generation stopped";
      const joinedLog = attemptLog || (job.logTail || []).join("\n");
      if (joinedLog.includes("invalid_image_file")) {
        job.error = "The image provider rejected the reference photo. Resume to retry with a normalized copy.";
        job.retry.label = "Resume generation";
      } else if (joinedLog.includes("moderation_blocked")) {
        if (failedStage === "portrait") {
          job.stageLabel = "Generated portrait was blocked";
          job.error = "The image provider blocked its generated portrait. The model and moveset variants are saved; reroll only the portrait to continue.";
          job.retry.label = "Reroll portrait";
        } else {
          job.stageLabel = "Generated art was blocked";
          job.error = "The image provider blocked generated art. Retry to reroll the missing stage.";
          job.retry.label = "Reroll art";
        }
      } else {
        const lastUsefulLine = [...(job.logTail || [])].reverse().find((line) => /failed|error|runtime/i.test(line));
        job.error = lastUsefulLine || `Pipeline exited ${signal ? `after ${signal}` : `with code ${code}`}.`;
        job.retry.label = "Resume generation";
      }
    }
    if (job.status === "failed") {
      try {
        await saveFailureCheckpoint(job);
      } catch (error) {
        job.logTail = [...(job.logTail || []), `checkpoint: ${error.message}`].slice(-24);
      }
    }
    job.lease = null;
    await saveJob(job);
  }

  function stageFromLine(line) {
    const normalized = line.toLowerCase();
    return STAGES.find((stage) => normalized.includes(stage.match.toLowerCase()));
  }

  async function runJob(job, { automatic = false } = {}) {
    workerBusy = true;
    job.attempt = (job.attempt || 0) + 1;
    job.status = "running";
    if (!automatic) {
      job.stage = "photo";
      job.stageLabel = "Preparing the reference photo";
      job.progress = 1;
    }
    job.startedAt ||= new Date().toISOString();
    job.error = null;
    job.retry.nextAttemptAt = null;
    await saveJob(job);

    const normalizedPhoto = path.join(jobRoot(job.id), "photo-normalized.png");
    try {
      await restoreCheckpoint(job);
      const localPhoto = path.join(jobRoot(job.id), job.photoFile);
      try {
        await access(localPhoto);
      } catch (error) {
        if (error.code !== "ENOENT" || !job.input?.key) throw error;
        await objectStore.getFile(job.input.key, localPhoto);
      }
      await execFileAsync(
        process.env.PYTHON || "python3",
        [normalizeImageScript, localPhoto, normalizedPhoto],
        { cwd: appRoot, timeout: 120_000, maxBuffer: 1024 * 1024 },
      );
      job.normalizedPhotoFile = path.basename(normalizedPhoto);
      if (!automatic) {
        job.stage = "starting";
        job.stageLabel = "Starting the fighter pipeline";
        job.progress = 2;
      }
      await saveJob(job);
    } catch (error) {
      job.status = "failed";
      job.stage = "failed";
      job.stageLabel = "Could not prepare the reference photo";
      job.error = "That photo could not be converted into a standard RGB image.";
      job.logTail = [...(job.logTail || []), error.message].slice(-24);
      job.lease = null;
      await saveJob(job);
      workerBusy = false;
      void runNext();
      return;
    }

    const args = [pipelineScript, job.name, "--photo", normalizedPhoto, "--out", path.join(pipelineUiRoot, job.slug)];
    if (job.emblem) args.push("--emblem", job.emblem);
    const child = spawn(process.env.PYTHON || "python3", args, {
      cwd: pipelineRoot,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const logPath = path.join(jobRoot(job.id), "run.log");
    let pending = "";
    let saveTimer = null;
    const attemptLines = [];

    function scheduleSave() {
      if (saveTimer) return;
      saveTimer = setTimeout(() => {
        saveTimer = null;
        saveJob(job).catch((error) => console.error("Could not save fighter progress:", error));
      }, 150);
    }

    function consume(text) {
      appendFile(logPath, text).catch((error) => console.error("Could not append fighter log:", error));
      pending += text;
      const lines = pending.split(/\r?\n/);
      pending = lines.pop() || "";
      for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line) continue;
        attemptLines.push(line);
        if (attemptLines.length > 200) attemptLines.shift();
        const structuredStage = parseProgressEvent(line);
        if (!structuredStage) job.logTail = [...(job.logTail || []), line].slice(-24);
        const stage = structuredStage || stageFromLine(line);
        if (stage && stage.progress >= (job.progress || 0)) {
          job.stage = stage.key;
          job.stageLabel = stage.label;
          job.progress = stage.progress;
        }
      }
      scheduleSave();
    }

    await new Promise((resolve) => {
      let spawnError = null;
      child.stdout.on("data", (chunk) => consume(chunk.toString()));
      child.stderr.on("data", (chunk) => consume(chunk.toString()));
      child.on("error", (error) => {
        spawnError = error;
      });
      child.on("close", async (code, signal) => {
        if (saveTimer) clearTimeout(saveTimer);
        if (pending.trim()) {
          const finalLine = pending;
          pending = "";
          consume(`${finalLine}\n`);
          if (saveTimer) clearTimeout(saveTimer);
        }
        if (spawnError) {
          job.logTail = [...(job.logTail || []), spawnError.message].slice(-24);
          job.status = "failed";
          job.stage = "failed";
          job.stageLabel = "Could not start the pipeline";
          job.error = spawnError.message;
          job.lease = null;
          await saveJob(job);
          workerBusy = false;
          void runNext();
          resolve();
          return;
        }
        const attemptLog = attemptLines.join("\n");
        const retryPlan = code === 0
          ? null
          : automaticRetryPlan(attemptLog, job.stage, job.retry.automaticCounts);
        if (retryPlan) {
          job.retry.automaticCounts[retryPlan.kind] += 1;
          job.status = "retrying";
          job.stageLabel = retryPlan.label;
          job.retry.nextAttemptAt = new Date(Date.now() + retryPlan.delayMs).toISOString();
          job.error = null;
          job.retry.label = null;
          await saveJob(job);
          setTimeout(async () => {
            await runJob(job, { automatic: true });
            resolve();
          }, retryPlan.delayMs);
          return;
        }
        await finishJob(job, code, signal, attemptLog);
        workerBusy = false;
        void runNext();
        resolve();
      });
    });
    return publicJob(job);
  }

  async function runNext() {
    if (!localExecution || workerBusy || process.env.FIGHTER_WORKER_DISABLED === "1") return;
    while (queue.length) {
      const id = queue.shift();
      const job = jobs.get(id);
      if (job?.status === "queued") {
        await runJob(job);
        return;
      }
    }
  }

  async function dispatch(job) {
    if (localExecution) {
      queue.push(job.id);
      void runNext();
      return;
    }
    try {
      const result = await dispatcher.dispatch(job);
      job.dispatch = {
        driver: dispatcher.driver,
        executionName: result.executionName,
        dispatchedAt: new Date().toISOString(),
      };
      job.stageLabel = "Generation worker scheduled";
      await saveJob(job);
    } catch (error) {
      job.status = "failed";
      job.stage = "dispatch";
      job.stageLabel = "Could not schedule generation";
      job.error = error.message;
      job.retry.label = "Retry scheduling";
      await saveJob(job);
      throw new HttpError(503, "Generation could not be scheduled. Retry this job.");
    }
  }

  async function reconcileStaleJobs() {
    if (localExecution) return;
    const now = Date.now();
    const dispatchTimeout = Number(process.env.FIGHTER_DISPATCH_TIMEOUT_SECONDS || 10 * 60) * 1000;
    for (const job of jobs.values()) {
      const leaseExpiry = Date.parse(job.lease?.expiresAt || "");
      const leaseExpired =
        (job.status === "running" || job.status === "retrying") &&
        (!Number.isFinite(leaseExpiry) || leaseExpiry < now);
      const neverClaimed =
        job.status === "queued" &&
        job.dispatch?.dispatchedAt &&
        Date.parse(job.dispatch.dispatchedAt) + dispatchTimeout < now;
      if (!leaseExpired && !neverClaimed) continue;
      job.status = "failed";
      job.stage = "interrupted";
      job.stageLabel = "Generation worker was interrupted";
      job.error = "The worker stopped reporting progress. Resume to continue from its last saved checkpoint.";
      job.retry.label = "Resume generation";
      job.lease = null;
      await saveJob(job);
    }
  }

  function assertCreationQuota(ownerId) {
    if (!ownerId) throw new HttpError(401, "A validated ROM session is required.");
    const allJobs = [...jobs.values()];
    const activeForOwner = allJobs.filter(
      (job) => job.ownerId === ownerId && ACTIVE_JOB_STATUSES.has(job.status),
    ).length;
    if (activeForOwner >= maxActivePerOwner) {
      throw new HttpError(429, "Finish your current fighter before starting another.");
    }
    const startOfDay = Date.now() - 24 * 60 * 60 * 1000;
    const dailyForOwner = allJobs.filter(
      (job) => job.ownerId === ownerId && Date.parse(job.createdAt) >= startOfDay,
    ).length;
    if (dailyForOwner >= maxDailyPerOwner) {
      throw new HttpError(429, "This session has reached its daily fighter limit.");
    }
    const globalActive = allJobs.filter((job) => ACTIVE_JOB_STATUSES.has(job.status)).length;
    if (globalActive >= maxGlobalActive) {
      throw new HttpError(503, "The fighter queue is full. Try again shortly.");
    }
  }

  function ownedJob(id, ownerId) {
    const job = jobs.get(id);
    return job && (!ownerId || job.ownerId === ownerId) ? job : null;
  }

  async function create(req, ownerId) {
    assertCreationQuota(ownerId);
    const id = randomUUID();
    const root = jobRoot(id);
    try {
      const { fields, photo } = await receiveForm(req, root);
      const name = String(fields.name || "").trim().replace(/\s+/g, " ");
      const emblem = String(fields.emblem || "").trim().replace(/\s+/g, " ");
      if (!name || name.length > 80) throw new HttpError(400, "Enter a fighter name up to 80 characters.");
      if (emblem.length > 200) throw new HttpError(400, "Keep the emblem description under 200 characters.");
      const slug = slugFor(name);
      if (!slug) throw new HttpError(400, "The fighter name must contain at least one A–Z letter or number.");

      const duplicate = [...jobs.values()].find((job) => job.slug === slug);
      if (duplicate) throw new HttpError(409, `A generation for '${name}' already exists. Retry that job instead.`);
      try {
        await access(path.join(pipelineUiRoot, slug));
        throw new HttpError(409, `The pipeline already has a fighter with the slug '${slug}'.`);
      } catch (error) {
        if (error instanceof HttpError) throw error;
        if (error.code !== "ENOENT") throw error;
      }

      const now = new Date().toISOString();
      const input = await objectStore.putFile(
        `characters/${slug}/sources/${id}/photo${photo.type.extension}`,
        photo.path,
        { contentType: photo.mimeType, public: false },
      );
      const job = {
        protocolVersion: 1,
        id,
        ownerId,
        name,
        slug,
        emblem,
        photoName: path.basename(photo.originalName).slice(0, 160),
        photoFile: path.basename(photo.path),
        photoMimeType: photo.mimeType,
        status: "queued",
        stage: "queued",
        stageLabel: workerBusy ? "Waiting for the current fighter" : "Queued for generation",
        progress: 0,
        createdAt: now,
        updatedAt: now,
        revision: 0,
        attempt: 0,
        startedAt: null,
        completedAt: null,
        error: null,
        retry: {
          automaticCounts: { moderation: 0, transient: 0 },
          nextAttemptAt: null,
          label: null,
        },
        input,
        logTail: [],
      };
      jobs.set(id, job);
      try {
        await insertJob(job);
      } catch (error) {
        jobs.delete(id);
        if (error.code === "DUPLICATE_SLUG") {
          throw new HttpError(409, `A generation for '${name}' already exists.`);
        }
        throw error;
      }
      await dispatch(job);
      return publicJob(job);
    } catch (error) {
      await rm(root, { recursive: true, force: true });
      throw error;
    }
  }

  async function retry(id, ownerId) {
    const job = ownedJob(id, ownerId);
    if (!job) throw new HttpError(404, "Fighter job not found.");
    if (ACTIVE_JOB_STATUSES.has(job.status)) throw new HttpError(409, "That fighter is already being generated.");
    if (job.status === "complete") throw new HttpError(409, "That fighter is already complete.");
    job.status = "queued";
    job.stage = "queued";
    job.stageLabel = workerBusy ? "Waiting for the current fighter" : "Queued to resume";
    job.progress = 0;
    job.error = null;
    job.retry = {
      automaticCounts: { moderation: 0, transient: 0 },
      nextAttemptAt: null,
      label: null,
    };
    job.completedAt = null;
    await saveJob(job);
    await dispatch(job);
    return publicJob(job);
  }

  return {
    async init({ loadAll = true } = {}) {
      if (loadAll) await loadJobs();
      stopDatabaseWatch = loadAll ? jobDatabase.watch((job) => {
        const current = jobs.get(job.id);
        if (!current || (job.revision || 0) > (current.revision || 0)) {
          jobs.set(job.id, job);
          events.emit(job.id, jobSnapshot(job));
        }
      }) : null;
      if (loadAll && !localExecution) {
        await reconcileStaleJobs();
        setInterval(() => {
          reconcileStaleJobs().catch((error) => console.error("Stale job reconciliation failed:", error));
        }, 60_000).unref();
      }
      void runNext();
    },
    async create(req, ownerId) {
      return create(req, ownerId);
    },
    list(ownerId = null) {
      return [...jobs.values()]
        .filter((job) => !ownerId || job.ownerId === ownerId)
        .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
        .map(publicJob);
    },
    get(id, ownerId = null) {
      const job = ownedJob(id, ownerId);
      return job ? publicJob(job) : null;
    },
    subscribe(id, ownerId, listener) {
      const job = ownedJob(id, ownerId);
      if (!job) return null;
      events.on(id, listener);
      listener(jobSnapshot(job));
      return () => events.off(id, listener);
    },
    async retry(id, ownerId) {
      return retry(id, ownerId);
    },
    async runSingle(id, executionId) {
      const claim = await jobDatabase.claim(id, executionId, leaseSeconds);
      if (!claim.claimed) return claim.job ? publicJob(normalizeStoredJob(claim.job)) : null;
      const job = normalizeStoredJob(claim.job);
      jobs.set(job.id, job);
      return runJob(job);
    },
    portraitPath(id) {
      const job = jobs.get(id);
      return job ? path.join(pipelineUiRoot, job.slug, "portrait_raw.png") : null;
    },
    announcerPath(id) {
      const job = jobs.get(id);
      return job ? path.join(pipelineUiRoot, job.slug, "announcer.wav") : null;
    },
    HttpError,
  };
}
