// handoff-rooms.js — signalling rooms for the ROM handoff (laptop → phone).
//
// A room is a short-lived mailbox pair: the host (a browser that already holds
// a validated ROM) posts its WebRTC offer and ICE candidates, the guest posts
// its answer and candidates, and each side polls for the other's messages.
// Once the data channel is up the room is irrelevant; the ROM itself streams
// peer-to-peer and never passes through here. Messages are capped in size and
// count so the mailbox cannot be repurposed as a file relay.
//
// The store is in-memory. That is fine while the API runs as a single Cloud
// Run instance (infra/README.md caps it at one); scaling the API out means
// moving rooms into Firestore behind this same interface.

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
export const MAX_QUEUED_MESSAGES = 64;

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

export function createHandoffRooms({ now = Date.now, ttlMs = ROOM_TTL_MS, maxRooms = MAX_ROOMS } = {}) {
  const rooms = new Map();

  function sweep() {
    const time = now();
    for (const [code, room] of rooms) {
      if (room.expiresAt <= time || room.closed) rooms.delete(code);
    }
  }

  function lookup(code) {
    sweep();
    const normalized = normalizeHandoffCode(code);
    if (!isHandoffCode(normalized)) throw new HandoffError(400, "That is not a valid handoff code.");
    const room = rooms.get(normalized);
    if (!room) throw new HandoffError(404, "That code has expired or was never issued. Start again on the device that has the ROM.");
    return room;
  }

  function authorize(room, role, key) {
    if (!ROLES.has(role)) throw new HandoffError(400, "Unknown handoff role.");
    const expected = role === "host" ? room.hostKey : room.guestKey;
    if (!expected || key !== expected) throw new HandoffError(403, "That device is not part of this handoff.");
  }

  return {
    /** Number of live rooms (tests and health output). */
    get size() { sweep(); return rooms.size; },

    /** The host opens a room. `address` bounds how many one client can hold. */
    create({ address = "unknown" } = {}) {
      sweep();
      if (rooms.size >= maxRooms) throw new HandoffError(503, "Too many handoffs are in progress. Try again in a minute.");
      let held = 0;
      for (const room of rooms.values()) if (room.address === address) held += 1;
      if (held >= MAX_ROOMS_PER_ADDRESS) throw new HandoffError(429, "Too many handoffs from this connection. Wait for one to finish.");

      let code = generateHandoffCode();
      while (rooms.has(code)) code = generateHandoffCode();
      const room = {
        code,
        address,
        hostKey: randomKey(),
        guestKey: null,
        createdAt: now(),
        expiresAt: now() + ttlMs,
        closed: false,
        // Mailboxes are named by the reader: messages FOR the host, FOR the guest.
        toHost: [],
        toGuest: [],
      };
      rooms.set(code, room);
      return { code, hostKey: room.hostKey, expiresAt: room.expiresAt };
    },

    /** The guest claims the room. Only one guest may ever join. */
    join(code) {
      const room = lookup(code);
      if (room.guestKey) throw new HandoffError(409, "Another device already joined this handoff. Start a new one.");
      room.guestKey = randomKey();
      return { code: room.code, guestKey: room.guestKey, expiresAt: room.expiresAt };
    },

    /** Leave a message for the other side. */
    post(code, { role, key, message }) {
      const room = lookup(code);
      authorize(room, role, key);
      const encoded = JSON.stringify(message ?? null);
      if (encoded === "null") throw new HandoffError(400, "A message is required.");
      if (Buffer.byteLength(encoded) > HANDOFF_MAX_MESSAGE_BYTES) throw new HandoffError(413, "Handoff message is too large.");
      const queue = role === "host" ? room.toGuest : room.toHost;
      if (queue.length >= MAX_QUEUED_MESSAGES) throw new HandoffError(429, "Too many queued handoff messages.");
      queue.push(message);
      return { queued: queue.length };
    },

    /** Read messages addressed to `role`, after cursor `after` (0-based count already seen). */
    poll(code, { role, key, after = 0 }) {
      const room = lookup(code);
      authorize(room, role, key);
      const queue = role === "host" ? room.toHost : room.toGuest;
      const start = Math.max(0, Math.min(queue.length, Number(after) || 0));
      return {
        messages: queue.slice(start),
        cursor: queue.length,
        peerJoined: Boolean(room.guestKey),
        expiresAt: room.expiresAt,
      };
    },

    /** Either side tears the room down once the data channel is open (or on cancel). */
    close(code, { role, key }) {
      const room = lookup(code);
      authorize(room, role, key);
      room.closed = true;
      rooms.delete(room.code);
      return { closed: true };
    },
  };
}
