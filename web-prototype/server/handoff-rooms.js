// handoff-rooms.js — signalling rooms for the ROM handoff (laptop → phone).
//
// A room is a short-lived mailbox pair: the host (a browser that already holds
// a validated ROM) posts its WebRTC offer and ICE candidates, the guest posts
// its answer and candidates, and each side polls for the other's messages.
// Once the data channel is up the room is irrelevant; the ROM itself streams
// peer-to-peer and never passes through here. Messages are capped in size and
// count so the mailbox cannot be repurposed as a file relay.
//
// Two stores share one async interface:
//   - MemoryHandoffRooms: single process, used for local development.
//   - FirestoreHandoffRooms: one document per room, so any API replica can
//     serve either side of a handoff. Selected in production (see
//     createHandoffRoomsFromEnv). Rooms carry an `expireAt` timestamp for a
//     Firestore TTL policy (infra/deploy.sh enables it) and are also skipped
//     once expired even before the TTL sweeper removes them.

import { randomBytes } from "node:crypto";
import {
  HANDOFF_MAX_MESSAGE_BYTES,
  generateHandoffCode,
  isHandoffCode,
  normalizeHandoffCode,
} from "../shared/rom-handoff.js";

export const ROOM_TTL_MS = 10 * 60 * 1000;
export const MAX_ROOMS = 2000;
export const MAX_ROOMS_PER_ADDRESS = 5;
export const MAX_QUEUED_MESSAGES = 256;

const ROLES = new Set(["host", "guest"]);

export class HandoffError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function randomKey() {
  return randomBytes(18).toString("base64url");
}

function requireCode(code) {
  const normalized = normalizeHandoffCode(code);
  if (!isHandoffCode(normalized)) throw new HandoffError(400, "That is not a valid handoff code.");
  return normalized;
}

function notFound() {
  return new HandoffError(404, "That code has expired or was never issued. Start again on the device that has the ROM.");
}

function authorize(room, role, key) {
  if (!ROLES.has(role)) throw new HandoffError(400, "Unknown handoff role.");
  const expected = role === "host" ? room.hostKey : room.guestKey;
  if (!expected || key !== expected) throw new HandoffError(403, "That device is not part of this handoff.");
}

function encodeMessage(message) {
  const encoded = JSON.stringify(message ?? null);
  if (encoded === "null") throw new HandoffError(400, "A message is required.");
  if (Buffer.byteLength(encoded) > HANDOFF_MAX_MESSAGE_BYTES) throw new HandoffError(413, "Handoff message is too large.");
  return message;
}

/** `post` accepts one `message` or a `messages` array (batched ICE candidates). */
function normalizeMessages({ message, messages }) {
  const list = Array.isArray(messages) ? messages : [message];
  if (!list.length) throw new HandoffError(400, "A message is required.");
  if (list.length > 64) throw new HandoffError(413, "Too many messages in one post.");
  return list.map(encodeMessage);
}

function queueFor(room, role, { reading }) {
  // Mailboxes are named by the reader: messages FOR the host, FOR the guest.
  const readerIsHost = reading ? role === "host" : role === "guest";
  return readerIsHost ? room.toHost : room.toGuest;
}

function pollView(room, role, after) {
  const queue = queueFor(room, role, { reading: true });
  const start = Math.max(0, Math.min(queue.length, Number(after) || 0));
  return {
    messages: queue.slice(start),
    cursor: queue.length,
    peerJoined: Boolean(room.guestKey),
    expiresAt: room.expiresAt,
  };
}

function newRoom(code, address, now, ttlMs) {
  return {
    code,
    address,
    hostKey: randomKey(),
    guestKey: null,
    createdAt: now,
    expiresAt: now + ttlMs,
    toHost: [],
    toGuest: [],
  };
}

// ---------------------------------------------------------------------------

export class MemoryHandoffRooms {
  constructor({ now = Date.now, ttlMs = ROOM_TTL_MS, maxRooms = MAX_ROOMS } = {}) {
    this.driver = "memory";
    this.now = now;
    this.ttlMs = ttlMs;
    this.maxRooms = maxRooms;
    this.rooms = new Map();
  }

  sweep() {
    const time = this.now();
    for (const [code, room] of this.rooms) if (room.expiresAt <= time) this.rooms.delete(code);
  }

  /** Number of live rooms (tests and health output). */
  get size() { this.sweep(); return this.rooms.size; }

  lookup(code) {
    this.sweep();
    const room = this.rooms.get(requireCode(code));
    if (!room) throw notFound();
    return room;
  }

  /** The host opens a room. `address` bounds how many one client can hold. */
  async create({ address = "unknown" } = {}) {
    this.sweep();
    if (this.rooms.size >= this.maxRooms) throw new HandoffError(503, "Too many handoffs are in progress. Try again in a minute.");
    let held = 0;
    for (const room of this.rooms.values()) if (room.address === address) held += 1;
    if (held >= MAX_ROOMS_PER_ADDRESS) throw new HandoffError(429, "Too many handoffs from this connection. Wait for one to finish.");

    let code = generateHandoffCode();
    while (this.rooms.has(code)) code = generateHandoffCode();
    const room = newRoom(code, address, this.now(), this.ttlMs);
    this.rooms.set(code, room);
    return { code, hostKey: room.hostKey, expiresAt: room.expiresAt };
  }

  /** The guest claims the room. Only one guest may ever join. */
  async join(code) {
    const room = this.lookup(code);
    if (room.guestKey) throw new HandoffError(409, "Another device already joined this handoff. Start a new one.");
    room.guestKey = randomKey();
    return { code: room.code, guestKey: room.guestKey, expiresAt: room.expiresAt };
  }

