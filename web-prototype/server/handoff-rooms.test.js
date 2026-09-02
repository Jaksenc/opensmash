import assert from "node:assert/strict";
import test from "node:test";
import { HandoffError, MAX_ROOMS_PER_ADDRESS, MAX_QUEUED_MESSAGES, createHandoffRooms } from "./handoff-rooms.js";
import { isHandoffCode } from "../shared/rom-handoff.js";

function clock(start = 1_000_000) {
  let time = start;
  const now = () => time;
  now.advance = (ms) => { time += ms; };
  return now;
}

test("host creates a room, guest joins once, messages flow both ways", () => {
  const rooms = createHandoffRooms({ now: clock() });
  const { code, hostKey } = rooms.create({ address: "a" });
  assert.ok(isHandoffCode(code));

  const { guestKey } = rooms.join(code.toLowerCase());
  assert.throws(() => rooms.join(code), (error) => error instanceof HandoffError && error.status === 409);

  rooms.post(code, { role: "host", key: hostKey, message: { type: "offer", sdp: "v=0" } });
  const guestView = rooms.poll(code, { role: "guest", key: guestKey, after: 0 });
  assert.deepEqual(guestView.messages, [{ type: "offer", sdp: "v=0" }]);
  assert.equal(guestView.cursor, 1);
  assert.equal(guestView.peerJoined, true);

  rooms.post(code, { role: "guest", key: guestKey, message: { type: "answer", sdp: "v=0" } });
  rooms.post(code, { role: "guest", key: guestKey, message: { type: "candidate", candidate: {} } });
  const hostView = rooms.poll(code, { role: "host", key: hostKey, after: 1 });
  assert.deepEqual(hostView.messages, [{ type: "candidate", candidate: {} }]);
  assert.equal(hostView.cursor, 2);

  // Reading your own outbox is impossible: the host's poll never shows the offer.
  assert.equal(rooms.poll(code, { role: "host", key: hostKey }).messages.some((m) => m.type === "offer"), false);
});

test("the host sees peerJoined flip when the guest arrives", () => {
  const rooms = createHandoffRooms({ now: clock() });
  const { code, hostKey } = rooms.create();
  assert.equal(rooms.poll(code, { role: "host", key: hostKey }).peerJoined, false);
  rooms.join(code);
  assert.equal(rooms.poll(code, { role: "host", key: hostKey }).peerJoined, true);
});

test("keys are enforced per role", () => {
  const rooms = createHandoffRooms({ now: clock() });
  const { code, hostKey } = rooms.create();
  const { guestKey } = rooms.join(code);
  const forbidden = (fn) => assert.throws(fn, (error) => error instanceof HandoffError && error.status === 403);
  forbidden(() => rooms.post(code, { role: "host", key: guestKey, message: { type: "x" } }));
  forbidden(() => rooms.poll(code, { role: "guest", key: hostKey }));
  forbidden(() => rooms.close(code, { role: "guest", key: "nope" }));
  assert.throws(() => rooms.poll(code, { role: "admin", key: hostKey }), /Unknown handoff role/);
});

test("rooms expire and unknown or malformed codes are rejected", () => {
  const now = clock();
  const rooms = createHandoffRooms({ now, ttlMs: 1000 });
  const { code, hostKey } = rooms.create();
  now.advance(999);
  assert.equal(rooms.poll(code, { role: "host", key: hostKey }).cursor, 0);
  now.advance(1);
  assert.throws(() => rooms.poll(code, { role: "host", key: hostKey }), (error) => error.status === 404);
  assert.equal(rooms.size, 0);
  assert.throws(() => rooms.join("bad"), (error) => error.status === 400);
  assert.throws(() => rooms.join("ABCDEF"), (error) => error.status === 404);
});

test("close removes the room for both sides", () => {
  const rooms = createHandoffRooms({ now: clock() });
  const { code, hostKey } = rooms.create();
  const { guestKey } = rooms.join(code);
  rooms.close(code, { role: "guest", key: guestKey });
  assert.throws(() => rooms.poll(code, { role: "host", key: hostKey }), (error) => error.status === 404);
});

test("message size, queue depth, and per-address room limits hold", () => {
  const rooms = createHandoffRooms({ now: clock() });
  const { code, hostKey } = rooms.create({ address: "x" });
  assert.throws(
    () => rooms.post(code, { role: "host", key: hostKey, message: { blob: "z".repeat(20 * 1024) } }),
    (error) => error.status === 413,
  );
  assert.throws(() => rooms.post(code, { role: "host", key: hostKey, message: null }), (error) => error.status === 400);
  for (let index = 0; index < MAX_QUEUED_MESSAGES; index += 1) {
    rooms.post(code, { role: "host", key: hostKey, message: { index } });
  }
  assert.throws(() => rooms.post(code, { role: "host", key: hostKey, message: { index: -1 } }), (error) => error.status === 429);

  for (let index = 1; index < MAX_ROOMS_PER_ADDRESS; index += 1) rooms.create({ address: "x" });
  assert.throws(() => rooms.create({ address: "x" }), (error) => error.status === 429);
  assert.ok(rooms.create({ address: "y" }).code);
});

test("the global room cap returns 503", () => {
  const rooms = createHandoffRooms({ now: clock(), maxRooms: 2 });
  rooms.create({ address: "a" });
  rooms.create({ address: "b" });
  assert.throws(() => rooms.create({ address: "c" }), (error) => error.status === 503);
});
