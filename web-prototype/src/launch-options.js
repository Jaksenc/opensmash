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
  bootMode: "free-for-all",
});

const VALID_MESHES = new Set(CHARACTER_MESHES.map(({ value }) => value));
const VALID_STAGES = new Set(STAGES.map(({ value }) => value));
const VALID_BOOT_MODES = new Set(BOOT_MODES.map(({ value }) => value));

export function normalizeAdvancedOptions(value) {
  return {
    characterMesh: VALID_MESHES.has(value?.characterMesh)
      ? value.characterMesh
      : DEFAULT_ADVANCED_OPTIONS.characterMesh,
    stage: VALID_STAGES.has(value?.stage) ? value.stage : DEFAULT_ADVANCED_OPTIONS.stage,
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

function directBattle(params, character, stage) {
  const player = character?.fkind ?? 0;
  params.set(
    "SSB64_BOOT_BATTLE",
    [player, Math.floor(Math.random() * 12), stage, 1, Math.floor(Math.random() * 12), Math.floor(Math.random() * 12)].join(","),
  );
}

export function engineUrl(action, advancedOptions, now = Date.now()) {
  const options = normalizeAdvancedOptions(advancedOptions);
  const character = resolvedCharacter(action.character, options.characterMesh);
  const stage = options.stage === "random" ? Math.floor(Math.random() * 9) : Number(options.stage);
  const params = new URLSearchParams({ cb: String(now) });

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
    if (action.type === "character") directBattle(params, character, stage);
    if (action.type === "select") {
      params.set("SSB64_START_SCENE", "16");
      params.set("roster", "1");
    }
  } else if (options.bootMode === "free-for-all") {
    directBattle(params, character, stage);
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

  return `/engine/?${params}`;
}
