export const JOB_PROTOCOL_VERSION = 1;

export const ACTIVE_JOB_STATUSES = new Set(["queued", "running", "retrying"]);
export const TERMINAL_JOB_STATUSES = new Set(["complete", "failed", "cancelled"]);

export function publicJob(job) {
  const visibility = job.visibility || "public";
  const assetRoot = `/api/fighters/${encodeURIComponent(job.id)}/assets`;
  const result = {
    protocolVersion: JOB_PROTOCOL_VERSION,
    id: job.id,
    revision: job.revision || 0,
    name: job.name,
    slug: job.slug,
    emblem: job.emblem,
    visibility,
    uploader: job.uploader?.displayName ? { displayName: job.uploader.displayName } : null,
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
      portrait: artifacts.portrait?.url || `${assetRoot}/portrait?v=${encodeURIComponent(job.completedAt || "")}`,
      announcer: artifacts.announcer?.url || `${assetRoot}/announcer?v=${encodeURIComponent(job.completedAt || "")}`,
      bundleUrl: artifacts.bundle?.url || `${assetRoot}/bundle`,
      uiUrl: artifacts.ui?.url || `${assetRoot}/ui`,
      voiceUrl: artifacts.announcer?.url || `${assetRoot}/announcer`,
      manifestUrl: artifacts.manifest?.url || `${assetRoot}/manifest`,
      variants: Object.fromEntries(
        Object.entries(artifacts.variants || {}).map(([fighter, artifact]) => [
          fighter,
          artifact.url || `${assetRoot}/variants/${encodeURIComponent(fighter)}`,
        ]),
      ),
      visibility,
      uploader: result.uploader,
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
