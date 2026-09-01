class LocalDispatcher {
  constructor() {
    this.driver = "local";
  }

  async init() {}

  async dispatch() {
    return { executionName: null };
  }
}

class CloudRunDispatcher {
  constructor({ projectId, location, jobName }) {
    if (!projectId || !location || !jobName) {
      throw new Error(
        "GOOGLE_CLOUD_PROJECT, CLOUD_RUN_REGION, and CLOUD_RUN_WORKER_JOB are required for cloud-run execution",
      );
    }
    this.driver = "cloud-run";
    this.projectId = projectId;
    this.location = location;
    this.jobName = jobName;
    this.client = null;
  }

  async init() {
    const { v2 } = await import("@google-cloud/run");
    this.client = new v2.JobsClient();
  }

  async dispatch(job) {
    const name = this.client.jobPath(this.projectId, this.location, this.jobName);
    const [operation] = await this.client.runJob({
      name,
      overrides: {
        containerOverrides: [{
          env: [
            { name: "JOB_ID", value: job.id },
            { name: "JOB_REVISION", value: String(job.revision || 0) },
          ],
        }],
      },
    });
    return { executionName: operation.name || null };
  }
}

export function createJobDispatcher() {
  const driver = process.env.FIGHTER_EXECUTION_MODE || "local";
  if (driver === "cloud-run") {
    return new CloudRunDispatcher({
      projectId: process.env.GOOGLE_CLOUD_PROJECT || process.env.GCLOUD_PROJECT,
      location: process.env.CLOUD_RUN_REGION,
      jobName: process.env.CLOUD_RUN_WORKER_JOB,
    });
  }
  if (driver !== "local") throw new Error(`Unsupported FIGHTER_EXECUTION_MODE '${driver}'`);
  return new LocalDispatcher();
}
