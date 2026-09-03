import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { decodeDisplayName, isAuthHandlerPath, proxyAuthHandler, publicUser } from "./auth.js";

test("Apple display names are form-decoded, others untouched", () => {
  assert.equal(decodeDisplayName("William+J Flynn+III", "apple.com"), "William J Flynn III");
  assert.equal(decodeDisplayName("Ana%C3%AFs+Nin", "apple.com"), "Anaïs Nin");
  assert.equal(decodeDisplayName("A+B", "google.com"), "A+B");
  assert.equal(decodeDisplayName("", "apple.com"), null);
  assert.equal(publicUser({ sub: "u1", name: "Tom+Jones", firebase: { sign_in_provider: "apple.com" } }).displayName, "Tom Jones");
});

test("auth handler paths are recognised", () => {
  assert.equal(isAuthHandlerPath("/__/auth/handler"), true);
  assert.equal(isAuthHandlerPath("/__/auth/iframe.js"), true);
  assert.equal(isAuthHandlerPath("/api/auth/config"), false);
});

async function roundTrip(fetchImpl, { method = "GET", path = "/__/auth/handler?apiKey=k", body } = {}) {
  const server = http.createServer((req, res) => proxyAuthHandler(req, res, { upstreamOrigin: "https://proj.firebaseapp.com", fetchImpl }));
  await new Promise((resolve) => server.listen(0, resolve));
  const { port } = server.address();
  try {
    const response = await fetch(`http://127.0.0.1:${port}${path}`, { method, body, headers: body ? { "content-type": "application/x-www-form-urlencoded" } : {} });
    return { status: response.status, headers: response.headers, text: await response.text() };
  } finally {
    server.close();
  }
}

test("proxy forwards path, query, method and body; strips cookies", async () => {
  const seen = [];
  const fetchImpl = async (url, init) => {
    seen.push({ url: String(url), method: init.method, contentType: init.headers["content-type"], body: init.body ? await new Response(init.body).text() : null });
    return new Response("<html>handler</html>", {
      status: 200,
      headers: { "content-type": "text/html", "set-cookie": "leak=1", "cache-control": "no-store" },
    });
  };
  const get = await roundTrip(fetchImpl);
  assert.equal(get.status, 200);
  assert.equal(get.text, "<html>handler</html>");
  assert.equal(get.headers.get("set-cookie"), null);
  assert.equal(get.headers.get("cache-control"), "no-store");
  assert.equal(seen[0].url, "https://proj.firebaseapp.com/__/auth/handler?apiKey=k");

  const post = await roundTrip(fetchImpl, { method: "POST", body: "code=abc&state=xyz" });
  assert.equal(post.status, 200);
  assert.equal(seen[1].method, "POST");
  assert.equal(seen[1].body, "code=abc&state=xyz");
  assert.equal(seen[1].contentType, "application/x-www-form-urlencoded");
});

test("proxy reports an unreachable upstream as 502", async () => {
  const result = await roundTrip(async () => { throw new Error("boom"); });
  assert.equal(result.status, 502);
  assert.match(result.text, /boom/);
});
