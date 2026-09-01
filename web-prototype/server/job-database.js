import { mkdir, readFile, readdir, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";

class LocalJobDatabase {
  constructor(root) {
    this.driver = "local";
    this.root = root;
  }

  async init() {
    await mkdir(this.root, { recursive: true });
  }

  async list() {
    const entries = await readdir(this.root, { withFileTypes: true });
    const jobs = [];
    for (const entry of entries) {
      if (!entry.isDirectory() || entry.name.startsWith(".")) continue;
      try {
        const job = JSON.parse(await readFile(path.join(this.root, entry.name, "job.json"), "utf8"));
        if (job.id === entry.name) jobs.push(job);
      } catch (error) {
        console.warn(`Skipping fighter job '${entry.name}': ${error.message}`);
      }
    }
    return jobs;
  }

  async get(id) {
    try {
      return JSON.parse(await readFile(path.join(this.root, id, "job.json"), "utf8"));
    } catch (error) {
      if (error.code === "ENOENT") return null;
      throw error;
    }
  }

  async insert(job) {
    const duplicate = (await this.list()).find((candidate) => candidate.slug === job.slug);
    if (duplicate) {
      const error = new Error(`A fighter with slug '${job.slug}' already exists.`);
      error.code = "DUPLICATE_SLUG";
      throw error;
    }
    await this.save(job);
  }

  async save(job) {
    const root = path.join(this.root, job.id);
    await mkdir(root, { recursive: true });
    const finalPath = path.join(root, "job.json");
    const temporaryPath = `${finalPath}.${randomUUID()}.tmp`;
    await writeFile(temporaryPath, `${JSON.stringify(job, null, 2)}\n`, { mode: 0o600 });
    await rename(temporaryPath, finalPath);
  }

  watch() {
    return null;
  }

  async claim(id, executionId, leaseSeconds) {
    const job = await this.get(id);
    if (!job || job.status === "complete" || job.status === "cancelled") {
      return { claimed: false, job };
    }
    const leaseExpires = Date.parse(job.lease?.expiresAt || "");
    if (job.lease?.executionId !== executionId && leaseExpires > Date.now()) {
      return { claimed: false, job };
    }
    job.lease = {
      executionId,
      expiresAt: new Date(Date.now() + leaseSeconds * 1000).toISOString(),
    };
    await this.save(job);
    return { claimed: true, job };
  }
}

class FirestoreJobDatabase {
  constructor({ collectionName }) {
    this.driver = "firestore";
    this.collectionName = collectionName;
    this.collection = null;
  }

  async init() {
    const { Firestore } = await import("@google-cloud/firestore");
    const firestore = new Firestore({
      projectId: process.env.GOOGLE_CLOUD_PROJECT || process.env.GCLOUD_PROJECT,
    });
    this.collection = firestore.collection(this.collectionName);
  }

  async list() {
    const snapshot = await this.collection.get();
    return snapshot.docs.map((document) => document.data());
  }

  async get(id) {
    const document = await this.collection.doc(id).get();
    return document.exists ? document.data() : null;
  }

  async insert(job) {
    const jobRef = this.collection.doc(job.id);
    const slugRef = this.collection.firestore.collection(`${this.collectionName}Slugs`).doc(job.slug);
    await this.collection.firestore.runTransaction(async (transaction) => {
      const slug = await transaction.get(slugRef);
      if (slug.exists) {
        const error = new Error(`A fighter with slug '${job.slug}' already exists.`);
        error.code = "DUPLICATE_SLUG";
        throw error;
      }
      transaction.create(slugRef, { jobId: job.id, createdAt: job.createdAt });
      transaction.create(jobRef, job);
    });
  }

  async save(job) {
    await this.collection.doc(job.id).set(job);
  }

  watch(listener) {
    return this.collection.onSnapshot((snapshot) => {
      for (const change of snapshot.docChanges()) {
        if (change.type !== "removed") listener(change.doc.data());
      }
    }, (error) => console.error("Firestore fighter job watch failed:", error));
  }


  async claim(id, executionId, leaseSeconds) {
    const reference = this.collection.doc(id);
    return this.collection.firestore.runTransaction(async (transaction) => {
      const document = await transaction.get(reference);
      if (!document.exists) return { claimed: false, job: null };
      const job = document.data();
      if (job.status === "complete" || job.status === "cancelled") {
        return { claimed: false, job };
      }
      const leaseExpires = Date.parse(job.lease?.expiresAt || "");
      if (job.lease?.executionId !== executionId && leaseExpires > Date.now()) {
        return { claimed: false, job };
      }
      job.lease = {
        executionId,
        expiresAt: new Date(Date.now() + leaseSeconds * 1000).toISOString(),
      };
      transaction.set(reference, job);
      return { claimed: true, job };
    });
  }
}

export function createJobDatabase({ jobsRoot }) {
  if ((process.env.JOB_DATABASE || "local") === "firestore") {
    return new FirestoreJobDatabase({
      collectionName: process.env.FIRESTORE_JOBS_COLLECTION || "fighterJobs",
    });
  }
  return new LocalJobDatabase(jobsRoot);
}
