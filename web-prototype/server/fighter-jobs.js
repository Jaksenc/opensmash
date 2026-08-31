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
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { execFile, spawn } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const MAX_PHOTO_BYTES = 12 * 1024 * 1024;
const ACTIVE_STATUSES = new Set(["queued", "running"]);
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

function publicJob(job) {
  const result = {
    id: job.id,
    name: job.name,
    slug: job.slug,
    emblem: job.emblem,
    status: job.status,
    stage: job.stage,
    stageLabel: job.stageLabel,
    progress: job.progress,
    createdAt: job.createdAt,
    startedAt: job.startedAt || null,
    completedAt: job.completedAt || null,
    error: job.error || null,
    retryLabel: job.retryLabel || null,
    logTail: job.logTail || [],
    photoName: job.photoName,
  };

  if (job.status === "complete") {
    result.character = {
      slug: job.slug,
      name: job.displayName || job.name,
      short: job.short || job.name,
      portrait: `/api/fighters/${job.id}/portrait?v=${encodeURIComponent(job.completedAt || "")}`,
      announcer: `/api/fighters/${job.id}/announcer?v=${encodeURIComponent(job.completedAt || "")}`,
      fkind: 0,
      bundle: `${job.slug}.osb`,
    };
    result.costUsd = job.costUsd ?? null;
  }
  return result;
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

export function createFighterJobs({ appRoot, repoRoot, engineRoot, pipelineUiRoot }) {
  const jobsRoot = path.resolve(process.env.FIGHTER_JOBS_ROOT || path.join(appRoot, "data", "fighter-jobs"));
  const pipelineRoot = path.join(repoRoot, "pipeline");
  const pipelineScript = path.join(pipelineRoot, "pipeline", "run_character.py");
  const normalizeImageScript = path.join(appRoot, "server", "normalize-image.py");
  const jobs = new Map();
  const queue = [];
  let workerBusy = false;

  function jobRoot(id) {
    return path.join(jobsRoot, id);
  }

  async function saveJob(job) {
    const finalPath = path.join(jobRoot(job.id), "job.json");
    const temporaryPath = `${finalPath}.${randomUUID()}.tmp`;
    await writeFile(temporaryPath, `${JSON.stringify(job, null, 2)}\n`, { mode: 0o600 });
    await rename(temporaryPath, finalPath);
  }

  async function loadJobs() {
    await mkdir(jobsRoot, { recursive: true });
    const entries = await readdir(jobsRoot, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory() || entry.name.startsWith(".")) continue;
      try {
        const job = JSON.parse(await readFile(path.join(jobsRoot, entry.name, "job.json"), "utf8"));
        if (job.id !== entry.name) continue;
        if (job.status === "running") {
          job.status = "queued";
          job.stage = "queued";
          job.stageLabel = "Recovered after server restart";
          job.progress = Math.min(job.progress || 0, 95);
          job.error = null;
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
            job.retryLabel = "Reroll portrait";
          } else {
            job.stageLabel = "Generated art was blocked";
            job.error = "The image provider blocked generated art. Retry to reroll the missing stage.";
            job.retryLabel = "Reroll art";
          }
          await saveJob(job);
        }
        jobs.set(job.id, job);
        if (job.status === "queued") queue.push(job.id);
      } catch (error) {
        console.warn(`Skipping fighter job '${entry.name}': ${error.message}`);
      }
    }
    queue.sort((left, right) => jobs.get(left).createdAt.localeCompare(jobs.get(right).createdAt));
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
        job.status = "complete";
        job.stage = "complete";
        job.stageLabel = "Fighter ready";
        job.progress = 100;
        job.completedAt = new Date().toISOString();
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
        job.retryLabel = "Resume generation";
      } else if (joinedLog.includes("moderation_blocked")) {
        if (failedStage === "portrait") {
          job.stageLabel = "Generated portrait was blocked";
          job.error = "The image provider blocked its generated portrait. The model and moveset variants are saved; reroll only the portrait to continue.";
          job.retryLabel = "Reroll portrait";
        } else {
          job.stageLabel = "Generated art was blocked";
          job.error = "The image provider blocked generated art. Retry to reroll the missing stage.";
          job.retryLabel = "Reroll art";
        }
      } else {
        const lastUsefulLine = [...(job.logTail || [])].reverse().find((line) => /failed|error|runtime/i.test(line));
        job.error = lastUsefulLine || `Pipeline exited ${signal ? `after ${signal}` : `with code ${code}`}.`;
        job.retryLabel = "Resume generation";
      }
    }
    await saveJob(job);
  }

  function stageFromLine(line) {
    const normalized = line.toLowerCase();
    return STAGES.find((stage) => normalized.includes(stage.match.toLowerCase()));
  }

  async function runJob(job, { automatic = false } = {}) {
    workerBusy = true;
    job.status = "running";
    if (!automatic) {
      job.stage = "photo";
      job.stageLabel = "Preparing the reference photo";
      job.progress = 1;
    }
    job.startedAt ||= new Date().toISOString();
    job.error = null;
    await saveJob(job);

    const normalizedPhoto = path.join(jobRoot(job.id), "photo-normalized.png");
    try {
      await execFileAsync(
        process.env.PYTHON || "python3",
        [normalizeImageScript, path.join(jobRoot(job.id), job.photoFile), normalizedPhoto],
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
        job.logTail = [...(job.logTail || []), line].slice(-24);
        const stage = stageFromLine(line);
        if (stage && stage.progress >= (job.progress || 0)) {
          job.stage = stage.key;
          job.stageLabel = stage.label;
          job.progress = stage.progress;
        }
      }
      scheduleSave();
    }

    child.stdout.on("data", (chunk) => consume(chunk.toString()));
    child.stderr.on("data", (chunk) => consume(chunk.toString()));
    child.on("error", async (error) => {
      job.logTail = [...(job.logTail || []), error.message].slice(-24);
      job.status = "failed";
      job.stage = "failed";
      job.stageLabel = "Could not start the pipeline";
      job.error = error.message;
      await saveJob(job);
    });
    child.on("close", async (code, signal) => {
      if (saveTimer) clearTimeout(saveTimer);
      if (pending.trim()) {
        const finalLine = pending;
        pending = "";
        consume(`${finalLine}\n`);
      }
      const attemptLog = attemptLines.join("\n");
      const retryPlan = code === 0
        ? null
        : automaticRetryPlan(attemptLog, job.stage, job.automaticRetryCounts);
      if (retryPlan) {
        job.automaticRetryCounts ||= { moderation: 0, transient: 0 };
        job.automaticRetryCounts[retryPlan.kind] += 1;
        job.status = "running";
        job.stageLabel = retryPlan.label;
        job.error = null;
        job.retryLabel = null;
        await saveJob(job);
        setTimeout(() => void runJob(job, { automatic: true }), retryPlan.delayMs);
        return;
      }
      await finishJob(job, code, signal, attemptLog);
      workerBusy = false;
      void runNext();
    });
  }

  async function runNext() {
    if (workerBusy || process.env.FIGHTER_WORKER_DISABLED === "1") return;
    while (queue.length) {
      const id = queue.shift();
      const job = jobs.get(id);
      if (job?.status === "queued") {
        await runJob(job);
        return;
      }
    }
  }

  async function create(req) {
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
      const job = {
        id,
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
        startedAt: null,
        completedAt: null,
        error: null,
        automaticRetryCounts: { moderation: 0, transient: 0 },
        logTail: [],
      };
      jobs.set(id, job);
      await saveJob(job);
      queue.push(id);
      void runNext();
      return publicJob(job);
    } catch (error) {
      await rm(root, { recursive: true, force: true });
      throw error;
    }
  }

  async function retry(id) {
    const job = jobs.get(id);
    if (!job) throw new HttpError(404, "Fighter job not found.");
    if (ACTIVE_STATUSES.has(job.status)) throw new HttpError(409, "That fighter is already being generated.");
    if (job.status === "complete") throw new HttpError(409, "That fighter is already complete.");
    job.status = "queued";
    job.stage = "queued";
    job.stageLabel = workerBusy ? "Waiting for the current fighter" : "Queued to resume";
    job.progress = 0;
    job.error = null;
    job.retryLabel = null;
    job.automaticRetryCounts = { moderation: 0, transient: 0 };
    job.completedAt = null;
    await saveJob(job);
    queue.push(id);
    void runNext();
    return publicJob(job);
  }

  return {
    async init() {
      await loadJobs();
      void runNext();
    },
    async create(req) {
      return create(req);
    },
    list() {
      return [...jobs.values()]
        .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
        .map(publicJob);
    },
    get(id) {
      const job = jobs.get(id);
      return job ? publicJob(job) : null;
    },
    async retry(id) {
      return retry(id);
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
