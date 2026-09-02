import { useEffect, useState } from "react";

// Browsers expose a gamepad to a page only after a button press on it, and
// gamepadconnected fires once per pad from then on. A slow poll covers pads
// that were pressed before our listener existed; Chrome allocates wrapper
// objects on every getGamepads() call, so keep it infrequent.
const POLL_INTERVAL_MS = 2000;

export function readGamepads() {
  try {
    const list = navigator.getGamepads?.() || [];
    return Array.from(list)
      .filter((pad) => pad && pad.connected)
      .map((pad) => ({ index: pad.index, id: pad.id, mapping: pad.mapping }));
  } catch {
    return [];
  }
}

function sameGamepads(left, right) {
  if (left.length !== right.length) return false;
  return left.every((pad, i) => pad.index === right[i].index && pad.id === right[i].id);
}

export function useGamepads() {
  const [gamepads, setGamepads] = useState(readGamepads);

  useEffect(() => {
    const sync = () => {
      setGamepads((current) => {
        const next = readGamepads();
        return sameGamepads(current, next) ? current : next;
      });
    };
    window.addEventListener("gamepadconnected", sync);
    window.addEventListener("gamepaddisconnected", sync);
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") sync();
    }, POLL_INTERVAL_MS);
    return () => {
      window.removeEventListener("gamepadconnected", sync);
      window.removeEventListener("gamepaddisconnected", sync);
      window.clearInterval(timer);
    };
  }, []);

  return gamepads;
}
