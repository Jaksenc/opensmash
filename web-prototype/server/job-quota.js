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
    maxDailyPerOwner: Number(env.MAX_DAILY_JOBS_PER_OWNER || 10),
    // Fighters generating at once across every account: each is one Cloud
    // Run worker execution, so this is a concurrency ceiling, not a budget.
    // Cloud Run allows far more parallel executions than this; it exists so
    // a runaway burst is visible before it becomes a bill.
    maxGlobalActive: Number(env.MAX_GLOBAL_ACTIVE_JOBS || 200),
    // Fighters started in any rolling 24 h across every account. This is the
    // spend bound: no number of fresh accounts can exceed it.
    maxGlobalDaily: Number(env.MAX_GLOBAL_DAILY_JOBS || 5000),
  };
}

// Daily usage counts every worker execution the owner has asked for in the
// last 24 hours: each created job plus each manual retry of one of their jobs.
export function quotaUsage(jobs, ownerId, { now = Date.now(), pending = null } = {}) {
  const since = now - DAY_MS;
  const usage = { activeForOwner: 0, dailyForOwner: 0, globalActive: 0, globalDaily: 0 };
  for (const job of jobs) {
    const active = ACTIVE_JOB_STATUSES.has(job.status);
    if (active) usage.globalActive += 1;
    let runs = Date.parse(job.createdAt) >= since ? 1 : 0;
    for (const at of job.retry?.manualRetriesAt || []) {
      if (Date.parse(at) >= since) runs += 1;
    }
    usage.globalDaily += runs;
    if (job.ownerId !== ownerId) continue;
    if (active) usage.activeForOwner += 1;
    usage.dailyForOwner += runs;
  }
  if (pending) {
    const ownerPending = pending.owners.get(ownerId) || 0;
    usage.activeForOwner += ownerPending;
    usage.dailyForOwner += ownerPending;
    usage.globalActive += pending.global;
    usage.globalDaily += pending.global;
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
  if (limits.maxGlobalDaily > 0 && usage.globalDaily >= limits.maxGlobalDaily) {
    throw new QuotaError(
      429,
      "Fighter creation has reached today's site-wide limit. Try again tomorrow.",
      "globalDaily",
    );
  }
}
