export const CHARACTER_MESHES = [
  { value: "auto", label: "Automatic" },
  { value: "mario", label: "Mario", fkind: 0 },
  { value: "fox", label: "Fox", fkind: 1 },
  { value: "donkey", label: "Donkey Kong", fkind: 2 },
  { value: "samus", label: "Samus", fkind: 3 },
  { value: "luigi", label: "Luigi", fkind: 4 },
  { value: "link", label: "Link", fkind: 5 },
  { value: "yoshi", label: "Yoshi", fkind: 6 },
  { value: "captain", label: "Captain Falcon", fkind: 7 },
  { value: "kirby", label: "Kirby", fkind: 8 },
  { value: "pikachu", label: "Pikachu", fkind: 9 },
  { value: "purin", label: "Jigglypuff", fkind: 10 },
  { value: "ness", label: "Ness", fkind: 11 },
];

export const STAGES = [
  { value: "random", label: "Random" },
  { value: "0", label: "Peach's Castle" },
  { value: "1", label: "Sector Z" },
  { value: "2", label: "Kongo Jungle" },
  { value: "3", label: "Planet Zebes" },
  { value: "4", label: "Hyrule Castle" },
  { value: "5", label: "Yoshi's Island" },
  { value: "6", label: "Dream Land" },
  { value: "7", label: "Saffron City" },
  { value: "8", label: "Mushroom Kingdom" },
];

export const OPPONENT_LEVELS = [
  { value: "1", label: "Level 1 — Very Easy" },
  { value: "2", label: "Level 2" },
  { value: "3", label: "Level 3 — Easy" },
  { value: "4", label: "Level 4" },
  { value: "5", label: "Level 5 — Normal" },
  { value: "6", label: "Level 6" },
  { value: "7", label: "Level 7 — Hard" },
  { value: "8", label: "Level 8" },
  { value: "9", label: "Level 9 — Very Hard" },
];

export const BOOT_MODES = [
  { value: "free-for-all", label: "Free-for-All", description: "Skip menus and start a VS match." },
  { value: "vs-menu", label: "VS Menu", description: "Open the VS mode menu." },
  { value: "vs-character-select", label: "VS Character Select", description: "Open the multiplayer fighter-select screen." },
  { value: "one-player-character-select", label: "1P Character Select", description: "Open the one-player fighter-select screen." },
  { value: "full-boot", label: "Full Boot", description: "Start from the N64 boot sequence." },
];

export const DEFAULT_ADVANCED_OPTIONS = Object.freeze({
  characterMesh: "auto",
  stage: "random",
  opponentLevel: "3",
  bootMode: "free-for-all",
});

const VALID_MESHES = new Set(CHARACTER_MESHES.map(({ value }) => value));
const VALID_STAGES = new Set(STAGES.map(({ value }) => value));
const VALID_OPPONENT_LEVELS = new Set(OPPONENT_LEVELS.map(({ value }) => value));
const VALID_BOOT_MODES = new Set(BOOT_MODES.map(({ value }) => value));

export function normalizeAdvancedOptions(value) {
  return {
    characterMesh: VALID_MESHES.has(value?.characterMesh)
      ? value.characterMesh
      : DEFAULT_ADVANCED_OPTIONS.characterMesh,
    stage: VALID_STAGES.has(value?.stage) ? value.stage : DEFAULT_ADVANCED_OPTIONS.stage,
    opponentLevel: VALID_OPPONENT_LEVELS.has(value?.opponentLevel)
      ? value.opponentLevel
      : DEFAULT_ADVANCED_OPTIONS.opponentLevel,
    bootMode: VALID_BOOT_MODES.has(value?.bootMode)
      ? value.bootMode
      : DEFAULT_ADVANCED_OPTIONS.bootMode,
  };
}

export function hasAdvancedOverrides(options) {
  return Object.keys(DEFAULT_ADVANCED_OPTIONS).some(
    (key) => options[key] !== DEFAULT_ADVANCED_OPTIONS[key],
  );
}

function resolvedCharacter(character, meshName) {
  if (!character || meshName === "auto") return character;

  const mesh = CHARACTER_MESHES.find(({ value }) => value === meshName);
  if (!mesh || mesh.fkind === character.fkind) return character;

  if (meshName === "mario") {
    return {
      ...character,
      fkind: mesh.fkind,
      base: meshName,
      bundle: `${character.slug}.osb`,
      bundleUrl: character.originalBundleUrl || character.bundleUrl || null,
    };
  }

  const bundleUrl = character.variants?.[meshName] || (
    character.bundleUrl ? null : `bundles/${character.slug}-${meshName}.osb`
  );
  if (!bundleUrl) {
    throw new Error(`${character.name} does not have a ${mesh.label} mesh variant.`);
  }

  return {
    ...character,
    fkind: mesh.fkind,
    base: meshName,
    bundle: `${character.slug}-${meshName}.osb`,
    bundleUrl,
  };
}

function randomItem(items, random) {
  return items.length ? items[Math.floor(random() * items.length)] : null;
}

function uniqueCharacters(characters) {
  const seen = new Set();
  return characters.filter((character) => {
    if (!character?.slug || seen.has(character.slug)) return false;
    seen.add(character.slug);
    return true;
  });
}

