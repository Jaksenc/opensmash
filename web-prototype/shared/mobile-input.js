// Engine keyboard map: WASD stick, J=A, K=B, L=Z, I=L, O=R, Space=Start,
// U=C-up (jump in Smash 64). Arrows are a stick fallback, so the overlay's
// Jump must send KeyU rather than ArrowUp.
export const MOBILE_KEY_VALUES = Object.freeze({
  KeyA: "a",
  KeyD: "d",
  KeyI: "i",
  KeyJ: "j",
  KeyK: "k",
  KeyL: "l",
  KeyO: "o",
  KeyS: "s",
  KeyU: "u",
  KeyW: "w",
  Space: " ",
});

export function joystickCodesForVector(x, y, radius, {
  axisThreshold = 0.32,
  deadZone = 0.28,
} = {}) {
  const safeRadius = Math.max(1, radius);
  const normalizedX = x / safeRadius;
  const normalizedY = y / safeRadius;
  const codes = new Set();
  if (Math.hypot(normalizedX, normalizedY) < deadZone) return codes;
  if (normalizedX <= -axisThreshold) codes.add("KeyA");
  if (normalizedX >= axisThreshold) codes.add("KeyD");
  if (normalizedY <= -axisThreshold) codes.add("KeyW");
  if (normalizedY >= axisThreshold) codes.add("KeyS");
  return codes;
}

export function dispatchGameKey(frame, code, pressed) {
  try {
    const frameWindow = frame?.contentWindow;
    const canvas = frame?.contentDocument?.getElementById("canvas");
    if (!frameWindow?.KeyboardEvent || !canvas) return false;
    if (pressed) canvas.focus?.({ preventScroll: true });
    canvas.dispatchEvent(new frameWindow.KeyboardEvent(pressed ? "keydown" : "keyup", {
      bubbles: true,
      cancelable: true,
      code,
      key: MOBILE_KEY_VALUES[code] || code,
    }));
    return true;
  } catch {
    return false;
  }
}
