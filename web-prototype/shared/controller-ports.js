// Logical N64 port plan: which device (a browser Gamepad or the keyboard)
// drives ports 1-4. The engine shell (BattleShip/web/index.html,
// window.controllerPorts) applies the same hot-plug rules while the game
// runs; keep the two in sync.
//
// Player choices are stored per port as a string:
//   "auto"              the default: controller k on port k (connection
//                       order); the keyboard on P1 only when there is no
//                       controller. Overrides never reshuffle the others.
//   "none"              leave the port empty
//   "keyboard"          the keyboard
//   "gamepad:<index>"   the Gamepad with that navigator index
// The resolved plan has one entry per port:
//   { kind: "gamepad", id, index } | { kind: "keyboard" } | { kind: "none" } | null
// where "none" is an explicit close (the shell will not hot-plug into it)
// and null is simply unfilled.

export const MAX_PORTS = 4;
export const AUTO = "auto";
export const NONE = "none";
export const KEYBOARD = "keyboard";

export function gamepadChoice(pad) {
  return `gamepad:${pad.index}`;
}

export function normalizePortChoices(value) {
  const choices = new Array(MAX_PORTS).fill(AUTO);
  if (!Array.isArray(value)) return choices;
  for (let i = 0; i < MAX_PORTS; i += 1) {
    const choice = value[i];
    if (choice === NONE || choice === KEYBOARD || /^gamepad:\d{1,2}$/.test(choice)) {
      choices[i] = choice;
    }
  }
  return choices;
}

// "DualSense Wireless Controller (STANDARD GAMEPAD Vendor: 054c Product: 0ce6)"
// -> "DualSense Wireless Controller"
export function padDisplayName(id) {
  const cleaned = String(id || "")
    .replace(/\((?:STANDARD GAMEPAD)?[^)]*Vendor:[^)]*\)/gi, "")
    .replace(/\(STANDARD GAMEPAD\)/gi, "")
    .replace(/\s+/g, " ")
    .trim();
  return cleaned || "Controller";
}

// Display name, numbered when two identical controllers are connected.
export function padLabel(pad, gamepads = []) {
  const name = padDisplayName(pad.id);
  const twins = gamepads
    .filter((other) => padDisplayName(other.id) === name)
    .sort((left, right) => left.index - right.index);
  if (twins.length < 2) return name;
  const position = twins.findIndex((other) => other.index === pad.index);
  return `${name} ${position + 1}`;
}

function padByChoice(choice, gamepads) {
  const match = /^gamepad:(\d+)$/.exec(choice);
  if (!match) return null;
  const index = Number(match[1]);
  return gamepads.find((pad) => pad.index === index) || null;
}

export function planControllerPorts({ gamepads = [], ports } = {}) {
  const choices = normalizePortChoices(ports);
  const pads = gamepads
    .filter((pad) => pad && typeof pad.id === "string" && Number.isInteger(pad.index))
    .sort((left, right) => left.index - right.index);
  const plan = new Array(MAX_PORTS).fill(null);
  const claimedPads = new Set();
  let keyboardClaimed = false;

  // Overrides take exactly what they name. A device can only sit on one
  // port; a later duplicate is ignored. A chosen controller that is not
  // connected leaves the port empty.
  choices.forEach((choice, port) => {
    if (choice === NONE) {
      plan[port] = { kind: NONE };
    } else if (choice === KEYBOARD) {
      if (!keyboardClaimed) {
        keyboardClaimed = true;
        plan[port] = { kind: KEYBOARD };
      }
    } else if (choice !== AUTO) {
      const pad = padByChoice(choice, pads);
      if (pad && !claimedPads.has(pad.index)) {
        claimedPads.add(pad.index);
        plan[port] = { kind: "gamepad", id: pad.id, index: pad.index };
      }
    }
  });

  // Defaults: controller k sits on port k, and the keyboard is P1 only when
  // there is no controller at all. A default whose device an override took
  // elsewhere stays empty rather than reflowing the others.
  choices.forEach((choice, port) => {
    if (choice !== AUTO) return;
    const pad = pads[port];
    if (pad) {
      if (!claimedPads.has(pad.index)) {
        claimedPads.add(pad.index);
        plan[port] = { kind: "gamepad", id: pad.id, index: pad.index };
      }
    } else if (port === 0 && pads.length === 0 && !keyboardClaimed) {
      keyboardClaimed = true;
      plan[port] = { kind: KEYBOARD };
    }
  });

  return plan;
}

export function humanPortCount(plan) {
  return plan.filter((entry) => entry && entry.kind !== NONE).length;
}

export function describePort(entry, gamepads = []) {
  if (!entry || entry.kind === NONE) return "";
  if (entry.kind === KEYBOARD) return "Keyboard";
  const pad = gamepads.find((candidate) => candidate.index === entry.index) || entry;
  return padLabel(pad, gamepads);
}

// The choice string that reproduces what a port currently shows.
export function choiceForEntry(entry) {
  if (!entry || entry.kind === NONE) return NONE;
  if (entry.kind === KEYBOARD) return KEYBOARD;
  return `gamepad:${entry.index}`;
}

// Dropdown contents for one port: the devices no other port is using, plus
// whatever this port shows now. Empty `options` (besides None) means the
// port cannot be filled until another controller is connected.
export function portOptions(plan, gamepads, port) {
  const usedElsewhere = new Set(
    plan.filter((entry, i) => i !== port && entry).map((entry) => choiceForEntry(entry)),
  );
  const options = [];
  if (!usedElsewhere.has(KEYBOARD)) options.push({ value: KEYBOARD, label: "Keyboard" });
  for (const pad of [...gamepads].sort((left, right) => left.index - right.index)) {
    const value = gamepadChoice(pad);
    if (!usedElsewhere.has(value)) options.push({ value, label: padLabel(pad, gamepads) });
  }
  return options;
}

// Query parameters the engine shell reads (see window.controllerPorts).
export function controllerPortParams(plan) {
  return { ports: JSON.stringify(plan) };
}
