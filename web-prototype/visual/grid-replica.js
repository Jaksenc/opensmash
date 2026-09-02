// Responsive extension of the supplied OpenSmash character grid. The lattice,
// fire, captions, and interaction stay code-rendered; character portraits are
// layered into the cells as transparent cutouts. Only generated/featured
// fighters are drawn — the original game's portraits are never bundled or
// served by the site (VANILLA_ROSTER below is metadata only: fkind order,
// labels, and the caption-font baking flags).

import {
  rosterGridDimensions,
  rosterReserveHeight,
} from '../shared/roster-layout.js';
// Character-select name font: the tan 7 px captions baked into the decomp's
// portrait tiles, rebuilt as a bitmap font with the original spacing rules
// (see tools/cssfont and font-playground.html).
import {
  SSB_NAME_FONT,
  layoutText as layoutNameFont,
  renderIA as renderNameFontIA,
  toImageData as nameFontImageData,
} from '../src/fonts/ssb-name-font.js';

const BUILD_ASSETS = {
  ...import.meta.glob('./assets/featured-fighters/action-*.png', {
    eager: true,
    query: '?url',
    import: 'default',
  }),
};

function buildAssetUrl(relativePath) {
  const url = BUILD_ASSETS[`./assets/${relativePath}`];
  if (!url) throw new Error(`Missing visual asset: ${relativePath}`);
  return url;
}

const RASTER_DEBUG = new URLSearchParams(window.location.search);

const CELL_W = 45;
const CELL_H = 43;
const RULE = 2;
// Shared menu cells use the same compressed height as the former control strip.
const FLAME_BRIDGE_HEIGHT_SCALE = 47 / 552;
const GRID_COLUMN_BREAKPOINTS = Object.freeze([
  { minWidth: 800, columns: 8 },
  { minWidth: 640, columns: 6 },
  { minWidth: 0, columns: 4 }
]);
const RASTER_SCALE = 2;
// Placeholder portraits already carry their native roster captions. Keep the
// code-rendered font pipeline intact, but hide it until caption-free art lands.
const USE_SOURCE_PORTRAIT_CAPTIONS = true;
// Preserve the extracted native glyph topology, smooth it into a 2x label
// framebuffer, then composite those finite samples as the visible pixel grid.
const requestedSmoothMix = Number(RASTER_DEBUG.get('smoothMix'));
const LABEL_SMOOTH_MIX = Math.max(0, Math.min(
  1, RASTER_DEBUG.has('smoothMix') && Number.isFinite(requestedSmoothMix)
    ? requestedSmoothMix : 0.5
));
const GEOMETRY_PIXEL_STEP = 4;
const STONE_BACKGROUND_SEED = 3075641479;
const FIRE_RGBA5551 = 'eIeRh5mFqkXDQ9QBzIXcydTJ1IfUQcvBw8HLgcNBw0HCwbsBw0HLwdRB1IPUydSH1MnUydRBzAHDAbLDqcWJRWgHQIVgh1hHWIVIhzCHOEVIhXBHiUeZh7rBcMeJBaIHskXLg8wB1IfUyd0L1MfMQ8vBw4HDgcMBy0G6wbLBw0HUAdRB1IXdC9TJ1QvUydRBzAHDQbKDqgeRR2BFUEdgRWBHaEdYR0iHQIVgR3jFiUWiBbrBCEMIQwhDCEMIQwhDGEMghShFGEMQQyBFIIUwhUCFSEdQh1iHYEdYR1CFSEdYh2BFaAdgR3hHWEVIhyhFIEUoRShFMIUwhTBFKIUoRSBFKEUohSBDEEUQQwhDCEMIQwhDCEMIQwhDGEMgRShFIIMYQxhFKEUwhUBHSIdQh2BHYEVgR1BHWEdYR2iFaEdgR3BHYEVAhShHMEUwhTCFMIU4hzBFMIUwhShFMEUoRSiFEEUQQwhDCEMIQwhDCEMIQwhDEEMoRSBFIEUYgyBFKIU4RUiHSIdYR2BHYIVgR2BFYEdgR2hFWIdoB3gHYIVARzCFMEU4hTCFOEUwhTiHMIUwhTBFOIUwRSCFEEMQQwhDCEMIQwhDCEMIQwhDEEMoRSiFIEUYQyBFMIU4R1BHQIVYR2iHYEVwR2hFYEdgR2BHWEVwB3AHYIc4RTiFOIU4hziFOEU4hzCFOIUwRTCFOEU4hSBFEEUIQQhDCEMIQwhDCEMIQwhDEEMgRSiFKEUYQyBFMIdAhVBFSIdgRWhHaAd4B3BFaAdgh2BFYEd4R2gHUIVAhzhFQIc4hzhFOIU4hziFOIcwRTCFOIUwhyBDEEUIQQhDCEMIQwhDCEMIQwhDCEMgRSiFKEMgRSiFMIVIhUiHUEdgR3hFeAd4SXhHaAVoR1hHcAdwR3AHSIU4hUBFQEdAhzhFQIc4hTiFOIc4hTiFOEUwRRiFEEMIQwhDCEMIQwhDCEMIQwhDCEMgQyiFKEcogyhHOIVIR1CFSEdwR3hFeAeAh3gFcEdoR2BHcAd4R2hFQEdAhUBHQIVAh0hFQIc4RTiHMIU4hTiHOEUohSBDEEUIQQhDCEMIAwhDCEMIAwhDCEMYgyhFKIUoRTCFOIdQh1BHWEVwBYCHeEWAh4BHcAdoB2hFeEVwB2CFQIdAhUCHSIVARUiFSIdARTiHOIU4RUCHMIUohRhFEEMIQwhDCEMIQwhDCEMIQwhDCEMYQyiFMEUwhShFQIdQh1hFaEd4RYBHgIWAh4CHcAdwBXBHgIVwB1iHQEVAh0CFQEdIhVCHSEdAh0BFOIc4RUCHOIUgRRhFEIMIAQhDCEMIQwhDCEMIQQhDCEMYRSiFMEUwRzCFQIdYR2BHaEWASYCFgMWIxYCFeEdwR4CHgMVwB1CFQEdAh0CFSIdIh1BHUEdIR0CFOEVAh0CHMIUoRRhDEEMIQwhDCEMIQwhDCEMIQwhDCEMQQzCHMEUwhTiFSIdgR2BHaEWAyYiHiMeIxYjHgMd4R4jFgMdwR1BHQIVAhUiHQEdQhVhHSIdQR0CFQIdIRUiHOIUgRRhDGEMIQwhDCEMIQwhDCEMIQwhDCEMQQyhFOIUwRUCHWIdYRWBHaEWIx4iHiMeRB4kFiMeAxYkHiMdoRVCFQEdIhUCFUEdIRVhFUEdQh0iHSEdQh0iHOIUoRRhDEEMIQwhDCEMIQwgDCEMIQwhDCEMYQzBFMIVAhUhHWIdgR2hFaAeAx5EFiMeRBZFHiQWRR5FHgIdoRVBHSIdAhUhHUIdYRVhHUIVQR0iFSIdQR1BHOIUohRBDGEUIQQhDCEMQQwhDCEMQQwhDCEMoRTCFQEVIhVCHYEdgh2CHaAeAx5EHiMeZRZlHkUeZhZFFgQVwB1iFSEdAh1CFUEdoRViHWEdQR1BHSIdYRUiFQIcohRhDEIUIAwhDCEMQQxBDGEUYQxBDGEUwhTiFSEdQh1BHYIdgR2BFcEeAhZlHkUWZRaHHmUWZhZGFiQd4B1iFUEdQh1iFUIdoB2hFUIdQR1CHUEdYRUiHQIcohRhDEEUQQwhBCEEgRSBFKIUoRRhFKIVAh0BHUIdYh1iFWIdgR2BFeAeJB5lFmUWhx6HFoYehh5mFiQd4R2BHWIVYR2BHYEdwRWhFUEdIRVCHUEdQhUiHQIUwRSCFIIUQQwhDEEMwhThHOIUwhShFQIVIR0iHWIVgR1hHYIdoR2AFgEeJB5mFmUWpxaIFqcWhxaHFkQeAx3AHYIVgR2hFcAd4R2BFUEdQh1BHWEVYh0hHQIcwhSBFKIUgRRBDIIU4RUiHSEdARTiFSIdYh1BFWEdoR2BHYEdoR3hHgIeRR6FFoYWiBaIFqgWiBanFmYWJB3hHaAdoB3BFgIdwBWCHUEVQR1BFWIdYRUiHQEU4hRBDOIUwRxhFKIVAR1CFUEdIh0iHWIdgRVhHYEdoRWhHYEdoBXhHiMWRRaGHocOqBbIFqkWpxaoFocWZR4DHcAdwB4jHgIdoBVhHWIVQh1BHYEVQh1CFQEc4hSBFOIU4hyhFMEVAh1hHWIVgR1hHaEdgR2BHaEdwR3AFaEdwB3iHkQWRhaGFqgOyBbJDqkOqBaoFocWhxZEHgMeAx4kFeElwBWBHWIdQR1BFWEdYRUiHSIdIhyBFQIdARTiFKEVIhWBHaEdoR2hFcAdwB2gFcAdwR3AHcAVwB4kHmUWhh5nFsgWqA7KDuoOqBapDsgWhxZmHiQWZR5DHeEdoBWCHYEdQhVBHYEdQh0hHSIVARzCFUEVQRUCHKEVAhWhHcAd4B3gHgEd4h3hHcAd4R3gHeAWASZlFmYehhaHFqgOyg7JDuoOyg7JFskWqA5mFkYWZhZEHeAdwR2BHYEdQRViHYEdIRUiHSIdAhThHUIVYR1BHKIVAR3BHeEWAx4jHiQWIx4DHgIeAhYBHgIWIx6GHmcWhxaHFskOyQ7qDuoGyg7JFskOyRaIFocWhhYkFeEd4B2gHWIdYRViHWEdQhUiHUEc4hUiHUEVYRWBHMIVIh3AHgMeJR5lFkUWZR5FHiMeJB4kHiQeRB6IFoYWpxaIFskOyg7rDuoG6g7JDuoOyQ6oFqgWhhYlHgId4R2hHWEdYRWBHWIVIh1CHSIdAhVBHWEVYR2hHMIVIR3hHiQeZhaGHocehxZmFmUWRR5FFkUeZhanDocWqBaoFskOyg8LBuoGyg7qDusO6gapFqgOhxZFFiMl4RXAHWEdgh1hHUEVIh0hFSIdIh2BHUEVYh3AFMIVYR3hHkUeZh6oFqgOqBaHFmYWhhaHFocWhhanFqgWiBaoFuoW6gbsBuoG6gbqDusPCwbqDqkWiBZFFiMeAh2hFaEdgRVhHUEdAhUCFQIdQh2BHYEdgRXBHOIdgRXiHkUehxaoFqkOyRaoDqcWhx6oFqgWqBaoDqgWhxbIFsoO6wcMBusG6w7rBusPCwbLDskOqBZlHkUeAhXgHcEdYR1BHQIdAhUhHOIVQRWgHcEdgR2hHQIdgRYDHkUWhx7IFsoO6g7KDsgWqQ6oFskOyRaoDqgWiBbIFsoPCwcsBuwG6wbrBwsHDAbrBuoOyRZnFkUeIxYBFcAdgR0CHOIVAhziFOEVYRXBHgIdgR2hHQIdoR4DFkUehxbJFuoO7AbqBukOyg7JDusOyAbKFqcWiBbJDuoHDA8NBwwG6wcMBuwHLAbsBwsOyg6nFmYWJB4jHeEdYRziHOIU4RTCFMEVYh3AFgMdwR2hHSIVoR4DHmYWqB6oFusHDAcLBusG6gbrBwsGyQ7JDqkOqBbJFuwHDAcNBwwHDAcMBw0HDAcNBwwG6wbIFoceZRZEHeEdIhTiHMEUohSBDMIVYR3BFiMV4h3BHUEdoR4kHkYWpxbKFusHLgcMBwwHCwbsBwwGyQ7qDqgOyQ7KDwwHDQcNBw0HLQcNBw0HDQcNBy0O7AbJDqcWhxZFHeAdIhTiHMIUoRRBDMEVYhWgHiQWAx3iFWEVwR4kHmceqA7qFw0HDg8OBw0G7AcMBwwGyg7qBqgWyg7qDwwHLg8uBwwHDQcuDy4HDg8OBy4G7AbqBqgOpx5FHeEdQhzhFMIUIAwBDMEVQRWhHgMWJB4jHYEd4h5FHogWqRbqDw0HLwcvBw4HLQcMDwwG6wbKDskO6wbrDw0HDgctBw4HDQcvBy8HLgcuBw0HDQbqDqgOpxYlHeAdYhzhFKIUIAwhDGENIRWBHeIWJCYlFcEd4h5GHogO6hbrBw4HMAcvBw8HDgctBwwG7AbrDukO7AcLBwwHLgcuBw4HDg8wBzAPLwcvBw0HDAbqBskOZxZEHcAVgh0BHEEEIQwhDEEVAhWhFcEeRR5mFeId4x5mFqkWyg8MDy4HMQcwBzAHLgcNBw0HDAbqBsoPDQbrBwwHLwcvBw8HLwcwBzAHMAcvDw0HLAbrBqkWhxYkFcAdoRUCHCEMAQxBDEEMwRWhFaAWZhaHHeMeBCZGHskO6w8MBy8HMQcxB1AHUAcODw0HDAbrBusHDQ8MBwwHLwcvBzAHLwcxB1AHMAcvBw4HLA7rBskWZxYlHcAVYRUhHEEMIQxBDEEUoRWhFcAmiBaoFgQeBBZGHqgW6wcuDzAHMQ9RDzEHMAcuBw4HDQbrBusHLQ7sBy0HLwcwBzAHMAdSDzEHUQcvBy4PDQbqBqkWZRYEHcEVQR0iFGEUIQxBDGEUog2hHcAeZxbJDgMeJR5GHogXDAcPDzAHUg9SF1EHUAcPBy8G7QbsBwwHDAcNBw0HMAcwB1EHUQcyD1IPUg8wBy4HDAbrBqgWJR4DFYEdQRViHKEUYgxhFIIUoRWBHeEeZx7rBgMeJh5GHqgXDQcPB1EPUhdTJ1IPMAcwBy4HDwcMBwwHDAcNBwwHMAcwB1EPUg9TF1IXUxcwDy8HDAbLBqgWJR3hFSIdYRVhHQIUwhSiFIEU4hXAHgQeZhbLDeMWRR5nHqgXDQdQD1IXUyd0L1EXMAcwBy4HDwcNBw0G7AbrBy0HLwdRB1EPcyczH1Mncx8xBzAPDQbKDocWJRWhHQIVgR2BFWIdIhTiHMEVIhXBHgQehx7rBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';
// Exact port of opensmash/pixel_font.py's portrait-caption alphabet. The rows
// were transcribed from the vanilla tile dumps; every label is composed from
// these same native pixels, so arbitrary names use the identical face, outline,
// tracking, fitting, and browser-capture path as the original roster names.
const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const CAPTION_CHARS = /[^A-Z. ]/g;
const RANDOM_NAME_POOL = Object.freeze([
  'ALEX', 'AMIR', 'ANNA', 'ARIA', 'ASH', 'AVA', 'BEAU', 'BEN',
  'BLAKE', 'CARA', 'CHLOE', 'COLE', 'DARA', 'DEV', 'ELI', 'ELLA',
  'EMMA', 'EVAN', 'FINN', 'FREYA', 'GABE', 'GRACE', 'HANA', 'HUGO',
  'IAN', 'IRIS', 'IVAN', 'JADE', 'JAMES', 'JAX', 'JOEL', 'JUNE',
  'KAI', 'KIRA', 'LEAH', 'LEO', 'LIAM', 'LILA', 'LUCA', 'MARA',
  'MAYA', 'MILO', 'MINA', 'NASH', 'NIA', 'NICO', 'NOAH', 'NORA',
  'OMAR', 'OPAL', 'OWEN', 'RAFA', 'REMI', 'RHEA', 'RILEY', 'ROSE',
  'SAM', 'SANA', 'SASHA', 'THEO', 'UMA', 'VERA', 'WILL', 'ZARA'
]);
const VANILLA_ROSTER = Object.freeze([
  { asset: 'mario', portrait: 'mario', label: 'MARIO', name: 'Mario' },
  { asset: 'fox', portrait: 'fox', label: 'FOX', name: 'Fox' },
  { asset: 'dk', portrait: 'dk', label: 'DK', name: 'Donkey Kong' },
  { asset: 'samus', portrait: 'samus', label: 'SAMUS', name: 'Samus' },
  { asset: 'luigi', portrait: 'luigi', label: 'LUIGI', name: 'Luigi' },
  { asset: 'link', portrait: 'link', label: 'LINK', name: 'Link' },
  { asset: 'yoshi', portrait: 'yoshi', label: 'YOSHI', name: 'Yoshi' },
  { asset: 'captain', portrait: 'falcon', label: 'C.FALCON', name: 'Captain Falcon' },
  { asset: 'kirby', portrait: 'kirby', label: 'KIRBY', name: 'Kirby' },
  { asset: 'pikachu', portrait: 'pikachu', label: 'PIKACHU', name: 'Pikachu' },
  { asset: 'purin', portrait: 'jigglypuff', label: 'JIGGLYPUFF', name: 'Jigglypuff' },
  { asset: 'ness', portrait: 'ness', label: 'NESS', name: 'Ness' }
]);
const ACTION_PORTRAITS = Object.freeze({
  search: 'action-search',
  create: 'action-create'
});
const APP_BRIDGE = window.openSmashReactBridge;
function liveRosterCharacter(character) {
  return {
    asset: character.slug,
    portrait: `live:${character.slug}`,
    portraitUrl: character.portrait,
    label: character.short || character.name,
    name: character.name,
    source: character.generated ? 'generated' : 'live',
    fkind: character.fkind,
    bundle: character.bundle,
  };
}
const LIVE_ROSTER = Object.freeze((APP_BRIDGE?.characters || []).map(liveRosterCharacter));
const INITIAL_FIGHTER_JOBS = APP_BRIDGE?.fighterJobs || [];
const BAKED_CAPTION_PORTRAITS = new Set(
  VANILLA_ROSTER.map(character => character.portrait)
);
// React supplies the manifest-backed roster. If it has not mounted yet the
// grid starts empty and syncCharacters fills it without a second roster source.
const ROSTER = Object.freeze([...new Map(
  LIVE_ROSTER.map(character => [character.asset, character])
).values()]);
const CELL_COUNT = ROSTER.length + 2;
const CELL_IDS = Object.freeze(Array.from(
  { length: CELL_COUNT }, (_, index) => `CELL-${String(index + 1).padStart(3, '0')}`
));