  /** Leave a message for the other side. */
  async post(code, { role, key, message, messages }) {
    const room = this.lookup(code);
    authorize(room, role, key);
    const incoming = normalizeMessages({ message, messages });
    const queue = queueFor(room, role, { reading: false });
    if (queue.length + incoming.length > MAX_QUEUED_MESSAGES) throw new HandoffError(429, "Too many queued handoff messages.");
    queue.push(...incoming);
    return { queued: queue.length };
  }

  /** Read messages addressed to `role`, after cursor `after` (count already seen). */
  async poll(code, { role, key, after = 0 }) {
    const room = this.lookup(code);
    authorize(room, role, key);
    return pollView(room, role, after);
  }

  /** Either side tears the room down once the data channel is open (or on cancel). */
  async close(code, { role, key }) {
    const room = this.lookup(code);
    authorize(room, role, key);
    this.rooms.delete(room.code);
    return { closed: true };
  }
}

// ---------------------------------------------------------------------------

/**
 * Firestore-backed rooms. `firestore` is a @google-cloud/firestore instance
 * (or anything with the same collection/doc/runTransaction surface — tests
 * pass a fake). Every mutation runs in a transaction so concurrent replicas
 * never lose a message or double-admit a guest.
 */
export class FirestoreHandoffRooms {
  constructor({ firestore, collectionName = "handoffRooms", now = Date.now, ttlMs = ROOM_TTL_MS, maxRooms = MAX_ROOMS }) {
    this.driver = "firestore";
    this.firestore = firestore;
    this.collection = firestore.collection(collectionName);
    this.now = now;
    this.ttlMs = ttlMs;
    this.maxRooms = maxRooms;
  }

  liveRoom(snapshot) {
    if (!snapshot.exists) return null;
    const room = snapshot.data();
    return room.expiresAt > this.now() ? room : null;
  }

  async create({ address = "unknown" } = {}) {
    // Per-address cap: equality-only query so no composite index is needed;
    // expiry is filtered in code.
    const held = await this.collection.where("address", "==", address).get();
    const live = held.docs.filter((doc) => this.liveRoom(doc)).length;
    if (live >= MAX_ROOMS_PER_ADDRESS) throw new HandoffError(429, "Too many handoffs from this connection. Wait for one to finish.");

    for (let attempt = 0; attempt < 5; attempt += 1) {
      const code = generateHandoffCode();
      const reference = this.collection.doc(code);
      const created = await this.firestore.runTransaction(async (transaction) => {
        const existing = await transaction.get(reference);
        if (this.liveRoom(existing)) return null;
        const room = newRoom(code, address, this.now(), this.ttlMs);
        transaction.set(reference, { ...room, expireAt: new Date(room.expiresAt) });
        return room;
      });
      if (created) return { code, hostKey: created.hostKey, expiresAt: created.expiresAt };
    }
    throw new HandoffError(503, "Too many handoffs are in progress. Try again in a minute.");
  }

  async join(code) {
    const reference = this.collection.doc(requireCode(code));
    return this.firestore.runTransaction(async (transaction) => {
      const room = this.liveRoom(await transaction.get(reference));
      if (!room) throw notFound();
      if (room.guestKey) throw new HandoffError(409, "Another device already joined this handoff. Start a new one.");
      const guestKey = randomKey();
      transaction.update(reference, { guestKey });
      return { code: room.code, guestKey, expiresAt: room.expiresAt };
    });
  }

  async post(code, { role, key, message, messages }) {
    const reference = this.collection.doc(requireCode(code));
    const incoming = normalizeMessages({ message, messages });
    return this.firestore.runTransaction(async (transaction) => {
      const room = this.liveRoom(await transaction.get(reference));
      if (!room) throw notFound();
      authorize(room, role, key);
      const field = role === "host" ? "toGuest" : "toHost";
      const queue = room[field];
      if (queue.length + incoming.length > MAX_QUEUED_MESSAGES) throw new HandoffError(429, "Too many queued handoff messages.");
      transaction.update(reference, { [field]: [...queue, ...incoming] });
      return { queued: queue.length + incoming.length };
    });
  }

  async poll(code, { role, key, after = 0 }) {
    const room = this.liveRoom(await this.collection.doc(requireCode(code)).get());
    if (!room) throw notFound();
    authorize(room, role, key);
    return pollView(room, role, after);
  }

  async close(code, { role, key }) {
    const reference = this.collection.doc(requireCode(code));
    return this.firestore.runTransaction(async (transaction) => {
      const room = this.liveRoom(await transaction.get(reference));
      if (!room) throw notFound();
      authorize(room, role, key);
      transaction.delete(reference);
      return { closed: true };
    });
  }
}

// ---------------------------------------------------------------------------

/** Back-compat helper used by tests: an in-memory store. */
export function createHandoffRooms(options) {
  return new MemoryHandoffRooms(options);
}

/**
 * Pick the store from the environment. Firestore whenever the job database
 * is on Firestore (the production deploy), unless HANDOFF_ROOMS overrides it,
 * so a scaled-out API needs no extra configuration.
 */
export async function createHandoffRoomsFromEnv(env = process.env) {
  const driver = env.HANDOFF_ROOMS || env.JOB_DATABASE || "local";
  if (driver !== "firestore") return new MemoryHandoffRooms();
  const { Firestore } = await import("@google-cloud/firestore");
  const firestore = new Firestore({ projectId: env.GOOGLE_CLOUD_PROJECT || env.GCLOUD_PROJECT });
  return new FirestoreHandoffRooms({
    firestore,
    collectionName: env.FIRESTORE_HANDOFF_COLLECTION || "handoffRooms",
  });
}
