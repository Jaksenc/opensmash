import assert from "node:assert/strict";
import test from "node:test";
import {
  FirestoreHandoffRooms,
  HandoffError,
  MAX_ROOMS_PER_ADDRESS,
  MAX_QUEUED_MESSAGES,
  MemoryHandoffRooms,
  createHandoffRoomsFromEnv,
} from "./handoff-rooms.js";
import { isHandoffCode } from "../shared/rom-handoff.js";

function clock(start = 1_000_000) {
  let time = start;
  const now = () => time;
  now.advance = (ms) => { time += ms; };
  return now;
}

// A tiny stand-in for @google-cloud/firestore covering exactly the surface the
// adapter uses: collection().doc().get/set/update/delete, where().get(), and
// runTransaction with get/set/update/delete. Writes inside a transaction are
// applied at commit.
function fakeFirestore() {
  const store = new Map(); // "collection/id" → data
  const snapshot = (key) => ({ exists: store.has(key), data: () => structuredClone(store.get(key)) });
  const docRef = (collection, id) => {
    const key = `${collection}/${id}`;
    return {
      key,
      async get() { return snapshot(key); },
      async set(data) { store.set(key, structuredClone(data)); },
    };
  };
  const collection = (name) => ({
    doc: (id) => docRef(name, id),
    where(field, op, value) {
      assert.equal(op, "==");
      return {
        async get() {
          const docs = [];
          for (const [key, data] of store) {
            if (key.startsWith(`${name}/`) && data[field] === value) docs.push({ exists: true, data: () => structuredClone(data) });
          }
          return { docs };
        },
      };
    },
  });
  return {
    store,
    collection,
    async runTransaction(work) {
      const writes = [];
      const transaction = {
        get: async (ref) => snapshot(ref.key),
        set: (ref, data) => writes.push(() => store.set(ref.key, structuredClone(data))),
        update: (ref, patch) => writes.push(() => store.set(ref.key, { ...store.get(ref.key), ...structuredClone(patch) })),
        delete: (ref) => writes.push(() => store.delete(ref.key)),
      };
      const result = await work(transaction);
      for (const write of writes) write();
      return result;
    },
  };
}

const drivers = [
  ["memory", (options) => new MemoryHandoffRooms(options)],
  ["firestore", (options) => new FirestoreHandoffRooms({ firestore: fakeFirestore(), ...options })],
];