function rosterCharacterForIndex(index) {
  return ROSTER[index];
}
// RGB samples from the supplied screenshot after resolving it to the native
// 96x92 grid. Only the six vertical and six horizontal 2px rule lanes are
// stored; portrait and fire pixels are not present in this border program.
const SCREENSHOT_BORDER_RGB = 'Ni4oOS8nOS0mNiojNSojLyMdKh8YKh8YKx8YKx8YLCAZLiMcMCUeNiskOy8oQTUuQjUuQjUuQjUuQjQuPjErOy4nNyskNiojOi0mOi4nOCskOCokNighNCcgLiIbMiYfNiojNiojNiojNiojNiojNiojNiojNiojNiojNyskOS0nOS0mNSkjMiYfMSYeLCAZMCQcLSEaKh8YKx8YMCUeNCkiNiojNiojNiojNiojNSojNSojNiojNiojNyskPTAqQjUuQjUuQDMsOi0mNyojNiojNiojNikiLB8ZLB8YLR8YLR8YLB8YLyIbLyMcMyghOCwmPjMsQTUuQTUuQTUuQTUuPzMtOzApOCwlNSojNyskOS0nOCwlNSojNyskNyskPC8mUj8yPS4kIBkUHxgTHhcTHxcTIxkUKBkWKRsXKRoXJhkUJhkUJxkWKhsVLxwXNxwZORsbPx0bPhsbPxsbPhwaOxsZNxwZNBsYNh0ZPx8bSiIfSiIeQyAcOR0YLx0XKBoXKBoVJxkXKRkXLBkXLxkXLRoXKxkWKBkWKBoWJxkUKBkXJhkWIhoTIhkSPS0iVkEzMSUdHxgTHxgTHhcTIBgTJBkVKBoVKRoXKBoWJhkTJhkUKBkWKhsVMhwZOBwZPBwbQR0cQRscQxscQxsbQRsaPBsaOhwZQBwaRxscSxwdSx0dSBwbPxwZMBsXJxkWJxkVJxkXKhkXLRkXLhoXLBoXKhkWKBkXKBoVJxkVKBkXJRkWIhoSJRsURzQpUDwwOS0lTDovNSceSDcsQTAmOSwkOi0mTDouNSceRjYrQTAmOCsjOS0lTDouNSceRjYrQTAmOCsjOi0lTDouNSceRjYrQTAmOCsjOS0lTDouNSceRjYrQTAmOCsjOi4lTDouNSceRjYrQTAmOCsjOS0lTDouNSceRjYrQTAmOCsjOSwkTDouNSceRjYrQTAmOCsjNysjTDouNSYeRjYrQTAmOCojOCsjTDouNSYeRjYrQTAmOCsjOS0lTDouNSceRjYrQTAmOCsjOSwlTDouNSceRjYrQTAmOCsjOSwlTDouNSceRjYrQTAmOCsjOSwkTDouNSceRjYrQTAmOCsjOS0mTDouNSceRjYrQTAmOiwjPDAnTDouNiceRzYrQTAmOy0kPTAoTDouNiceRzYrQTAmOy0kPi8oTDouNygfSDcsQTAmPS4lQTEqTTovOCggTzwwQjAmRTUrQy8qTjovPSwjV0AzQjAnbFlNRi8qUDovPCohXEI1RDAmc19RSC8oUDowQSsiXUM0RTEnaVVGTC8pUTowQyshXEI0RTEnY09AUC4rUTowQishXEM0RTEnX0s8Uy8rUjowQyohXEM0RjEnSzgtUy4qUzowQCohXUM0RzEnQzAoVC4pUzowPSkhXUM1RzAnQy8nVzArUzowPSkhXUM0RzEnRC8nVi8rUzowQCwkXUM0RzEnRS8nVS4qUzowRTEoXUM0RzEnRi8nVy8rUzowQCsjXkM1RzEnRi8nWTAsVDowPykhYEQ1RzEnRi8nWzErVDswQSkhYEQ1SDEnRy4nXTMrVTswRCohXkM1SDEnRy4nYTcsVjwwRywiXkM1STInSS8nYzsrVzwwSC0hX0Q1STMnSi8nZj0sWD0xSi4hX0M1SjMnSzAoaUEtWT4xSzAiXkM1SzQnSjEoa0MsWj4xTDAhXUQ1SzQnSjEoakMrWz8wTDEhXUQ2SzUnRzEnbEUqW0AwTTIgXUQ2SzUnRDIobEUrW0AwTDIhXkQ2SzUnQjEna0YtW0AwTDQmXUM1TDgqQTIoY0UuWkIxVDgsVzorWTwsXEAsXEMtV0Q8UUJCVD47YkAzakIwa0Iwa0EwaUIzZ0s8aFNEaVRGZ1FDYEs+WUQ3VkE1WUQ3WEM2VUA0VD8yUz4xUz0yUT0xTjoxSjczSjcwUTksUjgrUDYrTTMrTTQrTjMrTzQrTjQrTDMrSjQrSzMqTjQrUzUqVjkrVzwuUz4xWkM1YkQ2Y0U3ZEU4ZkY4ZkY4ZUY3ZUY3ZEU3Y0U3X0M2Vj8zXkA1Z0U5akg7akk8aUo9aUs9a00+a00+aks8aEc6ZkU5Z0g7alBCbFZIalFCaE4/Zkw+Y0o+YUo9Zkw+ak0/bE9Aa04/aks9ZUg6UTcuTTQrSzMrSjMqSzQqUDQrVDYrVjkrVT0vVD8yUD0wRjYqU0AyTjouPy4kPS0kPS0kPS0kPy4kQS4lQS8lQS4lQC4kQC4kQS4kQS8lQy4lRi8mRy4nSS8nSi4nSi8nSi8nSi4mSC8mRy4lSC8mSy8mTi4nTS4nTC8nSi4lRS8lQC4lQC4kQC4lQS4lQi4lQy4lQi4lQS4lQS4lQS4lQC4kQC4lQC4lPy4kPi4jSTUqVkE0SDYqPS0kPS0kPS0kPS0kQC4kQS8kQS4lQS4lQC4kQC4kQS4lQS8kRC4lRy8mRy4nSi8nSi4nSi8nSi4nSi4mRy4mRy8lSC4mTC4nTi4nTS8nTC8nSC4lRC4lQC4lQC4kQC4lQS4lQi4lQy4lQi4lQS4lQC4lQC4kQC4kQC4lQC4kPi4jPy4kTTktVUAyOy4mTz0wNygfTjsvQzInQzMpOi0mTDouNSceRjYrQTAmOCsjOy4mTDouNSceRjYrQTAmOCsjOi0lTDouNSceRjYrQTAmOCsjOS0kTDouNSceRjYrQTAmOCsjOi4lTDouNSceRjYrQTAmOCsjOy4nTDouNSceRjYrQTAmOCsjOi4lTDouNSceRjYrQTAmOCsjOS0lTDouNSceRjYrQTAmOCsjOi0mTDouNSYeRjYrQTAmOCsjOi0mTDouNSceRjYrQTAmOCsjOS0lTDouNSceRjYrQTAmOCsjOi4mTDouNSceRjYrQTAmOCsjOy8nTDouNSceRjYrQTAmOCsjOi0mTDouNSYeRjYrQTAmOCsjOS0lTDouNSYeRjYrQTAmOSsjOy4lTDouNScdRzYrQTAlOSsiOy4mTDouNSceRzYrQTAmOisjPi4oTTouNycfSDYsQjAmPSwkQS4oTTovOCcfUDwyQjAmQC0lQy4pTjovOScfXkdAQzAmQiwmRy4pUDovOycfYEhBRDAmQywmSzAqUDowPiggYUlCRTEnQy0mTi8qUTowPyghYUpCRTEnQy0lUS8qUjowQCggYUpCRjEnQy0mVDAsUjowQSghYUpCRjEnQy0mVTArUzowQighYEhBRjEnRC0nVi8pUzowQicgYUhCRzAnRS0mVi8rUzowQighYUlCRzEnRy0mVTAsUzowQighYElCRzEnSC0mVzAsUzowQighYEhBRzEnSS0mWC8rUzowQyghX0ZARzEnSi0nWjErVDowRCkhXkU/RzEnSy0nXTMrVTswRSkhXUQ+SDEnTC0oYDYtVjswRyshXEM9STInTi0nYTksVjwwRywiW0I8STInUC0oZDsrVzwwSS0hWkE7STMnUS4oaT8tWD4xSy8iWUA6SjQnUzAoakEsWj4xSzAhWD85SzQnVDIpa0MsWj8wTDAhVz85SzUnVTMobUYrWz8wTDEhVz44SzUnVjMobUUrW0AwTDIhVj44SzUnVjQobUYrW0AwTDIiVj43SzUoVjMoaEYuW0AwVzAkYjIhajsjdEcke1IlflsogGEtgWMvgWIvfl8qelcldVEjcU0ibUghZUIgYkEiZEkycWBTenBpe3Jrd25pc2tlbWVhZ2BcYFpVXFdSXFVRWVNPU05KTUdDR0E9Pjk1RTYxYzcufToufTouVyskQSEePSEeOiAePCEcRiEeUyUfXS8hXjYlTzotVj43VzA5WykjYSkiZyokbCwlbi0lcC0lci0mcy4mcy4mcy4mcS0mbiwlaCojYikgc0JIhFZrhlhuhlhuhlhuhVhuhFdtg1ZsgVVrf1NpfVFne09keExhdUpecUdbbURXakFTZT1OVzRAQiUkQSEeQyEeQyEePSAfOiAdPiEcSiIfVicgXjAiWjgnUDwwVDYrPi4jOCwkNSokNiokNiskNyskNywkNywkNywlNy0lMiggLCEaLiIbLCEZMyghOC4mPjQtOi8oNywmOC0oOC4pOC4pOC4oNy0oOzEsOC4pOjArNy4oNiwnNiwnNiwnNSwmNSsmNSsmNSslNyslOCslOCslNSolNSkkMygjLiMeKB0YKh4aNSkkOS4oNislNSslNismNiomNiolNyolNyolNyolNyolNyolNyolNyolNyolNyolNyolNyolNyolNiolOCwoOS0pOS0pOS0pOS0pOS0pOS0pOC0pOC0pOCwoOCwoOCwoNysnLiIeLiIeKyAcMSUhNiomPDEsOjAqNismNSkkNCkkNCkkNCkkNCkkNismOS0nNysmOS8oNSslNiol';

