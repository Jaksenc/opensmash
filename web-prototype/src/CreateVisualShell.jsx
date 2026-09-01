import { useEffect } from "react";
import { LaunchFlow } from "./RetroHome.jsx";

const CRT_RUNTIME = "/visual/crt-viewport.js?v=20260901-create1";
const CREATE_ROM_RUNTIME = "/visual/game-launcher.js?v=20260901-inline-create2";
let createRomRuntimePromise;

function loadVisualStyles() {
  return new Promise((resolve, reject) => {
    const existing = document.getElementById("site-shell-styles");
    if (existing) {
      if (existing.sheet) resolve();
      else existing.addEventListener("load", resolve, { once: true });
      return;
    }
    const link = document.createElement("link");
    link.id = "site-shell-styles";
    link.rel = "stylesheet";
    link.href = "/visual/site-shell.css?v=20260901-fighter-progress5";
    link.addEventListener("load", resolve, { once: true });
    link.addEventListener("error", () => reject(new Error("Could not load the ROM upload screen")), { once: true });
    document.head.append(link);
  });
}

function startCreateRomRuntime() {
  createRomRuntimePromise ||= loadVisualStyles().then(() => new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.type = "module";
    script.src = CREATE_ROM_RUNTIME;
    script.addEventListener("load", resolve, { once: true });
    script.addEventListener("error", () => reject(new Error("Could not load the cartridge upload screen")), { once: true });
    document.body.append(script);
  }));
  return createRomRuntimePromise;
}

export default function CreateVisualShell({ onError, romUploadRequired }) {
  useEffect(() => {
    document.body.classList.add("create-retro-screen");
    let script;
    let cancelled = false;
    const startTimer = window.setTimeout(() => {
      if (cancelled || window.__crtViewport?.canvas?.isConnected) return;
      script = document.createElement("script");
      script.type = "module";
      script.src = CRT_RUNTIME;
      document.body.append(script);
    });

    return () => {
      cancelled = true;
      window.clearTimeout(startTimer);
      script?.remove();
      document.body.classList.remove("create-retro-screen");
    };
  }, []);

  useEffect(() => {
    if (!romUploadRequired) return undefined;
    let cancelled = false;
    startCreateRomRuntime()
      .then(() => {
        if (!cancelled) window.gameLauncher?.requestCreate?.();
      })
      .catch((error) => {
        if (!cancelled) onError(error);
      });
    return () => { cancelled = true; };
  }, [onError, romUploadRequired]);

  return (
    <>
      <LaunchFlow />
      <canvas id="crt-viewport-canvas" aria-hidden="true" />
    </>
  );
}
