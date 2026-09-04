export const FIGHTERS = [
  "mario", "fox", "donkey", "samus", "luigi", "link",
  "yoshi", "captain", "kirby", "pikachu", "purin", "ness",
];

// DK/Yoshi remain valid explicit targets but are not production defaults.
// Keep this order aligned with BattleShip's dev roster assignment.
export const DEFAULT_ROSTER_BASES = [
  "mario", "fox", "samus", "luigi", "link",
  "captain", "kirby", "pikachu", "purin", "ness",
];

const BASE_ALIASES = new Map([
  ["", "mario"], ["donkeykong", "donkey"], ["dk", "donkey"],
  ["jigglypuff", "purin"], ["falcon", "captain"],
  ["captainfalcon", "captain"],
]);

export function normalizeBase(name) {
  if (typeof name !== "string") return null;
  const key = name.toLowerCase().replaceAll(" ", "");
  return BASE_ALIASES.get(key) ?? key;
}

function hasBundleFor(character, base) {
  return base === "mario" || (character.variants || []).includes(base);
}

export function assignRosterBases(characters) {
  const usage = new Map(DEFAULT_ROSTER_BASES.map((base) => [base, 0]));

  return characters.map((source) => {
    const character = { ...source };
    const explicit = normalizeBase(character.base);
    if (explicit !== null) {
      character.base = explicit;
      if (usage.has(explicit)) usage.set(explicit, usage.get(explicit) + 1);
      delete character.preferredBases;
      return character;
    }

    const requested = Array.isArray(character.preferredBases) && character.preferredBases.length
      ? character.preferredBases
      : DEFAULT_ROSTER_BASES;
    let candidates = [];
    for (const preference of requested) {
      const base = normalizeBase(preference);
      if (
        DEFAULT_ROSTER_BASES.includes(base) &&
        !candidates.includes(base) &&
        hasBundleFor(character, base)
      ) candidates.push(base);
    }
    if (!candidates.length) {
      candidates = DEFAULT_ROSTER_BASES.filter((base) => hasBundleFor(character, base));
    }

    if (candidates.length) {
      character.base = candidates.reduce((best, base) => (
        usage.get(base) < usage.get(best) ? base : best
      ));
      usage.set(character.base, usage.get(character.base) + 1);
    }
    delete character.preferredBases;
    return character;
  });
}

// Backyard positions -> playstyle classes. Each class lists the Smash bases
// whose moveset fits, in preference order, plus flavor for the draft board.
// Salary (followers) is the cost/power knob from backyarddesigners.club.
export const POSITION_CLASSES = {
  "Design Leader": {
    class: "captain",
    label: "Captain",
    playstyle: "all-rounder, team buffs",
    bases: ["mario", "luigi", "captain", "samus"],
  },
  "Product Designer": {
    class: "rushdown",
    label: "Rushdown",
    playstyle: "fast pressure, pixel-precise punishes",
    bases: ["fox", "captain", "kirby", "pikachu"],
  },
  "Design Engineer": {
    class: "zoner",
    label: "Zoner",
    playstyle: "traps + projectiles, toolbelt gadgets",
    bases: ["link", "samus", "fox", "pikachu"],
  },
  "Brand Designer": {
    class: "tricky",
    label: "Tricky",
    playstyle: "status / sleep setups, big brand moments",
    bases: ["purin", "ness", "kirby", "luigi"],
  },
  "Web Designer": {
    class: "control",
    label: "Control",
    playstyle: "capsule / egg control, stage coverage",
    bases: ["yoshi", "link", "ness", "kirby"],
  },
  "Wildcard": {
    class: "heavy",
    label: "Heavy",
    playstyle: "hard reads, beam finishers",
    bases: ["donkey", "samus", "captain", "ness"],
  },
};

export function normalizePosition(name) {
  if (typeof name !== "string") return null;
  const key = name.trim().toLowerCase();
  for (const position of Object.keys(POSITION_CLASSES)) {
    if (position.toLowerCase() === key) return position;
  }
  return null;
}

export function positionClassFor(position) {
  const normalized = normalizePosition(position);
  return normalized ? POSITION_CLASSES[normalized] : null;
}

// Attach `positionClass` + default `preferredBases` from backyard position
// when the entry doesn't already pin them. Never overrides explicit picks.
export function assignPositionClasses(characters) {
  return characters.map((source) => {
    const character = { ...source };
    const info = positionClassFor(character.position);
    if (info) {
      character.positionClass = info.class;
      character.positionLabel = info.label;
      character.playstyle = info.playstyle;
      if (!character.base && !character.preferredBases) {
        character.preferredBases = [...info.bases];
      }
    }
    return character;
  });
}

// One OSB6 per character carries every built target; the engine picks the
// block for the fighter it spawns, so the file name no longer encodes the base.
export function bundleForBase(slug) {
  return `${slug}.osb6`;
}

// Target names present in an OSB6 (pipeline/osb_merge.py layout):
//   'OSB6' u32 texW, texH, ntargets; u16 atlas[texW*texH];
//   ntargets x { u32 fkind, u32 length, payload[length] }
// Only the block headers are read, so this costs a few hundred bytes of I/O.
export async function readOsb6Targets(filePath) {
  const { open } = await import("node:fs/promises");
  const handle = await open(filePath, "r");
  try {
    const head = Buffer.alloc(16);
    if ((await handle.read(head, 0, 16, 0)).bytesRead !== 16 || head.toString("latin1", 0, 4) !== "OSB6") {
      throw new Error(`${filePath}: not an OSB6 bundle`);
    }
    const texW = head.readUInt32LE(4);
    const texH = head.readUInt32LE(8);
    const count = head.readUInt32LE(12);
    if (count > 64) throw new Error(`${filePath}: implausible target count ${count}`);
    let offset = 16 + texW * texH * 2;
    const targets = [];
    const block = Buffer.alloc(8);
    for (let index = 0; index < count; index += 1) {
      if ((await handle.read(block, 0, 8, offset)).bytesRead !== 8) break;
      const fkind = block.readUInt32LE(0);
      const length = block.readUInt32LE(4);
      if (fkind < FIGHTERS.length) targets.push(FIGHTERS[fkind]);
      offset += 8 + length;
    }
    return targets;
  } finally {
    await handle.close();
  }
}