function fromBase64(s) {
  const raw = atob(s);
  return Uint8Array.from(raw, ch => ch.charCodeAt(0));
}

function decodeFire() {
  const src = fromBase64(FIRE_RGBA5551);
  const out = new Uint8ClampedArray(CELL_W * CELL_H * 4);
  for (let p = 0; p < CELL_W * CELL_H; p++) {
    const v = (src[p * 2] << 8) | src[p * 2 + 1];
    const r = (v >>> 11) & 31, g = (v >>> 6) & 31, b = (v >>> 1) & 31;
    const i = p * 4;
    out[i] = (r << 3) | (r >>> 2);
    out[i + 1] = (g << 3) | (g >>> 2);
    out[i + 2] = (b << 3) | (b >>> 2);
    out[i + 3] = (v & 1) ? 255 : 0;
  }
  return out;
}

const FIRE = decodeFire();

function put(dst, width, x, y, r, g, b, a = 255) {
  if (x < 0 || y < 0 || x >= width || y >= dst.length / 4 / width) return;
  const i = (y * width + x) * 4;
  if (a === 255) { dst[i] = r; dst[i + 1] = g; dst[i + 2] = b; dst[i + 3] = 255; return; }
  if (a === 0) return;
  const sourceAlpha = a / 255;
  const destinationAlpha = dst[i + 3] / 255;
  const outputAlpha = sourceAlpha + destinationAlpha * (1 - sourceAlpha);
  const destinationWeight = destinationAlpha * (1 - sourceAlpha);
  dst[i] = Math.round((r * sourceAlpha + dst[i] * destinationWeight) / outputAlpha);
  dst[i + 1] = Math.round((g * sourceAlpha + dst[i + 1] * destinationWeight) / outputAlpha);
  dst[i + 2] = Math.round((b * sourceAlpha + dst[i + 2] * destinationWeight) / outputAlpha);
  dst[i + 3] = Math.round(outputAlpha * 255);
}

function drawFire(dst) {
  for (let y = 0; y < CELL_H; y++) for (let x = 0; x < CELL_W; x++) {
    // Rows 0-1 are the texture's hot storage lip. The screenshot shows the
    // lattice covering that lip, so the first visible rows continue from 2-3.
    // The storage texture's final row is transparent; repeat row 41 so the
    // flame reaches the bottom rule instead of leaving a dark one-pixel gap.
    const fireY = y === CELL_H - 1 ? CELL_H - 2 : (y < 2 ? y + 2 : y);
    const s = (fireY * CELL_W + x) * 4;
    put(dst, CELL_W, x, y, FIRE[s], FIRE[s + 1], FIRE[s + 2], FIRE[s + 3]);
  }
}


const CAPTION_SOURCE_IMAGES = new Map();

async function loadCaptionImage(url) {
  if (!CAPTION_SOURCE_IMAGES.has(url)) {
    CAPTION_SOURCE_IMAGES.set(url, (async () => {
      const image = new Image();
      image.decoding = 'async';
      image.src = url;
      await image.decode();
      const canvas = document.createElement('canvas');
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      context.drawImage(image, 0, 0);
      return Object.freeze({
        width: canvas.width,
        height: canvas.height,
        pixels: context.getImageData(0, 0, canvas.width, canvas.height).data
      });
    })());
  }
  return CAPTION_SOURCE_IMAGES.get(url);
}


// One entry per letter (plus '.'), as RGBA tiles in cell coordinates: the
// glyph box (outline row, 7 face rows, outline row) sits at rows 2..10 like
// the baked captions, so existing consumers see the same geometry.
const CAPTION_GLYPHS = new Map([...ALPHABET, '.'].map(char => {
  const glyph = SSB_NAME_FONT.glyphs[char];
  const r = renderNameFontIA(char, { exact: false });
  const image = nameFontImageData(r);
  const top = SSB_NAME_FONT.faceRow - r.originY;
  const height = top + r.height;
  const pixels = new Uint8ClampedArray(r.width * height * 4);
  pixels.set(image.data, top * r.width * 4);
  return [char, Object.freeze({
    char, width: r.width, height, advance: glyph.faceW + SSB_NAME_FONT.defaultGap,
    originX: r.originX, pixels, extracted: !glyph.synth, synth: !!glyph.synth
  })];
}));

