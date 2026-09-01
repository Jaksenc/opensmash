export const MOBILE_KEY_VALUES = Object.freeze({
  KeyA: "a",
  KeyC: "c",
  KeyD: "d",
  KeyE: "e",
  KeyR: "r",
  KeyS: "s",
  KeyW: "w",
  KeyX: "x",
  KeyZ: "z",
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
