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

export function bundleForBase(slug, base) {
  return base === "mario" ? `${slug}.osb` : `${slug}-${base}.osb`;
}