function cutOutPortrait(source, sourceLabel) {
  const bakedCaption = renderCaption(sourceLabel);
  const bakedCaptionRight = Math.min(CELL_W - 1, 4 + bakedCaption.width + 1);
  const bakedCaptionBottom = Math.min(CELL_H - 1, bakedCaption.height + 1);
  const pixels = new Uint8ClampedArray(CELL_W * CELL_H * 4);
  for (let y = 0; y < CELL_H; y++) for (let x = 0; x < CELL_W; x++) {
    const sourceIndex = (y * source.width + x) * 4;
    const targetIndex = (y * CELL_W + x) * 4;
    const r = source.pixels[sourceIndex];
    const g = source.pixels[sourceIndex + 1];
    const b = source.pixels[sourceIndex + 2];
    const a = source.pixels[sourceIndex + 3];
    // The decomp portrait sprite carries a one-texel frame of its own. Our
    // shared rule canvas supplies the grid border, so omit this baked ring to
    // avoid a doubled inset frame around every character.
    if (x === 0 || y === 0 || x === CELL_W - 1 || y === CELL_H - 1) continue;
    // These decomp tiles also contain the original roster name in their top
    // band. Clear its full ink box (including the antialiased fringe) before
    // our code-rendered caption is composited, otherwise two labels overlap.
    if (!USE_SOURCE_PORTRAIT_CAPTIONS
      && x >= 3 && x <= bakedCaptionRight && y <= bakedCaptionBottom) continue;
    // The source PNGs carry their own cutout alpha. Drop any residual black
    // matte in transparent edge samples without erasing dark costume/face ink.
    if (!a || (a < 128 && Math.max(r, g, b) < 24)) continue;
    pixels[targetIndex] = r;
    pixels[targetIndex + 1] = g;
    pixels[targetIndex + 2] = b;
    pixels[targetIndex + 3] = a;
  }
  return Object.freeze({ width: CELL_W, height: CELL_H, pixels });
}

// Portrait pixel data by portrait name. Populated from featured-fighter and
// live-roster PNGs only; vanilla names simply have no entry.
const CHARACTER_PORTRAITS = new Map();

async function loadFeaturedPortrait(portraitName, portraitUrl = null) {
  const image = new Image();
  image.decoding = 'async';
  image.src = portraitUrl || buildAssetUrl(`featured-fighters/${portraitName}.png`);
  await image.decode();

  const canvas = document.createElement('canvas');
  canvas.width = CELL_W;
  canvas.height = CELL_H;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  const sourceAspect = image.naturalWidth / image.naturalHeight;
  const targetAspect = CELL_W / CELL_H;
  let sourceX = 0;
  let sourceY = 0;
  let sourceWidth = image.naturalWidth;
  let sourceHeight = image.naturalHeight;

  if (sourceAspect > targetAspect) {
    sourceWidth = image.naturalHeight * targetAspect;
    sourceX = (image.naturalWidth - sourceWidth) / 2;
  } else {
    sourceHeight = image.naturalWidth / targetAspect;
    sourceY = (image.naturalHeight - sourceHeight) / 2;
  }

  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = 'high';
  context.drawImage(
    image,
    sourceX, sourceY, sourceWidth, sourceHeight,
    0, 0, CELL_W, CELL_H
  );
  return Object.freeze({
    width: CELL_W,
    height: CELL_H,
    pixels: context.getImageData(0, 0, CELL_W, CELL_H).data
  });
}

await Promise.all(FEATURED_ROSTER.map(async character => {
  CHARACTER_PORTRAITS.set(
    character.portrait,
    await loadFeaturedPortrait(character.portrait)
  );
}));

await Promise.all(Object.values(ACTION_PORTRAITS).map(async portraitName => {
  const portraitUrl = BUILD_ASSETS[`./assets/featured-fighters/${portraitName}.png`];
  if (!portraitUrl) return;
  CHARACTER_PORTRAITS.set(
    portraitName,
    await loadFeaturedPortrait(portraitName, portraitUrl)
  );
}));

await Promise.all(LIVE_ROSTER.map(async character => {
  try {
    CHARACTER_PORTRAITS.set(
      character.portrait,
      await loadFeaturedPortrait(character.portrait, character.portraitUrl)
    );
  } catch (error) {
    console.warn(`Could not load live portrait for ${character.name}:`, error);
  }
}));






function layoutCaption(text, tracking = 0) {
  const layout = layoutNameFont(text, { exact: false, tracking });
  if (!layout.glyphs.length) return { glyphs: [], width: 0, left: 0 };
  let left = Infinity, right = -Infinity;
  for (const { id, x } of layout.glyphs) {
    const glyph = SSB_NAME_FONT.glyphs[id];
    left = Math.min(left, x + glyph.ox);
    right = Math.max(right, x + glyph.ox + glyph.w);
  }
  // width measured from the first face origin (cell column 4) to the last
  // glyph's outline edge — the extent that has to fit inside the cell.
  return { glyphs: layout.glyphs, width: right, left };
}

function measureCaption(text, tracking = 0) {
  return layoutCaption(text, tracking).width;
}

function fitCaption(value, maxWidth = CELL_W - 5) {
  let text = String(value).toUpperCase().replace(CAPTION_CHARS, '').trim();
  for (const tracking of [0, -1]) {
    const width = measureCaption(text, tracking);
    if (width <= maxWidth) return Object.freeze({ text, tracking, width: Math.max(1, width) });
  }
  while (text && measureCaption(text, -1) > maxWidth) text = text.slice(0, -1).trim();
  return Object.freeze({ text, tracking: -1, width: Math.max(1, measureCaption(text, -1)) });
}



function renderCaption(value, maxWidth = CELL_W - 5) {
  const layout = fitCaption(value, maxWidth);
  const r = renderNameFontIA(layout.text, { exact: false, tracking: layout.tracking });
  // Cell-space bitmap: x=0 is the first face origin (cell column 4), y=0 the
  // cell's top row; the font's left outline margin lands at negative x and is
  // clipped by put(), matching how the baked tiles sit against the frame.
  const top = SSB_NAME_FONT.faceRow - r.originY;
  const height = Math.max(10, top + r.height);
  const pixels = new Uint8ClampedArray(Math.max(1, layout.width) * height * 4);
  if (r.width) {
    const image = nameFontImageData(r);
    for (let y = 0; y < r.height; y++) for (let x = 0; x < r.width; x++) {
      const source = (y * r.width + x) * 4;
      put(
        pixels, Math.max(1, layout.width), x - r.originX, y + top,
        image.data[source], image.data[source + 1], image.data[source + 2], image.data[source + 3]
      );
    }
  }
  return Object.freeze({ ...layout, height, pixels });
}

function drawLabel(dst, value, opacity = 1) {
  const caption = renderCaption(value);
  if (!caption.text) return;
  // The baked tile captions start their first face column at x=4, y=3.
  const originX = 4;
  const originY = 0;
  for (let y = 0; y < caption.height; y++) for (let x = 0; x < caption.width; x++) {
    const source = (y * caption.width + x) * 4;
    put(
      dst, CELL_W, originX + x, originY + y,
      caption.pixels[source], caption.pixels[source + 1],
      caption.pixels[source + 2], Math.round(caption.pixels[source + 3] * opacity)
    );
  }
}

function decodeReferenceRules() {
  const sourceWidth = 96;
  const sourceHeight = 92;
  const dst = new Uint8ClampedArray(sourceWidth * sourceHeight * 4);
  const border = fromBase64(SCREENSHOT_BORDER_RGB);
  let p = 0;
  for (let y = 0; y < sourceHeight; y++) for (let x = 0; x < sourceWidth; x++) {
    const xr = x < 2 || (x >= 47 && x < 49) || x >= 94;
    const yr = y < 2 || (y >= 45 && y < 47) || y >= 90;
    if (!xr && !yr) continue;
    put(dst, sourceWidth, x, y, border[p++], border[p++], border[p++]);
  }
  return dst;
}

function mapRuleSample(position, extent, cellSize, sourceExtent) {
  const stride = cellSize + RULE;
  if (position < RULE) return position;
  if (position >= extent - RULE) {
    return sourceExtent - RULE + position - (extent - RULE);
  }
  const local = position % stride;
  if (local < RULE) return stride + local;
  const tile = Math.floor(position / stride);
  return (tile & 1) ? stride + local : local;
}

// Repeat the calibrated 2x2 rule lattice across the larger board. Every
// boundary remains real code geometry, but its pixels come from the sampled
// frame treatment instead of a flat CSS color.
function renderRules(gridWidth, gridHeight, columns, cellCount) {
  const sourceWidth = 96;
  const sourceHeight = 92;
  const reference = decodeReferenceRules();
  const dst = new Uint8ClampedArray(gridWidth * gridHeight * 4);
  const xStride = CELL_W + RULE;
  const yStride = CELL_H + RULE;
  const ruleMask = new Uint8Array(gridWidth * gridHeight);

  for (let index = 0; index < cellCount; index++) {
    const left = (index % columns) * xStride;
    const top = Math.floor(index / columns) * yStride;
    const right = left + CELL_W + RULE * 2;
    const bottom = top + CELL_H + RULE * 2;
    for (let y = top; y < bottom; y++) for (let x = left; x < right; x++) {
      if (x < left + RULE || x >= right - RULE ||
          y < top + RULE || y >= bottom - RULE) {
        ruleMask[y * gridWidth + x] = 1;
      }
    }
  }

  for (let y = 0; y < gridHeight; y++) for (let x = 0; x < gridWidth; x++) {
    if (!ruleMask[y * gridWidth + x]) continue;
    const sourceX = mapRuleSample(x, gridWidth, CELL_W, sourceWidth);
    const sourceY = mapRuleSample(y, gridHeight, CELL_H, sourceHeight);
    const source = (sourceY * sourceWidth + sourceX) * 4;
    put(
      dst, gridWidth, x, y,
      reference[source], reference[source + 1], reference[source + 2], reference[source + 3]
    );
  }
  return dst;
}

// Wrap non-grid media in the very same sampled roster rule. The transparent
// center lets the media show through while the two native edge pixels retain
// the game's irregular, texture-derived color instead of becoming a flat CSS
// border.
function renderOuterRules(frameWidth, frameHeight) {
  const sourceWidth = 96;
  const sourceHeight = 92;
  const reference = decodeReferenceRules();
  const dst = new Uint8ClampedArray(frameWidth * frameHeight * 4);
  for (let y = 0; y < frameHeight; y++) for (let x = 0; x < frameWidth; x++) {
    const xr = x < RULE || x >= frameWidth - RULE;
    const yr = y < RULE || y >= frameHeight - RULE;
    if (!xr && !yr) continue;
    const sourceX = mapRuleSample(x, frameWidth, CELL_W, sourceWidth);
    const sourceY = mapRuleSample(y, frameHeight, CELL_H, sourceHeight);
    const source = (sourceY * sourceWidth + sourceX) * 4;
    put(
      dst, frameWidth, x, y,
      reference[source], reference[source + 1], reference[source + 2], reference[source + 3]
    );
  }
  return dst;
}

function sharedPanelRuleSample(position, extent, segments, internalStart, sourceExtent) {
  if (position < RULE) return position;
  if (position >= extent - RULE) {
    return sourceExtent - RULE + position - (extent - RULE);
  }
  for (let segment = 1; segment < segments; segment++) {
    const laneStart = Math.round(extent * segment / segments) - Math.floor(RULE / 2);
    if (position >= laneStart && position < laneStart + RULE) {
      return internalStart + position - laneStart;
    }
  }
  return null;
}

