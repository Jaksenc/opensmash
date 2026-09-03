import "../visual/site-shell.css";

let homeRuntimePromise;
let createRuntimePromise;
let crtRuntimePromise;

// Dynamic-import failures (including exceptions thrown during module
// evaluation) would otherwise resolve into a silently rejected promise that
// nobody awaits. Route them to the global error handler so they show up.
function surfaceImportFailure(promise, name) {
  promise.catch(error => {
    console.error(`[visual-runtime] ${name} failed to load`, error);
    if (typeof window.reportError === 'function') window.reportError(error);
  });
  return promise;
}

export function startCrtRuntime() {
  crtRuntimePromise ||= surfaceImportFailure(import("../visual/crt-viewport.js"), "crt-viewport");
  return crtRuntimePromise;
}

export function startCreateRuntime() {
  createRuntimePromise ||= surfaceImportFailure(import("../visual/game-launcher.js"), "game-launcher");
  return createRuntimePromise;
}

export function startHomeRuntime() {
  homeRuntimePromise ||= surfaceImportFailure(import("../visual/home-runtime.js"), "home-runtime");
  return homeRuntimePromise;
}