for (const [name, make] of drivers) {
  test(`[${name}] host creates a room, guest joins once, messages flow both ways`, async () => {
    const rooms = make({ now: clock() });
    const { code, hostKey } = await rooms.create({ address: "a" });
    assert.ok(isHandoffCode(code));

    const { guestKey } = await rooms.join(code.toLowerCase());
    await assert.rejects(rooms.join(code), (error) => error instanceof HandoffError && error.status === 409);

    await rooms.post(code, { role: "host", key: hostKey, message: { type: "offer", sdp: "v=0" } });
    const guestView = await rooms.poll(code, { role: "guest", key: guestKey, after: 0 });
    assert.deepEqual(guestView.messages, [{ type: "offer", sdp: "v=0" }]);
    assert.equal(guestView.cursor, 1);
    assert.equal(guestView.peerJoined, true);

    await rooms.post(code, { role: "guest", key: guestKey, message: { type: "answer", sdp: "v=0" } });
    await rooms.post(code, { role: "guest", key: guestKey, message: { type: "candidate", candidate: {} } });
    const hostView = await rooms.poll(code, { role: "host", key: hostKey, after: 1 });
    assert.deepEqual(hostView.messages, [{ type: "candidate", candidate: {} }]);
    assert.equal(hostView.cursor, 2);

    // Reading your own outbox is impossible: the host's poll never shows the offer.
    const own = await rooms.poll(code, { role: "host", key: hostKey });
    assert.equal(own.messages.some((m) => m.type === "offer"), false);
  });

  test(`[${name}] the host sees peerJoined flip when the guest arrives`, async () => {
    const rooms = make({ now: clock() });
    const { code, hostKey } = await rooms.create();
    assert.equal((await rooms.poll(code, { role: "host", key: hostKey })).peerJoined, false);
    await rooms.join(code);
    assert.equal((await rooms.poll(code, { role: "host", key: hostKey })).peerJoined, true);
  });

  test(`[${name}] keys are enforced per role`, async () => {
    const rooms = make({ now: clock() });
    const { code, hostKey } = await rooms.create();
    const { guestKey } = await rooms.join(code);
    const forbidden = (promise) => assert.rejects(promise, (error) => error instanceof HandoffError && error.status === 403);
    await forbidden(rooms.post(code, { role: "host", key: guestKey, message: { type: "x" } }));
    await forbidden(rooms.poll(code, { role: "guest", key: hostKey }));
    await forbidden(rooms.close(code, { role: "guest", key: "nope" }));
    await assert.rejects(rooms.poll(code, { role: "admin", key: hostKey }), /Unknown handoff role/);
  });

  test(`[${name}] rooms expire and unknown or malformed codes are rejected`, async () => {
    const now = clock();
    const rooms = make({ now, ttlMs: 1000 });
    const { code, hostKey } = await rooms.create();
    now.advance(999);
    assert.equal((await rooms.poll(code, { role: "host", key: hostKey })).cursor, 0);
    now.advance(1);
    await assert.rejects(rooms.poll(code, { role: "host", key: hostKey }), (error) => error.status === 404);
    await assert.rejects(rooms.join("bad"), (error) => error.status === 400);
    await assert.rejects(rooms.join("ABCDEF"), (error) => error.status === 404);
  });

  test(`[${name}] close removes the room for both sides`, async () => {
    const rooms = make({ now: clock() });
    const { code, hostKey } = await rooms.create();
    const { guestKey } = await rooms.join(code);
    await rooms.close(code, { role: "guest", key: guestKey });
    await assert.rejects(rooms.poll(code, { role: "host", key: hostKey }), (error) => error.status === 404);
  });

  test(`[${name}] message size, queue depth, and per-address room limits hold`, async () => {
    const rooms = make({ now: clock() });
    const { code, hostKey } = await rooms.create({ address: "x" });
    await assert.rejects(
      rooms.post(code, { role: "host", key: hostKey, message: { blob: "z".repeat(20 * 1024) } }),
      (error) => error.status === 413,
    );
    await assert.rejects(rooms.post(code, { role: "host", key: hostKey, message: null }), (error) => error.status === 400);
    for (let index = 0; index < MAX_QUEUED_MESSAGES; index += 1) {
      await rooms.post(code, { role: "host", key: hostKey, message: { index } });
    }
    await assert.rejects(rooms.post(code, { role: "host", key: hostKey, message: { index: -1 } }), (error) => error.status === 429);

    for (let index = 1; index < MAX_ROOMS_PER_ADDRESS; index += 1) await rooms.create({ address: "x" });
    await assert.rejects(rooms.create({ address: "x" }), (error) => error.status === 429);
    assert.ok((await rooms.create({ address: "y" })).code);
  });
}

test("[memory] the global room cap returns 503", async () => {
  const rooms = new MemoryHandoffRooms({ now: clock(), maxRooms: 2 });
  await rooms.create({ address: "a" });
  await rooms.create({ address: "b" });
  await assert.rejects(rooms.create({ address: "c" }), (error) => error.status === 503);
});

test("[firestore] expired rooms do not block reuse of their code or count toward the address cap", async () => {
  const now = clock();
  const firestore = fakeFirestore();
  const rooms = new FirestoreHandoffRooms({ firestore, now, ttlMs: 1000 });
  for (let index = 0; index < MAX_ROOMS_PER_ADDRESS; index += 1) await rooms.create({ address: "x" });
  await assert.rejects(rooms.create({ address: "x" }), (error) => error.status === 429);
  now.advance(1001);
  const { code } = await rooms.create({ address: "x" });
  assert.ok(isHandoffCode(code));
  // Documents carry a Date for the Firestore TTL policy.
  assert.ok(firestore.store.get(`handoffRooms/${code}`).expireAt instanceof Date);
});

test("createHandoffRoomsFromEnv picks memory unless Firestore is configured", async () => {
  assert.equal((await createHandoffRoomsFromEnv({})).driver, "memory");
  assert.equal((await createHandoffRoomsFromEnv({ JOB_DATABASE: "local" })).driver, "memory");
  assert.equal((await createHandoffRoomsFromEnv({ JOB_DATABASE: "firestore", HANDOFF_ROOMS: "memory" })).driver, "memory");
});