// The bridge has oversized cells, but its rule is rasterized at the roster's
// native display scale. That keeps the shared video/bridge/roster boundary the
// same visible thickness instead of magnifying a two-pixel rule with each cell.
function renderSharedPanelRules(frameWidth, frameHeight, columns, rows) {
  const sourceWidth = 96;
  const sourceHeight = 92;
  const reference = decodeReferenceRules();
  const dst = new Uint8ClampedArray(frameWidth * frameHeight * 4);
  for (let y = 0; y < frameHeight; y++) for (let x = 0; x < frameWidth; x++) {
    const sourceRuleX = sharedPanelRuleSample(
      x, frameWidth, columns, CELL_W + RULE, sourceWidth
    );
    const sourceRuleY = sharedPanelRuleSample(
      y, frameHeight, rows, CELL_H + RULE, sourceHeight
    );
    if (sourceRuleX == null && sourceRuleY == null) continue;
    const sourceX = sourceRuleX ?? mapRuleSample(x, frameWidth, CELL_W, sourceWidth);
    const sourceY = sourceRuleY ?? mapRuleSample(y, frameHeight, CELL_H, sourceHeight);
    const source = (sourceY * sourceWidth + sourceX) * 4;
    put(
      dst, frameWidth, x, y,
      reference[source], reference[source + 1], reference[source + 2], reference[source + 3]
    );
  }
  return dst;
}

function renderCellBackground() {
  const dst = new Uint8ClampedArray(CELL_W * CELL_H * 4);
  for (let i = 0; i < dst.length; i += 4) { dst[i] = 8; dst[i + 1] = 5; dst[i + 2] = 4; dst[i + 3] = 255; }
  drawFire(dst);
  return dst;
}

function seededRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state += 0x6D2B79F5;
    let value = state;
    value = Math.imul(value ^ value >>> 15, value | 1);
    value ^= value + Math.imul(value ^ value >>> 7, value | 61);
    return ((value ^ value >>> 14) >>> 0) / 4294967296;
  };
}

function renderActionCellBackground(seed) {
  const random = seededRandom(seed);
  const dst = new Uint8ClampedArray(CELL_W * CELL_H * 4);

  for (let y = 0; y < CELL_H; y++) for (let x = 0; x < CELL_W; x++) {
    const grain = random();
    const tone = grain < 0.08
      ? 3 + Math.floor(random() * 2)
      : grain > 0.92
        ? 14 + Math.floor(random() * 10)
        : 6 + Math.floor(random() * 5);
    const target = (y * CELL_W + x) * 4;
    dst[target] = tone;
    dst[target + 1] = Math.max(0, tone - 1);
    dst[target + 2] = Math.max(0, tone - 2);
    dst[target + 3] = 255;
  }

  return dst;
}

const ACTION_CELL_BACKGROUND_PIXELS = Object.freeze({
  search: renderActionCellBackground(STONE_BACKGROUND_SEED),
  create: renderActionCellBackground(STONE_BACKGROUND_SEED ^ 0x9E3779B9)
});

function scalePixels2x(pixels, width, height, smooth) {
  const scaledWidth = width * 2;
  const scaledHeight = height * 2;
  const scaled = new Uint8ClampedArray(scaledWidth * scaledHeight * 4);
  for (let y = 0; y < scaledHeight; y++) for (let x = 0; x < scaledWidth; x++) {
    const sourceX = x >> 1;
    const sourceY = y >> 1;
    const target = (y * scaledWidth + x) * 4;
    if (!smooth) {
      const source = (sourceY * width + sourceX) * 4;
      scaled.set(pixels.subarray(source, source + 4), target);
      continue;
    }
    const nextX = Math.min(width - 1, sourceX + 1);
    const nextY = Math.min(height - 1, sourceY + 1);
    const fx = (x & 1) * 0.5;
    const fy = (y & 1) * 0.5;
    const samples = [
      [sourceX, sourceY, (1 - fx) * (1 - fy)],
      [nextX, sourceY, fx * (1 - fy)],
      [sourceX, nextY, (1 - fx) * fy],
      [nextX, nextY, fx * fy]
    ];
    let alpha = 0;
    const premultiplied = [0, 0, 0];
    for (const [sampleX, sampleY, weight] of samples) {
      if (!weight) continue;
      const source = (sampleY * width + sampleX) * 4;
      const sampleAlpha = pixels[source + 3] / 255;
      alpha += sampleAlpha * weight;
      for (let channel = 0; channel < 3; channel++) {
        premultiplied[channel] += pixels[source + channel] * sampleAlpha * weight;
      }
    }
    if (alpha > 0) {
      for (let channel = 0; channel < 3; channel++) {
        scaled[target + channel] = Math.round(premultiplied[channel] / alpha);
      }
      scaled[target + 3] = Math.round(alpha * 255);
    }
  }
  return Object.freeze({ width: scaledWidth, height: scaledHeight, pixels: scaled });
}

function blendPixelFrames(nearest, smooth, mix) {
  const pixels = new Uint8ClampedArray(nearest.pixels.length);
  for (let index = 0; index < pixels.length; index += 4) {
    const nearestAlpha = nearest.pixels[index + 3] / 255;
    const smoothAlpha = smooth.pixels[index + 3] / 255;
    const alpha = nearestAlpha * (1 - mix) + smoothAlpha * mix;
    if (alpha > 0) for (let channel = 0; channel < 3; channel++) {
      pixels[index + channel] = Math.round((
        nearest.pixels[index + channel] * nearestAlpha * (1 - mix) +
        smooth.pixels[index + channel] * smoothAlpha * mix
      ) / alpha);
    }
    pixels[index + 3] = Math.round(alpha * 255);
  }
  return Object.freeze({ width: nearest.width, height: nearest.height, pixels });
}

function compositePortrait(dst, portraitName) {
  const portrait = CHARACTER_PORTRAITS.get(portraitName);
  if (!portrait) return;
  for (let y = 0; y < CELL_H; y++) for (let x = 0; x < CELL_W; x++) {
    const source = (y * CELL_W + x) * 4;
    put(
      dst, CELL_W, x, y,
      portrait.pixels[source], portrait.pixels[source + 1],
      portrait.pixels[source + 2], portrait.pixels[source + 3]
    );
  }
}

function renderCellFramebuffer(
  name,
  portraitName = null,
  labelOpacity = 1,
  backgroundPixels = null
) {
  const native = backgroundPixels
    ? new Uint8ClampedArray(backgroundPixels)
    : renderCellBackground();
  compositePortrait(native, portraitName);
  const background = scalePixels2x(native, CELL_W, CELL_H, false);
  if (!name || (portraitName && USE_SOURCE_PORTRAIT_CAPTIONS &&
    BAKED_CAPTION_PORTRAITS.has(portraitName))) return background;
  const nativeLabel = new Uint8ClampedArray(CELL_W * CELL_H * 4);
  drawLabel(nativeLabel, name, labelOpacity);
  const nearestLabel = scalePixels2x(nativeLabel, CELL_W, CELL_H, false);
  const smoothLabel = scalePixels2x(nativeLabel, CELL_W, CELL_H, true);
  const label = blendPixelFrames(nearestLabel, smoothLabel, LABEL_SMOOTH_MIX);
  for (let y = 0; y < label.height; y++) for (let x = 0; x < label.width; x++) {
    const source = (y * label.width + x) * 4;
    put(
      background.pixels, background.width, x, y,
      label.pixels[source], label.pixels[source + 1],
      label.pixels[source + 2], label.pixels[source + 3]
    );
  }
  return background;
}

function paintPixels(
  target, pixels, width, height, displayScale = 1,
  pixelStep = 1, stepMix = 1, captureRect = null
) {
  const source = document.createElement('canvas');
  source.width = width;
  source.height = height;
  source.getContext('2d').putImageData(new ImageData(pixels, width, height), 0, 0);

  let renderSource = source;
  if (pixelStep > 1) {
    const stepped = document.createElement('canvas');
    stepped.width = width * pixelStep;
    stepped.height = height * pixelStep;
    const steppedCtx = stepped.getContext('2d');
    steppedCtx.imageSmoothingEnabled = false;
    steppedCtx.drawImage(source, 0, 0, stepped.width, stepped.height);
    renderSource = stepped;
  }

  const scaleX = typeof displayScale === 'number' ? displayScale : displayScale.x;
  const scaleY = typeof displayScale === 'number' ? displayScale : displayScale.y;
  const canvas = typeof target.getContext === 'function'
    ? target
    : document.createElement('canvas');
  canvas.width = Math.round(width * scaleX);
  canvas.height = Math.round(height * scaleY);
  const ctx = canvas.getContext('2d', {
    willReadFrequently: scaleX === 1 && scaleY === 1
  });
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (displayScale === 1 && !captureRect) {
    ctx.putImageData(new ImageData(pixels, width, height), 0, 0);
  } else {
    const target = captureRect || { x: 0, y: 0, width: 1, height: 1 };
    const dx = target.x * canvas.width;
    const dy = target.y * canvas.height;
    const dw = target.width * canvas.width;
    const dh = target.height * canvas.height;
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'low';
    if (pixelStep > 1 && stepMix < 1) {
      ctx.drawImage(source, dx, dy, dw, dh);
      ctx.globalAlpha = stepMix;
    }
    // Match the captured game texture path: magnify the 2x texture lattice
    // without interpolation, then let the browser's final CSS reduction
    // supply the single antialiasing pass visible in the screenshot.
    if (pixelStep > 1) ctx.imageSmoothingEnabled = false;
    ctx.drawImage(renderSource, dx, dy, dw, dh);
    ctx.globalAlpha = 1;
  }
  if (canvas !== target) target.src = canvas.toDataURL('image/png');
}

function canvasFromPixels(
  pixels, width, height, className = '', displayScale = 1,
  pixelStep = 1, stepMix = 1, captureRect = null
) {
  const canvas = document.createElement('canvas');
  canvas.className = className;
  canvas.setAttribute('aria-hidden', 'true');
  paintPixels(canvas, pixels, width, height, displayScale, pixelStep, stepMix, captureRect);
  return canvas;
}

function paintCellCanvas(
  canvas,
  label,
  portraitName,
  labelOpacity = 1,
  backgroundPixels = null
) {
  const framebuffer = renderCellFramebuffer(
    label, portraitName, labelOpacity, backgroundPixels
  );
  paintPixels(
    canvas, framebuffer.pixels, framebuffer.width, framebuffer.height
  );
}

const grid = document.getElementById('replica-grid');
const arenaShell = document.querySelector('.arena-shell');
const arenaSurface = grid.closest('.arena-surface');
const introVideoFrame = document.querySelector('.intro-video-frame');
const introVideoRuleCanvas = document.querySelector('.intro-video-rule-layer');
const siteMenuBridge = document.getElementById('site-menu-bridge');
const siteMenuRuleCanvas = document.querySelector('.site-menu-rule-layer');
const cells = new Map();
const jobCells = new Map();

const advancedFrameCells = [...document.querySelectorAll('.advanced-cell-frame')];
const advancedFrameCanvases = new Map(advancedFrameCells.map(cell => {
  const canvas = document.createElement('canvas');
  canvas.className = 'advanced-cell-rule-layer';
  canvas.setAttribute('aria-hidden', 'true');
  cell.append(canvas);
  return [cell, canvas];
}));

