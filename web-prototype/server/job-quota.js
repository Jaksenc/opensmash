import { ACTIVE_JOB_STATUSES } from "./job-protocol.js";

export const DAY_MS = 24 * 60 * 60 * 1000;

export class QuotaError extends Error {
  constructor(status, message, reason) {
    super(message);
    this.code = "QUOTA_EXCEEDED";
    this.status = status;
    this.reason = reason;
  }
}

export function quotaLimits(env = process.env) {
  return {
    maxActivePerOwner: Number(env.MAX_ACTIVE_JOBS_PER_OWNER || 1),
    maxDailyPerOwner: Number(env.MAX_DAILY_JOBS_PER_OWNER || 3),
    maxGlobalActive: Number(env.MAX_GLOBAL_ACTIVE_JOBS || 20),
  };
}

// Daily usage counts every worker execution the owner has asked for in the
// last 24 hours: each created job plus each manual retry of one of their jobs.
export function quotaUsage(jobs, ownerId, { now = Date.now(), pending = null } = {}) {
  const since = now - DAY_MS;
  const usage = { activeForOwner: 0, dailyForOwner: 0, globalActive: 0 };
  for (const job of jobs) {
    const active = ACTIVE_JOB_STATUSES.has(job.status);
    if (active) usage.globalActive += 1;
    if (job.ownerId !== ownerId) continue;
    if (active) usage.activeForOwner += 1;
    if (Date.parse(job.createdAt) >= since) usage.dailyForOwner += 1;
    for (const at of job.retry?.manualRetriesAt || []) {
      if (Date.parse(at) >= since) usage.dailyForOwner += 1;
    }
  }
  if (pending) {
    const ownerPending = pending.owners.get(ownerId) || 0;
    usage.activeForOwner += ownerPending;
    usage.dailyForOwner += ownerPending;
    usage.globalActive += pending.global;
  }
  return usage;
}

export function assertQuota(usage, limits) {
  if (usage.activeForOwner >= limits.maxActivePerOwner) {
    throw new QuotaError(429, "Finish your current fighter before starting another.", "active");
  }
  if (usage.dailyForOwner >= limits.maxDailyPerOwner) {
    throw new QuotaError(429, "This account has reached its daily fighter limit.", "daily");
  }
  if (usage.globalActive >= limits.maxGlobalActive) {
    throw new QuotaError(503, "The fighter queue is full. Try again shortly.", "global");
  }
}
