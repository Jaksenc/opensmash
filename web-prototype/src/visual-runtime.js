import "../visual/site-shell.css";

let homeRuntimePromise;
let createRuntimePromise;
let crtRuntimePromise;

export function startCrtRuntime() {
  crtRuntimePromise ||= import("../visual/crt-viewport.js");
  return crtRuntimePromise;
}

export function startCreateRuntime() {
  createRuntimePromise ||= import("../visual/game-launcher.js");
  return createRuntimePromise;
}

export function startHomeRuntime() {
  homeRuntimePromise ||= import("../visual/home-runtime.js");
  return homeRuntimePromise;
}
