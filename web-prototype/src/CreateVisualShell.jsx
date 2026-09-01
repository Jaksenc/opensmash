import { useEffect } from "react";
import { LaunchFlow } from "./RetroHome.jsx";
import { startCreateRuntime, startCrtRuntime } from "./visual-runtime.js";

export default function CreateVisualShell({ onError, romUploadRequired }) {
  useEffect(() => {
    document.body.classList.add("create-retro-screen");
    let cancelled = false;
    const startTimer = window.setTimeout(() => {
      if (cancelled || window.__crtViewport?.canvas?.isConnected) return;
      startCrtRuntime().catch((error) => {
        if (!cancelled) onError(error);
      });
    });

    return () => {
      cancelled = true;
      window.clearTimeout(startTimer);
      document.body.classList.remove("create-retro-screen");
    };
  }, [onError]);

  useEffect(() => {
    if (!romUploadRequired) return undefined;
    let cancelled = false;
    startCreateRuntime()
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
