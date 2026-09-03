// The keyboard map the engine shell resolves in JS (BattleShip/web/index.html
// KEY_MAP). Bindings are PHYSICAL (event.code): the right-hand cluster
// stays under the fingers on every layout. Controls are the tutorial's
// ids: w a s d = stick, j=A k=B l=Z i=L o=R (named after the QWERTY caps).
export const CONTROL_KEYS = Object.freeze(['w', 'a', 's', 'd', 'j', 'k', 'l', 'i', 'o']);

// Physical code -> control id. Every entry is a real engine binding.
export const CODE_CONTROLS = Object.freeze({
  KeyW: 'w', KeyA: 'a', KeyS: 's', KeyD: 'd',
  KeyJ: 'j', KeyK: 'k', KeyL: 'l', KeyI: 'i', KeyO: 'o',
  ArrowUp: 'w', ArrowDown: 's', ArrowLeft: 'a', ArrowRight: 'd',
  ControlLeft: 'j', ControlRight: 'j', AltLeft: 'k', AltRight: 'k',
  ShiftLeft: 'l', ShiftRight: 'l',
});

// What the keycap says on a US QWERTY board; other layouts override via
// the layout map (see keycapLabels()).
export const QWERTY_LABELS = Object.freeze({
  w: 'W', a: 'A', s: 'S', d: 'D', j: 'J', k: 'K', l: 'L', i: 'I', o: 'O',
});

// Short "or ..." hints shown under the tutorial keycaps.
export const CONTROL_ALT_LABELS = Object.freeze({
  stick: 'or arrow keys', j: 'or Ctrl', k: 'or Alt', l: 'or Shift',
});

// The primary (letter) code for each control, used to look up its label.
const CONTROL_CODES = Object.freeze({
  w: 'KeyW', a: 'KeyA', s: 'KeyS', d: 'KeyD',
  j: 'KeyJ', k: 'KeyK', l: 'KeyL', i: 'KeyI', o: 'KeyO',
});

// event -> control id, or null. Prefers the physical code; a synthetic
// event with only a key falls back to treating the letter as its code.
export function controlForEvent(event) {
  if (!event) return null;
  const code = typeof event.code === 'string' && event.code ? event.code
    : (typeof event.key === 'string' && event.key.length === 1 ? 'Key' + event.key.toUpperCase() : '');
  return CODE_CONTROLS[code] ?? null;
}

// A modifier pressed ON ITS OWN is a game button (Ctrl=A, Alt=B, Shift=Z),
// not a shortcut chord; anything with Meta, or a modifier held while a
// different key goes down, is left to the browser.
export function isControlChord(event) {
  if (!event || event.metaKey) return true;
  const code = String(event.code || '');
  if (event.ctrlKey && !code.startsWith('Control')) return true;
  if (event.altKey && !code.startsWith('Alt')) return true;
  return false;
}

// Per-control keycap labels for the viewer's layout: the browser's layout
// map where it exists (Chromium), else QWERTY (Firefox/Safari expose no
// layout information; guessing from presses was rejected as too weird).
export async function keycapLabels(keyboard = globalThis.navigator?.keyboard) {
  const labels = { ...QWERTY_LABELS };
  try {
    const map = keyboard?.getLayoutMap ? await keyboard.getLayoutMap() : null;
    if (map) {
      for (const [control, code] of Object.entries(CONTROL_CODES)) {
        const label = map.get(code);
        if (typeof label === 'string' && label.length === 1) labels[control] = label.toUpperCase();
      }
    }
  } catch { /* layout map unavailable: QWERTY */ }
  return labels;
}
