// Inline first-paint data into the Vite shell without turning the app into an
// SSR build. The HTML is shared at the edge, so callers must only pass public,
// URL-invariant state here.
export function withInitialState(html, state) {
  const json = JSON.stringify(state)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
  return html.replace(
    "</head>",
    `<script>window.__OPENSMASH_INITIAL_STATE__=${json}</script></head>`,
  );
}
