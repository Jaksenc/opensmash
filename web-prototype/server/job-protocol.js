export const JOB_PROTOCOL_VERSION = 1;

export const ACTIVE_JOB_STATUSES = new Set(["queued", "running", "retrying"]);
export const TERMINAL_JOB_STATUSES = new Set(["complete", "failed", "cancelled"]);

export function publicJob(job) {
  const result = {
    protocolVersion: JOB_PROTOCOL_VERSION,
    id: job.id,
    revision: job.revision || 0,
    name: job.name,
    slug: job.slug,
    emblem: job.emblem,
    status: job.status,
    stage: job.stage,
    stageLabel: job.stageLabel,
    progress: job.progress,
    attempt: job.attempt || 0,
    retry: job.retry || {
      automaticCounts: { moderation: 0, transient: 0 },
      nextAttemptAt: null,
      label: null,
    },
    createdAt: job.createdAt,
    updatedAt: job.updatedAt || job.createdAt,
    startedAt: job.startedAt || null,
    completedAt: job.completedAt || null,
    error: job.error || null,
    logTail: job.logTail || [],
    photoName: job.photoName,
  };

  if (job.status === "complete") {
    const artifacts = job.artifacts || {};
    result.artifacts = artifacts;
    result.character = {
      slug: job.slug,
      name: job.displayName || job.name,
      short: job.short || job.name,
      portrait: artifacts.portrait?.url || `/api/fighters/${job.id}/portrait?v=${encodeURIComponent(job.completedAt || "")}`,
      announcer: artifacts.announcer?.url || `/api/fighters/${job.id}/announcer?v=${encodeURIComponent(job.completedAt || "")}`,
      bundleUrl: artifacts.bundle?.url || null,
      uiUrl: artifacts.ui?.url || null,
      voiceUrl: artifacts.announcer?.url || null,
      manifestUrl: artifacts.manifest?.url || null,
      variants: Object.fromEntries(
        Object.entries(artifacts.variants || {}).map(([fighter, artifact]) => [fighter, artifact.url]),
      ),
      fkind: 0,
      bundle: `${job.slug}.osb`,
    };
    result.costUsd = job.costUsd ?? null;
  }
  return result;
}

export function jobSnapshot(job) {
  return {
    protocolVersion: JOB_PROTOCOL_VERSION,
    type: "job.snapshot",
    emittedAt: new Date().toISOString(),
    job: publicJob(job),
  };
}
