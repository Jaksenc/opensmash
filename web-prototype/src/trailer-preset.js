import { FULL_BOOT_INTRO_CARDS } from "./launch-options.js";
import trailerConfig from "../config/trailer.js";

export const TRAILER_CONFIG = trailerConfig;
export const TRAILER_INTRO_SLUGS = trailerConfig.introFighters;
export const TRAILER_INTRO_ROOM_PICKS = trailerConfig.introRoomPicks;
export const TRAILER_OPPONENT_SLUGS = trailerConfig.match.opponents;
export const TRAILER_STAGE = trailerConfig.match.stage;
export const TRAILER_CPU_LEVEL = trailerConfig.match.cpuLevel;

function characterBySlug(characters, slug) {
  return characters.find((character) => character.slug === slug) || null;
}

export function createTrailerIntroConfig(characters) {
  let injectedIndex = 0;
  return FULL_BOOT_INTRO_CARDS.map((card) => {
    if (card.mode === "vanilla") return { ...card, type: "vanilla" };

    const slug = TRAILER_INTRO_SLUGS[injectedIndex++];
    const character = characterBySlug(characters, slug);
    if (!character) return { ...card, type: "vanilla" };

    // The capture cast uses OSB6 bundles with every production-ready target.
    // Pinning fkind/base makes the opening-card assignment deterministic.
    return {
      ...card,
      type: "character",
      character: { ...character, fkind: card.fkind, base: card.mesh },
    };
  });
}

export function createTrailerIntroAction(action, characters) {
  const introConfig = createTrailerIntroConfig(characters);
  const availableSlugs = new Set(
    introConfig
      .filter((card) => card.type === "character")
      .map((card) => card.character.slug),
  );
  const missingSlug = TRAILER_INTRO_ROOM_PICKS.find((slug) => !availableSlugs.has(slug));
  if (missingSlug) {
    throw new Error(`Trailer opening-room fighter is unavailable: ${missingSlug}`);
  }
  if (TRAILER_INTRO_ROOM_PICKS.length !== 2 || new Set(TRAILER_INTRO_ROOM_PICKS).size !== 2) {
    throw new Error("Trailer config needs two different opening-room fighters.");
  }

  return {
    ...action,
    introConfig,
    introRoomPicks: [...TRAILER_INTRO_ROOM_PICKS],
  };
}

export function createTrailerMatchAction(action, characters) {
  const selectedSlugs = new Set([
    action.character?.slug,
    ...(action.picks || []).map((pick) => pick?.slug),
  ].filter(Boolean));
  const opponentCount = Math.max(0, 4 - selectedSlugs.size);
  const configuredSlugs = TRAILER_OPPONENT_SLUGS
    .filter((slug) => !selectedSlugs.has(slug))
    .slice(0, opponentCount);
  const opponents = configuredSlugs.map((slug) => characterBySlug(characters, slug));
  const missingIndex = opponents.findIndex((opponent) => !opponent);
  if (missingIndex >= 0) {
    throw new Error(`Trailer opponent is unavailable: ${configuredSlugs[missingIndex]}`);
  }
  if (opponents.length !== opponentCount) {
    throw new Error(`Trailer config needs ${opponentCount} available opponents outside the current picks.`);
  }

  return {
    ...action,
    opponents: opponents.map((opponent) => ({ type: "character", character: opponent })),
  };
}