function paintAdvancedFrame(cell) {
  const canvas = advancedFrameCanvases.get(cell);
  const width = Math.round(cell.getBoundingClientRect().width);
  const height = Math.round(cell.getBoundingClientRect().height);
  if (!canvas || width < RULE * 2 + 1 || height < RULE * 2 + 1) return;
  const signature = `${width}x${height}`;
  if (canvas.dataset.signature === signature) return;
  canvas.dataset.signature = signature;
  paintPixels(canvas, renderOuterRules(width, height), width, height);
}

if ('ResizeObserver' in window) {
  const advancedFrameObserver = new ResizeObserver(entries => {
    entries.forEach(entry => paintAdvancedFrame(entry.target));
  });
  advancedFrameCells.forEach(cell => advancedFrameObserver.observe(cell));
} else {
  advancedFrameCells.forEach(paintAdvancedFrame);
  window.addEventListener('resize', () => advancedFrameCells.forEach(paintAdvancedFrame));
}

CELL_IDS.forEach((id, index) => {
  const isSearch = index === 0;
  const isCreate = index === 1;
  const character = isSearch
    ? { asset: 'search', portrait: ACTION_PORTRAITS.search, label: 'SEARCH', name: 'Search fighters' }
    : isCreate
      ? { asset: 'create', portrait: ACTION_PORTRAITS.create, label: 'CREATE', name: 'Create fighter' }
      : rosterCharacterForIndex(index - 2);
  const fkind = character.fkind ?? VANILLA_ROSTER.indexOf(character);
  const label = character.label;
  const button = document.createElement(isSearch ? 'label' : 'button');
  if (!isSearch) button.type = 'button';
  button.className = `replica-cell${isSearch ? ' is-search' : isCreate ? ' is-create' : ''}`;
  button.dataset.character = id;
  button.dataset.kind = isSearch ? 'search' : isCreate ? 'create' : 'fighter';
  button.dataset.label = label;
  button.dataset.rosterCharacter = character.asset;
  button.dataset.portrait = character.portrait;
  if (character.portraitUrl) button.dataset.portraitUrl = character.portraitUrl;
  button.dataset.displayName = character.name;
  button.dataset.fkind = String(fkind);
  if (character.bundle) button.dataset.bundle = character.bundle;
  button.setAttribute('role', 'gridcell');
  button.setAttribute('aria-label', character.name);
  // Create is a momentary action, not a toggle or selection-holding cell.
  if (!isSearch && !isCreate) button.setAttribute('aria-pressed', 'false');
  if (isSearch) {
    const caret = document.createElement('span');
    caret.className = 'replica-search-caret';
    caret.setAttribute('aria-hidden', 'true');
    button.append(caret);

    const input = document.createElement('input');
    input.id = 'fighter-search';
    input.className = 'replica-search-input';
    input.type = 'search';
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.setAttribute('autocapitalize', 'characters');
    input.setAttribute('aria-label', 'Search fighters');
    button.append(input);
  }
  const framebuffer = renderCellFramebuffer(
    label,
    character.portrait,
    1,
    isSearch
      ? ACTION_CELL_BACKGROUND_PIXELS.search
      : isCreate
        ? ACTION_CELL_BACKGROUND_PIXELS.create
        : null
  );
  button.append(canvasFromPixels(
    framebuffer.pixels, framebuffer.width, framebuffer.height, 'replica-texture-layer'
  ));
  grid.append(button);
  cells.set(id, button);
});

const ruleCanvas = document.createElement('canvas');
ruleCanvas.className = 'replica-rule-layer';
ruleCanvas.setAttribute('aria-hidden', 'true');
grid.append(ruleCanvas);

let currentGridLayout;
let introVideoRuleSignature = '';
let siteMenuRuleSignature = '';

function paintIntroVideoRule() {
  if (!currentGridLayout || !introVideoFrame || !introVideoRuleCanvas) return;
  const frameRect = introVideoFrame.getBoundingClientRect();
  const gridWidth = grid.getBoundingClientRect().width || window.innerWidth;
  const rosterScale = gridWidth / currentGridLayout.width;
  const width = Math.max(RULE * 2 + 1, Math.round(frameRect.width / rosterScale));
  const height = Math.max(RULE * 2 + 1, Math.round(frameRect.height / rosterScale));
  const signature = `${width}x${height}`;
  if (signature === introVideoRuleSignature) return;
  introVideoRuleSignature = signature;
  paintPixels(
    introVideoRuleCanvas, renderOuterRules(width, height), width, height
  );
}

function sharedControlStripHeight(width) {
  const logicalWidth = RULE + CELL_W + RULE;
  const logicalHeight = RULE + CELL_H + RULE;
  return Math.max(
    RULE * 2 + 1,
    Math.round(width * logicalHeight / logicalWidth * FLAME_BRIDGE_HEIGHT_SCALE)
  );
}

function paintSiteMenuRule() {
  if (!currentGridLayout || !siteMenuBridge || !siteMenuRuleCanvas) return;
  const columns = 3;
  const rows = 1;
  const logicalWidth = RULE + CELL_W + RULE;
  const logicalHeight = RULE + CELL_H + RULE;
  const width = currentGridLayout.width;
  const height = sharedControlStripHeight(width);
  const signature = `${width}x${height}:${columns}x${rows}`;

  // This is the same physical row height as Search Fighters. With six roster
  // columns each menu cell spans two character units; with three, it spans one.
  siteMenuBridge.style.aspectRatio =
    `${logicalWidth} / ${logicalHeight * FLAME_BRIDGE_HEIGHT_SCALE}`;
  if (signature === siteMenuRuleSignature) return;
  siteMenuRuleSignature = signature;
  paintPixels(
    siteMenuRuleCanvas,
    renderSharedPanelRules(width, height, columns, rows),
    width,
    height
  );
}

function columnsForContainer() {
  // The arena is square and capped by viewport height, so using its rendered
  // width keeps wide laptop windows stuck at six columns. Break the roster by
  // page width instead; the cells still scale to the arena once laid out.
  return GRID_COLUMN_BREAKPOINTS.find(({ minWidth }) => window.innerWidth >= minWidth).columns;
}

function reserveRosterFootprint(layout) {
  const renderedWidth = arenaSurface.clientWidth || window.innerWidth;
  const reserveHeight = rosterReserveHeight(layout, renderedWidth);
  arenaShell.style.setProperty('--roster-layout-reserve', `${reserveHeight}px`);
}

function visibleCellsInDisplayOrder() {
  const visible = [...cells.values()].filter(button => !button.hidden);
  return [
    ...visible.filter(button => button.dataset.kind === 'search'),
    ...visible.filter(button => button.dataset.kind === 'create'),
    ...visible.filter(button => button.dataset.kind === 'job'),
    ...visible.filter(button => button.dataset.kind === 'creation'),
    ...visible.filter(button => button.dataset.kind === 'fighter'),
  ];
}

function applyGridLayout(columns = columnsForContainer()) {
  const visibleCells = visibleCellsInDisplayOrder();
  const visibleSignature = visibleCells.map(button => button.dataset.character).join(',');
  // Job cells arrive after the static roster. Keep the unfiltered footprint in
  // the cache key so a job sync cannot leave a filtered layout using a stale
  // reserve merely because none of the new cells match the current query.
  const reservedCellCount = cells.size;
  if (currentGridLayout?.columns === columns &&
      currentGridLayout.visibleSignature === visibleSignature &&
      currentGridLayout.reservedCellCount === reservedCellCount) {
    reserveRosterFootprint(currentGridLayout);
    return currentGridLayout;
  }

  const { rows, width, height } = rosterGridDimensions(visibleCells.length, columns, {
    cellWidth: CELL_W,
    cellHeight: CELL_H,
    rule: RULE,
  });
  const reservedLayout = rosterGridDimensions(reservedCellCount, columns, {
    cellWidth: CELL_W,
    cellHeight: CELL_H,
    rule: RULE,
  });
  const reservedRows = reservedLayout.rows;
  const reservedHeight = reservedLayout.height;
  currentGridLayout = Object.freeze({
    columns, rows, width, height,
    reservedCellCount, reservedRows, reservedHeight,
    visibleCount: visibleCells.length,
    visibleSignature
  });

  arenaShell.style.setProperty(
    '--shared-rule-overlap', `${100 * RULE / width}%`
  );
  // Filtering compacts the visible tiles, but keep the roster's original page
  // footprint so a focused search field does not trigger scroll anchoring.
  // Apply the reserve before contracting the surface: reserveRosterFootprint()
  // reads clientWidth and therefore forces layout. Reversing these assignments
  // briefly makes sparse searches shorter than the viewport and clamps scrollY.
  reserveRosterFootprint(currentGridLayout);
  arenaSurface.style.aspectRatio = `${width} / ${height}`;
  grid.setAttribute('aria-colcount', String(columns));
  grid.setAttribute('aria-rowcount', String(rows));

  visibleCells.forEach((button, index) => {
    const col = index % columns;
    const row = Math.floor(index / columns);
    button.dataset.column = String(col + 1);
    button.dataset.row = String(row + 1);
    button.style.setProperty('--cell-left', `${100 * (RULE + col * (CELL_W + RULE)) / width}%`);
    button.style.setProperty('--cell-top', `${100 * (RULE + row * (CELL_H + RULE)) / height}%`);
    button.style.setProperty('--cell-width', `${100 * CELL_W / width}%`);
    button.style.setProperty('--cell-height', `${100 * CELL_H / height}%`);
    button.setAttribute(
      'aria-label',
      `${button.dataset.displayName}, row ${row + 1}, column ${col + 1}`
    );
  });

  paintPixels(
    ruleCanvas,
    renderRules(width, height, columns, visibleCells.length),
    width,
    height
  );
  paintIntroVideoRule();
  paintSiteMenuRule();

  const metrics = document.getElementById('replica-metrics');
  metrics.textContent =
    `${visibleCells.length}/${cells.size} targetable cells · ${columns}×${rows} · ${width}×${height} native`;

  return currentGridLayout;
}

applyGridLayout();

function syncLayoutToVideoWidth() {
  applyGridLayout(columnsForContainer());
  paintIntroVideoRule();
  paintSiteMenuRule();
}

if (introVideoFrame && 'ResizeObserver' in window) {
  const videoWidthObserver = new ResizeObserver(syncLayoutToVideoWidth);
  videoWidthObserver.observe(introVideoFrame);
}
window.addEventListener('resize', syncLayoutToVideoWidth);

const fighterSearch = document.getElementById('fighter-search');
const fighterEmptyState = document.getElementById('fighter-empty-state');
const searchCell = [...cells.values()].find(button => button.dataset.kind === 'search');
let pendingSearchSelection = null;

function selectableRosterCell(target) {
  const cell = target?.closest?.('.replica-cell');
  return cell?.hasAttribute('aria-pressed') && !cell.hidden ? cell : null;
}

function updateSearchTile(query = '') {
  if (!searchCell) return;
  const value = String(query).trim();
  const active = document.activeElement === fighterSearch;
  const displayLabel = value || 'SEARCH';
  const caption = renderCaption(displayLabel);
  const caretX = value
    ? Math.min(CELL_W - 2, 4 + caption.width + 1)
    : 3;

  searchCell.classList.toggle('is-searching', active);
  searchCell.style.setProperty('--search-caret-left', `${100 * caretX / CELL_W}%`);
  paintCellCanvas(
    searchCell.querySelector('.replica-texture-layer'),
    displayLabel,
    ACTION_PORTRAITS.search,
    active && !value ? 0.5 : 1,
    ACTION_CELL_BACKGROUND_PIXELS.search
  );
}