export function selectDirectBattleOpponents(
  selectedCharacter,
  gridCharacters,
  ownedCharacters = [],
  random = Math.random,
) {
  const selectedSlug = selectedCharacter?.slug;
  const uniqueGrid = uniqueCharacters(gridCharacters);
  const availableGrid = uniqueGrid.filter((character) => character.slug !== selectedSlug);
  const availableOwned = uniqueCharacters(ownedCharacters)
    .filter((character) => character.slug !== selectedSlug);
  const ownedSlugs = new Set(availableOwned.map((character) => character.slug));
  const nonOwnedGrid = availableGrid.filter((character) => !ownedSlugs.has(character.slug));
  const gridCharacter = randomItem(
    nonOwnedGrid.length ? nonOwnedGrid : (availableGrid.length ? availableGrid : uniqueGrid),
    random,
  );
  const ownedCharacter = randomItem(
    availableOwned.filter((character) => character.slug !== gridCharacter?.slug),
    random,
  );
  const fallbackCharacter = ownedCharacter || randomItem(
    availableGrid.filter((character) => character.slug !== gridCharacter?.slug),
    random,
  ) || gridCharacter;

  return [
    { type: "vanilla", fkind: Math.floor(random() * 12) },
    ...(gridCharacter ? [{ type: "character", character: gridCharacter }] : []),
    ...(fallbackCharacter ? [{ type: "character", character: fallbackCharacter }] : []),
  ];
}

function characterInjection(character, player) {
  return {
    player,
    slug: character.slug,
    fkind: character.fkind,
    short: character.short || character.name,
    bundleUrl: character.bundleUrl || `bundles/${character.bundle}`,
    uiUrl: character.uiUrl || (character.ui ? `bundles/${character.slug}.osbui` : null),
    voiceUrl: character.voiceUrl || (character.voice ? `bundles/${character.slug}.wav` : null),
  };
}

function directBattle(params, character, stage, opponents) {
  const player = character?.fkind ?? 0;
  const cpuKinds = opponents?.map((opponent) => (
    opponent.type === "character" ? opponent.character.fkind : opponent.fkind
  ));
  const [playerTwo, playerThree, playerFour] = cpuKinds?.length === 3
    ? cpuKinds
    : [
        Math.floor(Math.random() * 12),
        Math.floor(Math.random() * 12),
        Math.floor(Math.random() * 12),
      ];
  params.set(
    "SSB64_BOOT_BATTLE",
    [player, playerTwo, stage, 1, playerThree, playerFour].join(","),
  );
  opponents?.forEach((opponent, index) => {
    if (opponent.type === "character") {
      params.append("inject_player", JSON.stringify(characterInjection(opponent.character, index + 1)));
    }
  });
}

export function engineUrl(action, advancedOptions) {
  const options = normalizeAdvancedOptions(advancedOptions);
  const character = resolvedCharacter(action.character, options.characterMesh);
  const stage = options.stage === "random" ? Math.floor(Math.random() * 9) : Number(options.stage);
  const params = new URLSearchParams();

  if (character) {
    params.set("inject", character.bundleUrl || `bundles/${character.bundle}`);
    if (character.uiUrl || character.ui) {
      params.set("inject_ui", character.uiUrl || `bundles/${character.slug}.osbui`);
    }
    if (character.voiceUrl || character.voice) {
      params.set("inject_voice", character.voiceUrl || `bundles/${character.slug}.wav`);
    }
    params.set("fkind", String(character.fkind));
    params.set("player", "0");
    if (options.characterMesh !== "auto") {
      params.set("base", `${character.slug}:${options.characterMesh}`);
    }
  }

  if (options.bootMode === "default") {
    if (action.type === "character") directBattle(params, character, stage, action.opponents);
    if (action.type === "select") {
      params.set("SSB64_START_SCENE", "16");
      params.set("roster", "1");
    }
  } else if (options.bootMode === "free-for-all") {
    directBattle(params, character, stage, action.type === "character" ? action.opponents : null);
  } else if (options.bootMode === "vs-menu") {
    params.set("SSB64_START_SCENE", "9");
    params.set("roster", "1");
  } else if (options.bootMode === "vs-character-select") {
    params.set("SSB64_START_SCENE", "16");
    params.set("roster", "1");
  } else if (options.bootMode === "one-player-character-select") {
    params.set("SSB64_START_SCENE", "17");
    params.set("roster", "1");
  }

  if (
    (character || options.stage !== "random") &&
    options.bootMode !== "default" &&
    options.bootMode !== "free-for-all" &&
    options.bootMode !== "full-boot" &&
    options.bootMode !== "one-player-character-select"
  ) {
    params.set("SSB64_BOOT_BATTLE", `${character?.fkind ?? -1},8,${stage}`);
  } else if (
    action.type === "select" &&
    options.bootMode === "default" &&
    options.stage !== "random"
  ) {
    params.set("SSB64_BOOT_BATTLE", `-1,8,${stage}`);
  }

  if (params.has("SSB64_BOOT_BATTLE")) {
    params.set("SSB64_CPU_LEVEL", options.opponentLevel);
  }

  return `/engine/?${params}`;
}
