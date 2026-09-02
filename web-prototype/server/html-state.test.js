import assert from "node:assert/strict";
import test from "node:test";
import { withInitialState } from "./html-state.js";

const SHELL = "<html><head><title>OpenSmash</title></head><body></body></html>";

test("withInitialState injects the public roster before the closing head", () => {
  const html = withInitialState(SHELL, {
    characters: [{ slug: "ada", name: "Ada" }],
  });
  assert.match(
    html,
    /<script>window\.__OPENSMASH_INITIAL_STATE__=\{"characters":\[\{"slug":"ada","name":"Ada"\}\]\}<\/script><\/head>/,
  );
});

test("withInitialState escapes script-breaking roster text", () => {
  const html = withInitialState(SHELL, {
    characters: [{ slug: "ada", name: "</script><script>alert(1)</script>" }],
  });
  assert.doesNotMatch(html, /<\/script><script>alert\(1\)/);
  assert.match(html, /\\u003c\/script\\u003e/);
});
