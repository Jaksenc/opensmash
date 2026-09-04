import assert from "node:assert/strict";
import test from "node:test";
import { CloudRunServiceDispatcher } from "./job-dispatcher.js";

function streamResponse(lines, { status = 200, hold = null } = {}) {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    async start(controller) {
      for (const line of lines) {
        controller.enqueue(encoder.encode(`${JSON.stringify(line)}\n`));
      }
      if (hold) await hold;
      controller.close();
    },
  });
  return new Response(body, { status, headers: { "content-type": "application/x-ndjson" } });
}

test("dispatch resolves with the worker's execution id once the job is accepted", async () => {
  const calls = [];
  let release;
  const hold = new Promise((resolve) => { release = resolve; });
  const dispatcher = new CloudRunServiceDispatcher({
    url: "https://worker.example/",
    idToken: async (audience) => `token-for-${audience}`,
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return streamResponse([{ accepted: true, executionId: "rev-abc-1" }, { heartbeat: "x" }], { hold });
    },
  });
  const result = await dispatcher.dispatch({ id: "job-1", revision: 3 });
  assert.deepEqual(result, { executionName: "rev-abc-1" });
  assert.equal(calls[0].url, "https://worker.example/run");
  assert.equal(calls[0].init.headers.Authorization, "Bearer token-for-https://worker.example");
  assert.deepEqual(JSON.parse(calls[0].init.body), { jobId: "job-1", revision: 3 });
  release();
});

test("dispatch fails when the worker refuses the job", async () => {
  const dispatcher = new CloudRunServiceDispatcher({
    url: "https://worker.example",
    fetchImpl: async () => new Response(JSON.stringify({ error: "busy" }), { status: 409 }),
  });
  await assert.rejects(dispatcher.dispatch({ id: "job-1" }), /HTTP 409/);
});

test("dispatch fails when the stream ends before acceptance", async () => {
  const dispatcher = new CloudRunServiceDispatcher({
    url: "https://worker.example",
    fetchImpl: async () => streamResponse([]),
  });
  await assert.rejects(dispatcher.dispatch({ id: "job-1" }), /before accepting/);
});

test("dispatch gives up when acceptance takes too long", async () => {
  const dispatcher = new CloudRunServiceDispatcher({
    url: "https://worker.example",
    acceptTimeoutMs: 20,
    fetchImpl: (url, { signal }) => new Promise((_, reject) => {
      signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
    }),
  });
  await assert.rejects(dispatcher.dispatch({ id: "job-1" }), /did not accept the job in time/);
});

test("the service dispatcher requires a worker URL", () => {
  assert.throws(() => new CloudRunServiceDispatcher({ url: "" }), /FIGHTER_WORKER_URL/);
});