function filterRoster(query = '') {
  const normalized = String(query).trim().toLocaleLowerCase();
  let visibleCount = 0;

  cells.forEach(button => {
    if (button.dataset.kind === 'search') {
      button.hidden = false;
      return;
    }
    if (button.dataset.kind === 'create') {
      button.hidden = Boolean(normalized);
      return;
    }
    const matches = !normalized || [
      button.dataset.displayName,
      button.dataset.label,
      button.dataset.rosterCharacter,
      button.dataset.portrait
    ].filter(Boolean).some(value => value.toLocaleLowerCase().includes(normalized));
    button.hidden = !matches;
    if (matches) visibleCount++;
  });

  updateSearchTile(query);
  applyGridLayout(columnsForContainer());
  if (fighterEmptyState) {
    fighterEmptyState.hidden = visibleCount > 0;
    fighterEmptyState.textContent = visibleCount
      ? ''
      : `No fighters match “${String(query).trim()}”`;
  }
  grid.setAttribute('aria-label', normalized
    ? `${visibleCount} fighters matching ${String(query).trim()}`
    : 'Search, create, and character roster');
  return visibleCount;
}

fighterSearch?.addEventListener('input', event => filterRoster(event.currentTarget.value));
grid.addEventListener('pointerdown', event => {
  if (!event.isPrimary || event.button !== 0) return;
  pendingSearchSelection = document.activeElement === fighterSearch
    ? selectableRosterCell(event.target)
    : null;
}, { capture: true });
searchCell?.addEventListener('pointerdown', event => {
  // Mouse users expect the field to focus as soon as they press. Touch input
  // waits for click so a scroll gesture that begins here does not activate it.
  if (!event.isPrimary || event.button !== 0 || event.pointerType !== 'mouse') return;
  fighterSearch?.focus({ preventScroll: true });
});
fighterSearch?.addEventListener('focus', event => filterRoster(event.currentTarget.value));
fighterSearch?.addEventListener('blur', event => {
  // Pointer-down blurs the input before click selects the fighter. Keep the
  // filtered layout stable until that click lands, or it can land on empty
  // space after the full roster is restored.
  if (pendingSearchSelection || selectableRosterCell(event.relatedTarget)) return;
  window.setTimeout(() => {
    if (document.activeElement !== fighterSearch) clearFighterSearch();
  }, 0);
});
window.addEventListener('pointerup', event => {
  if (!pendingSearchSelection) return;
  if (selectableRosterCell(event.target) !== pendingSearchSelection) {
    pendingSearchSelection = null;
    if (document.activeElement !== fighterSearch) clearFighterSearch();
  }
});
window.addEventListener('pointercancel', () => {
  pendingSearchSelection = null;
  if (document.activeElement !== fighterSearch) clearFighterSearch();
});
document.addEventListener('click', event => {
  if (searchCell?.contains(event.target)) return;
  pendingSearchSelection = null;
  clearFighterSearch();
});
fighterSearch?.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  event.preventDefault();
  clearFighterSearch();
});

function clearFighterSearch() {
  if (!fighterSearch) return;
  const searchTileStillActive = searchCell?.classList.contains('is-searching');
  if (!fighterSearch.value &&
      document.activeElement !== fighterSearch &&
      !searchTileStillActive) return;
  fighterSearch.value = '';
  fighterSearch.blur();
  // Paint after blur so the custom pixel caret and dimmed SEARCH label reflect
  // the input's final focus state instead of preserving the focused frame.
  filterRoster('');
}

function getCell(name) {
  const value = String(name);
  const key = value.toUpperCase();
  return cells.get(key) || [...cells.values()].find(cell =>
    cell.dataset.label === key || cell.dataset.rosterCharacter === value
  ) || null;
}

function jobCellId(jobId) {
  return `JOB-${jobId}`;
}

function rosterCellId(slug) {
  return `ROSTER-${slug}`;
}

function createRosterCell(character) {
  const id = rosterCellId(character.asset);
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'replica-cell';
  button.dataset.character = id;
  button.dataset.kind = 'fighter';
  button.setAttribute('role', 'gridcell');
  button.setAttribute('aria-pressed', 'false');
  button.append(canvasFromPixels(
    renderCellFramebuffer(character.label, character.portrait).pixels,
    CELL_W,
    CELL_H,
    'replica-texture-layer'
  ));
  attachCellActivation(button);
  grid.append(button);
  cells.set(id, button);
  return button;
}

async function syncCharacters(characters = []) {
  const nextRoster = [...new Map(
    characters.map(character => {
      const rosterCharacter = liveRosterCharacter(character);
      return [rosterCharacter.asset, rosterCharacter];
    })
  ).values()];
  const nextSlugs = new Set(nextRoster.map(character => character.asset));
  const staticFighterCells = [...cells.values()].filter(button =>
    !button.classList.contains('fighter-job-cell') &&
    (button.dataset.kind === 'fighter' || button.dataset.kind === 'creation')
  );

  for (const button of staticFighterCells) {
    if (nextSlugs.has(button.dataset.rosterCharacter)) continue;
    cells.delete(button.dataset.character);
    button.remove();
  }

  await Promise.all(nextRoster.map(async character => {
    let button = [...cells.values()].find(candidate =>
      !candidate.classList.contains('fighter-job-cell') &&
      candidate.dataset.rosterCharacter === character.asset
    );
    // A completed private fighter may already be represented by its job cell.
    // Keep that richer progress/ready cell instead of drawing a duplicate.
    if (!button && [...jobCells.values()].some(candidate =>
      candidate.dataset.kind === 'creation' &&
      candidate.dataset.rosterCharacter === character.asset
    )) return;
    if (!button) button = createRosterCell(character);

    const previousPortraitUrl = button.dataset.portraitUrl || '';
    button.dataset.label = character.label;
    button.dataset.rosterCharacter = character.asset;
    button.dataset.portrait = character.portrait;
    button.dataset.portraitUrl = character.portraitUrl || '';
    button.dataset.displayName = character.name;
    button.dataset.fkind = String(character.fkind ?? 0);
    if (character.bundle) button.dataset.bundle = character.bundle;
    else delete button.dataset.bundle;
    button.setAttribute('aria-label', character.name);

    if (
      character.portraitUrl &&
      (previousPortraitUrl !== character.portraitUrl || !CHARACTER_PORTRAITS.has(character.portrait))
    ) {
      try {
        CHARACTER_PORTRAITS.set(
          character.portrait,
          await loadFeaturedPortrait(character.portrait, character.portraitUrl)
        );
      } catch (error) {
        console.warn(`Could not load live portrait for ${character.name}:`, error);
      }
    }
    paintCellCanvas(
      button.querySelector('.replica-texture-layer'),
      character.label,
      character.portrait
    );
  }));

  filterRoster(fighterSearch?.value || '');
  return cells;
}

function createJobCell(job) {
  const id = jobCellId(job.id);
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'replica-cell fighter-job-cell';
  button.dataset.character = id;
  button.dataset.kind = 'job';
  button.dataset.label = fitCaption(job.name).text;
  button.dataset.rosterCharacter = job.slug;
  button.dataset.portrait = '';
  button.dataset.displayName = job.name;
  button.dataset.fkind = '0';
  button.setAttribute('role', 'gridcell');
  button.setAttribute('aria-pressed', 'false');
  button.setAttribute('aria-disabled', 'true');

  const framebuffer = renderCellFramebuffer(job.name);
  button.append(canvasFromPixels(
    framebuffer.pixels, framebuffer.width, framebuffer.height, 'replica-texture-layer'
  ));

  const spinner = document.createElement('span');
  spinner.className = 'fighter-job-spinner';
  spinner.setAttribute('aria-hidden', 'true');
  button.append(spinner);

  const progress = document.createElement('span');
  progress.className = 'fighter-job-progress';
  progress.setAttribute('role', 'progressbar');
  progress.setAttribute('aria-valuemin', '0');
  progress.setAttribute('aria-valuemax', '100');
  const fill = document.createElement('i');
  progress.append(fill);
  button.append(progress);

  button.addEventListener('click', () => {
    if (button.dataset.kind === 'fighter' || button.dataset.kind === 'creation') {
      requestSelection(button.dataset.rosterCharacter);
    }
  });
  grid.append(button);
  cells.set(id, button);
  jobCells.set(job.id, button);
  return button;
}

async function updateJobCell(job) {
  if (!job?.id) return null;
  const button = jobCells.get(job.id) || createJobCell(job);
  const revision = Number(button.dataset.revision || -1);
  if (revision >= (job.revision || 0)) return button;

  const active = ['queued', 'running', 'retrying'].includes(job.status);
  const complete = job.status === 'complete' && job.character;
  const progress = Math.max(0, Math.min(100, Number(job.progress) || 0));
  button.dataset.revision = String(job.revision || 0);
  button.dataset.status = job.status;
  button.dataset.displayName = job.character?.name || job.name;
  button.dataset.label = fitCaption(job.character?.short || job.name).text;
  button.dataset.rosterCharacter = job.character?.slug || job.slug;
  button.classList.toggle('is-generating', active);
  button.classList.toggle('is-failed', job.status === 'failed');
  button.querySelector('.fighter-job-spinner').hidden = !active;
  const progressElement = button.querySelector('.fighter-job-progress');
  progressElement.hidden = complete;
  progressElement.setAttribute('aria-valuenow', String(progress));
  progressElement.setAttribute('aria-label', `${job.name} generation ${progress}% complete`);
  progressElement.querySelector('i').style.width = `${progress}%`;
  button.setAttribute('aria-label', complete
    ? `${job.character.name}, ready to fight`
    : `${job.name}, ${job.stageLabel || job.status}, ${progress}% complete`);
  button.setAttribute('aria-disabled', String(!complete));

  if (complete) {
    button.dataset.kind = 'creation';
    button.dataset.character = job.character.slug;
    button.dataset.portrait = `job:${job.id}`;
    button.dataset.fkind = String(job.character.fkind || 0);
    if (job.character.bundle) button.dataset.bundle = job.character.bundle;
    try {
      CHARACTER_PORTRAITS.set(
        button.dataset.portrait,
        await loadFeaturedPortrait(button.dataset.portrait, job.character.portrait)
      );
    } catch (error) {
      console.warn(`Could not load generated portrait for ${job.name}:`, error);
    }
  } else {
    button.dataset.kind = 'job';
  }
  paintCellCanvas(
    button.querySelector('.replica-texture-layer'),
    job.character?.short || job.character?.name || job.name,
    complete ? button.dataset.portrait : null
  );
  return button;
}

async function syncJobs(jobs = []) {
  const staticCells = [...cells.values()].filter(
    button => !button.classList.contains('fighter-job-cell')
  );
  staticCells.forEach(button => {
    if (button.dataset.kind === 'creation') button.dataset.kind = 'fighter';
  });

  const renderedJobs = jobs.filter(job => {
    if (job.status !== 'complete' || !job.character) return true;
    const existing = staticCells.find(
      button => button.dataset.rosterCharacter === job.character.slug
    );
    if (!existing) return true;
    existing.dataset.kind = 'creation';
    return false;
  });

  const nextIds = new Set(renderedJobs.map(job => job.id));
  for (const [jobId, button] of jobCells) {
    if (nextIds.has(jobId)) continue;
    cells.delete(jobCellId(jobId));
    jobCells.delete(jobId);
    button.remove();
  }
  await Promise.all(renderedJobs.map(updateJobCell));
  filterRoster(fighterSearch?.value || '');
  return jobCells;
}

