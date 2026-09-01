import { copyFile, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

function encodeObjectKey(key) {
  return key.split("/").map(encodeURIComponent).join("/");
}

function assertObjectKey(key) {
  if (!/^[a-zA-Z0-9][a-zA-Z0-9._/-]*$/.test(key) || key.includes("..")) {
    throw new Error(`Invalid object key: ${key}`);
  }
  return key;
}

class LocalObjectStore {
  constructor(root) {
    this.driver = "local";
    this.root = root;
  }

  async init() {
    await mkdir(this.root, { recursive: true });
  }

  async putFile(key, sourcePath, { contentType, public: isPublic = false } = {}) {
    assertObjectKey(key);
    const destination = path.join(this.root, key);
    await mkdir(path.dirname(destination), { recursive: true });
    await copyFile(sourcePath, destination);
    return {
      key,
      contentType: contentType || "application/octet-stream",
      url: isPublic ? `/objects/${encodeObjectKey(key)}` : null,
    };
  }

  async getFile(key, destination) {
    assertObjectKey(key);
    await mkdir(path.dirname(destination), { recursive: true });
    await copyFile(path.join(this.root, key), destination);
  }

  async putJson(key, value, { public: isPublic = false, immutable = true } = {}) {
    assertObjectKey(key);
    const destination = path.join(this.root, key);
    await mkdir(path.dirname(destination), { recursive: true });
    await writeFile(destination, `${JSON.stringify(value, null, 2)}\n`);
    return {
      key,
      contentType: "application/json",
      url: isPublic ? `/objects/${encodeObjectKey(key)}` : null,
      immutable,
    };
  }

  localPath(key) {
    assertObjectKey(key);
    return path.join(this.root, key);
  }
}

class GcsObjectStore {
  constructor({ privateBucketName, publicBucketName, assetBaseUrl }) {
    if (!privateBucketName || !publicBucketName) {
      throw new Error(
        "GCS_PRIVATE_BUCKET and GCS_PUBLIC_BUCKET are required when OBJECT_STORE=gcs",
      );
    }
    if (process.env.NODE_ENV === "production" && privateBucketName === publicBucketName) {
      throw new Error("Production source photos and public fighter assets must use separate buckets");
    }
    this.driver = "gcs";
    this.privateBucketName = privateBucketName;
    this.publicBucketName = publicBucketName;
    this.assetBaseUrl = assetBaseUrl?.replace(/\/+$/, "") || `https://storage.googleapis.com/${publicBucketName}`;
    this.privateBucket = null;
    this.publicBucket = null;
  }

  async init() {
    const { Storage } = await import("@google-cloud/storage");
    const storage = new Storage();
    this.privateBucket = storage.bucket(this.privateBucketName);
    this.publicBucket = storage.bucket(this.publicBucketName);
    await Promise.all([this.privateBucket.getMetadata(), this.publicBucket.getMetadata()]);
  }

  async putFile(key, sourcePath, { contentType, public: isPublic = false } = {}) {
    assertObjectKey(key);
    const bucket = isPublic ? this.publicBucket : this.privateBucket;
    await bucket.upload(sourcePath, {
      destination: key,
      resumable: false,
      metadata: {
        contentType: contentType || "application/octet-stream",
        cacheControl: isPublic
          ? "public, max-age=31536000, immutable"
          : "private, no-store",
      },
    });
    return {
      key,
      contentType: contentType || "application/octet-stream",
      url: isPublic ? `${this.assetBaseUrl}/${encodeObjectKey(key)}` : null,
    };
  }

  async getFile(key, destination) {
    assertObjectKey(key);
    await mkdir(path.dirname(destination), { recursive: true });
    await this.privateBucket.file(key).download({ destination });
  }

  async putJson(key, value, { public: isPublic = false, immutable = true } = {}) {
    assertObjectKey(key);
    const bucket = isPublic ? this.publicBucket : this.privateBucket;
    await bucket.file(key).save(`${JSON.stringify(value, null, 2)}\n`, {
      resumable: false,
      contentType: "application/json",
      metadata: {
        cacheControl: isPublic
          ? immutable ? "public, max-age=31536000, immutable" : "public, max-age=60"
          : "private, no-store",
      },
    });
    return {
      key,
      contentType: "application/json",
      url: isPublic ? `${this.assetBaseUrl}/${encodeObjectKey(key)}` : null,
      immutable,
    };
  }

  localPath() {
    return null;
  }
}

export function createObjectStore({ appRoot }) {
  if ((process.env.OBJECT_STORE || "local") === "gcs") {
    return new GcsObjectStore({
      privateBucketName: process.env.GCS_PRIVATE_BUCKET || process.env.GCS_BUCKET,
      publicBucketName: process.env.GCS_PUBLIC_BUCKET || process.env.GCS_BUCKET,
      assetBaseUrl: process.env.ASSET_BASE_URL,
    });
  }
  return new LocalObjectStore(
    path.resolve(process.env.OBJECT_STORE_ROOT || path.join(appRoot, "data", "objects")),
  );
}