function setLabel(character, label) {
  const cell = getCell(character);
  if (!cell) return null;
  const fitted = fitCaption(label).text;
  cell.dataset.label = fitted;
  cell.setAttribute('aria-label', fitted || cell.dataset.character);
  paintCellCanvas(
    cell.querySelector('.replica-texture-layer'), fitted, cell.dataset.portrait
  );
  return cell;
}

function randomize() {
  [...cells.values()].filter(cell =>
    cell.dataset.kind === 'fighter' || cell.dataset.kind === 'creation'
  ).forEach(cell => {
    const name = RANDOM_NAME_POOL[Math.floor(Math.random() * RANDOM_NAME_POOL.length)];
    setLabel(cell.dataset.character, name);
  });
  return cells;
}

function clearHighlights() {
  cells.forEach(cell => cell.classList.remove('is-highlighted'));
}

function highlight(name, active = true) {
  const cell = getCell(name);
  if (cell) cell.classList.toggle('is-highlighted', Boolean(active));
  return cell;
}

function select(name) {
  const candidate = name == null ? null : getCell(name);
  const selected = candidate?.hasAttribute('aria-pressed') ? candidate : null;
  cells.forEach(cell => {
    if (cell.hasAttribute('aria-pressed')) {
      cell.setAttribute('aria-pressed', String(cell === selected));
    }
  });
  return selected;
}

// Double select: stamp "1P"/"2P" on picked tiles while more players choose.
function markPick(name, tag) {
  const cell = name == null ? null : getCell(name);
  if (!cell) return null;
  if (tag) cell.dataset.pick = tag;
  else delete cell.dataset.pick;
  return cell;
}

function clearPicks() {
  cells.forEach(cell => { delete cell.dataset.pick; });
}

function requestSelection(name) {
  const selected = name == null ? null : getCell(name);
  if (selected) {
    pendingSearchSelection = null;
    clearFighterSearch();
    grid.dispatchEvent(new CustomEvent('characterselect', {
      bubbles: true,
      detail: {
        name: selected.dataset.character,
        label: selected.dataset.label,
        displayName: selected.dataset.displayName,
        slug: selected.dataset.rosterCharacter,
        fkind: Number(selected.dataset.fkind),
        bundle: selected.dataset.bundle || null,
        cell: selected
      }
    }));
  }
  return selected;
}

function attachCellActivation(cell) {
  cell.addEventListener('click', () => {
    if (cell.dataset.kind === 'search') {
      fighterSearch?.focus({ preventScroll: true });
      return;
    }
    if (cell.dataset.kind === 'create') {
      if (APP_BRIDGE?.navigate) APP_BRIDGE.navigate('/create');
      else window.location.assign('/create');
      return;
    }
    requestSelection(cell.dataset.character);
  });
}

cells.forEach(attachCellActivation);

const BENCH_W = 24;
const BENCH_H = 14;

function stageCaption(caption) {
  const pixels = new Uint8ClampedArray(BENCH_W * BENCH_H * 4);
  const originX = Math.floor((BENCH_W - caption.width) / 2);
  const originY = Math.floor((BENCH_H - caption.height) / 2);
  for (let y = 0; y < caption.height; y++) for (let x = 0; x < caption.width; x++) {
    const source = (y * caption.width + x) * 4;
    put(
      pixels, BENCH_W, originX + x, originY + y,
      caption.pixels[source], caption.pixels[source + 1],
      caption.pixels[source + 2], caption.pixels[source + 3]
    );
  }
  return pixels;
}

function strictPixelGrade(expected, actual) {
  let mismatchedPixels = 0;
  for (let i = 0; i < expected.length; i += 4) {
    if (
      expected[i] !== actual[i] ||
      expected[i + 1] !== actual[i + 1] ||
      expected[i + 2] !== actual[i + 2] ||
      expected[i + 3] !== actual[i + 3]
    ) mismatchedPixels++;
  }
  return {
    mismatchedPixels,
    totalPixels: expected.length / 4,
    score: 100 * (expected.length / 4 - mismatchedPixels) / (expected.length / 4)
  };
}

function glyphIntegrityIssue(char, glyph) {
  const ink = (x, y) => x >= 0 && y >= 0 && x < glyph.width && y < glyph.height &&
    glyph.pixels[(y * glyph.width + x) * 4 + 3] > 0;
  const rowInk = y => Array.from({ length: glyph.width }, (_, x) => x).filter(x => ink(x, y));
  if (![3, 4, 5, 6, 7, 8, 9].some(y => rowInk(y).length)) return 'empty glyph';
  if (char === 'T') {
    if (rowInk(3).length < 4) return 'incomplete top bar';
    if ([4, 5, 6, 7, 8, 9].some(y => rowInk(y).length > 2)) return 'horizontal stem artifact';
  }
  if (char === 'Z') {
    if (glyph.width > 5 || rowInk(3).length < 4 || rowInk(9).length < 4) return 'bulky Z';
    if ([4, 5, 6, 7, 8].some(y => rowInk(y).length > 2)) return 'thick Z diagonal';
  }
  if (char === 'R' && glyph.width > 5) return 'borrowed lower-left pixel';
  if (char === 'Q') {
    const bowl = CAPTION_GLYPHS.get('O');
    if (glyph.width !== bowl.width + 1 || !ink(glyph.width - 1, 9)) return 'missing Q tail';
  }
  if ((char === 'C' || char === 'L') &&
      [3, 4, 5, 6, 7, 8, 9].some(y => ink(glyph.width - 1, y))) {
    return 'missing right side-bearing';
  }
  if (char === 'O' && ink(0, 3)) return 'rogue upper-left pixel';
  if (char === 'I' && glyph.width !== 2) return 'contaminated I stem';
  return '';
}

function buildFontBench() {
  const bench = document.getElementById('font-glyph-grid');
  if (!bench) {
    return Object.freeze({
      validGlyphs: 0,
      exactGlyphs: 0,
      mismatchedPixels: 0,
      totalPixels: 0,
      score: 0,
    });
  }
  let mismatchedPixels = 0;
  let totalPixels = 0;
  let validGlyphs = 0;

  for (const char of ALPHABET) {
    const glyph = CAPTION_GLYPHS.get(char);
    const expected = stageCaption(glyph);
    const sourceCanvas = canvasFromPixels(expected, BENCH_W, BENCH_H);
    const sourcePixels = sourceCanvas.getContext('2d')
      .getImageData(0, 0, BENCH_W, BENCH_H).data;
    const canvas = canvasFromPixels(stageCaption(renderCaption(char, BENCH_W)), BENCH_W, BENCH_H);
    const actual = canvas.getContext('2d').getImageData(0, 0, BENCH_W, BENCH_H).data;
    const grade = strictPixelGrade(sourcePixels, actual);
    const integrityIssue = glyphIntegrityIssue(char, glyph);
    if (!integrityIssue) validGlyphs++;
    mismatchedPixels += grade.mismatchedPixels;
    totalPixels += grade.totalPixels;

    const figure = document.createElement('figure');
    figure.className = `glyph-pair${grade.mismatchedPixels || integrityIssue ? '' : ' is-exact'}`;
    figure.dataset.character = char;
    figure.dataset.mismatchedPixels = String(grade.mismatchedPixels);
    figure.dataset.integrityIssue = integrityIssue;

    const caption = document.createElement('figcaption');
    const character = document.createElement('strong');
    const score = document.createElement('output');
    character.textContent = char;
    score.textContent = integrityIssue ? 'FAIL' : 'PASS';
    if (integrityIssue) score.title = integrityIssue;
    caption.append(character, score);

    const gameRow = document.createElement('div');
    gameRow.className = 'glyph-row';
    const gameLabel = document.createElement('span');
    gameLabel.className = 'glyph-row-label';
    gameLabel.textContent = 'Font';
    const gameStage = document.createElement('span');
    gameStage.className = 'glyph-stage';
    sourceCanvas.setAttribute('role', 'img');
    sourceCanvas.setAttribute('aria-label', `${char} from the extracted OpenSmash tile-caption font`);
    gameStage.append(sourceCanvas);
    gameRow.append(gameLabel, gameStage);

    const codeRow = document.createElement('div');
    codeRow.className = 'glyph-row';
    const codeLabel = document.createElement('span');
    codeLabel.className = 'glyph-row-label';
    codeLabel.textContent = 'Code';
    const codeStage = document.createElement('span');
    codeStage.className = 'glyph-stage';
    codeStage.append(canvas);
    codeRow.append(codeLabel, codeStage);

    figure.append(caption, gameRow, codeRow);
    bench.append(figure);
  }

  const exactGlyphs = [...bench.children].filter(node => node.dataset.mismatchedPixels === '0').length;
  const score = 100 * (totalPixels - mismatchedPixels) / totalPixels;
  document.getElementById('font-bench-detail').textContent =
    `${validGlyphs}/26 topology checks · ${exactGlyphs}/26 compositor matches · ${mismatchedPixels.toLocaleString()} RGBA mismatches`;
  document.getElementById('font-bench-score').textContent = `${validGlyphs}/26 valid`;
  return Object.freeze({ validGlyphs, exactGlyphs, mismatchedPixels, totalPixels, score });
}

const FONT_GRADE = buildFontBench();

// Public, DOM-first hooks for future game/UI work. Example:
// characterGrid.setLabel('CELL-001', 'CUSTOM'); characterGrid.highlight('CELL-042');
window.characterGrid = Object.freeze({
  element: grid,
  cells,
  get columnCount() { return currentGridLayout.columns; },
  get rowCount() { return currentGridLayout.rows; },
  getCell,
  setLabel,
  highlight,
  clearHighlights,
  select,
  markPick,
  clearPicks,
  syncCharacters,
  syncJobs,
  filter: filterRoster,
  randomize
});

await syncJobs(INITIAL_FIGHTER_JOBS);

window.__replicaMetrics = Object.freeze({
  get nativeGrid() { return currentGridLayout.width + 'x' + currentGridLayout.height; },
  get columns() { return currentGridLayout.columns; },
  get rows() { return currentGridLayout.rows; },
  cellInterior: CELL_W + 'x' + CELL_H,
  get cellElements() { return cells.size; },
  alphabetGlyphs: CAPTION_GLYPHS.size,
  sharedRule: RULE + 'px',
  rasterScale: RASTER_SCALE,
  fireTexels: CELL_W * CELL_H,
  labelGlyphPixels: [...CAPTION_GLYPHS.values()].reduce(
    (total, glyph) => total + glyph.width * glyph.height, 0
  ),
  runtimeFontAssetRequests: CAPTION_GLYPHS.size,
  sharedCaptionPipeline: true,
  fontGrade: FONT_GRADE,
  get characterPortraits() { return CHARACTER_PORTRAITS.size; },
  get runtimePortraitAssetRequests() { return CHARACTER_PORTRAITS.size; },
  portraitSource: 'OpenSmash transparent portrait cutouts',
  portraitsGraded: false
});

document.documentElement.dataset.replicaReady = 'true';
