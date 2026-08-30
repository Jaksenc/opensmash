// Responsive extension of the supplied OpenSmash character grid. The lattice,
// fire, captions, and interaction stay code-rendered; only the twelve native
// character portraits are layered into the cells as transparent cutouts.

const RASTER_DEBUG = new URLSearchParams(window.location.search);

const CELL_W = 45;
const CELL_H = 43;
const RULE = 2;
const CELL_COUNT = 200;
const FLAME_BRIDGE_CELL_COUNT = 4;
const FLAME_BRIDGE_BREAKPOINT = 640;
const FLAME_BRIDGE_HEIGHT_SCALE = 0.25;
const GRID_COLUMN_BREAKPOINTS = Object.freeze([
  { minWidth: 1024, columns: 8 },
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
const FIRE_RGBA5551 = 'eIeRh5mFqkXDQ9QBzIXcydTJ1IfUQcvBw8HLgcNBw0HCwbsBw0HLwdRB1IPUydSH1MnUydRBzAHDAbLDqcWJRWgHQIVgh1hHWIVIhzCHOEVIhXBHiUeZh7rBcMeJBaIHskXLg8wB1IfUyd0L1MfMQ8vBw4HDgcMBy0G6wbLBw0HUAdRB1IXdC9TJ1QvUydRBzAHDQbKDqgeRR2BFUEdgRWBHaEdYR0iHQIVgR3jFiUWiBbrBCEMIQwhDCEMIQwhDGEMghShFGEMQQyBFIIUwhUCFSEdQh1iHYEdYR1CFSEdYh2BFaAdgR3hHWEVIhyhFIEUoRShFMIUwhTBFKIUoRSBFKEUohSBDEEUQQwhDCEMIQwhDCEMIQwhDGEMgRShFIIMYQxhFKEUwhUBHSIdQh2BHYEVgR1BHWEdYR2iFaEdgR3BHYEVAhShHMEUwhTCFMIU4hzBFMIUwhShFMEUoRSiFEEUQQwhDCEMIQwhDCEMIQwhDEEMoRSBFIEUYgyBFKIU4RUiHSIdYR2BHYIVgR2BFYEdgR2hFWIdoB3gHYIVARzCFMEU4hTCFOEUwhTiHMIUwhTBFOIUwRSCFEEMQQwhDCEMIQwhDCEMIQwhDEEMoRSiFIEUYQyBFMIU4R1BHQIVYR2iHYEVwR2hFYEdgR2BHWEVwB3AHYIc4RTiFOIU4hziFOEU4hzCFOIUwRTCFOEU4hSBFEEUIQQhDCEMIQwhDCEMIQwhDEEMgRSiFKEUYQyBFMIdAhVBFSIdgRWhHaAd4B3BFaAdgh2BFYEd4R2gHUIVAhzhFQIc4hzhFOIU4hziFOIcwRTCFOIUwhyBDEEUIQQhDCEMIQwhDCEMIQwhDCEMgRSiFKEMgRSiFMIVIhUiHUEdgR3hFeAd4SXhHaAVoR1hHcAdwR3AHSIU4hUBFQEdAhzhFQIc4hTiFOIc4hTiFOEUwRRiFEEMIQwhDCEMIQwhDCEMIQwhDCEMgQyiFKEcogyhHOIVIR1CFSEdwR3hFeAeAh3gFcEdoR2BHcAd4R2hFQEdAhUBHQIVAh0hFQIc4RTiHMIU4hTiHOEUohSBDEEUIQQhDCEMIAwhDCEMIAwhDCEMYgyhFKIUoRTCFOIdQh1BHWEVwBYCHeEWAh4BHcAdoB2hFeEVwB2CFQIdAhUCHSIVARUiFSIdARTiHOIU4RUCHMIUohRhFEEMIQwhDCEMIQwhDCEMIQwhDCEMYQyiFMEUwhShFQIdQh1hFaEd4RYBHgIWAh4CHcAdwBXBHgIVwB1iHQEVAh0CFQEdIhVCHSEdAh0BFOIc4RUCHOIUgRRhFEIMIAQhDCEMIQwhDCEMIQQhDCEMYRSiFMEUwRzCFQIdYR2BHaEWASYCFgMWIxYCFeEdwR4CHgMVwB1CFQEdAh0CFSIdIh1BHUEdIR0CFOEVAh0CHMIUoRRhDEEMIQwhDCEMIQwhDCEMIQwhDCEMQQzCHMEUwhTiFSIdgR2BHaEWAyYiHiMeIxYjHgMd4R4jFgMdwR1BHQIVAhUiHQEdQhVhHSIdQR0CFQIdIRUiHOIUgRRhDGEMIQwhDCEMIQwhDCEMIQwhDCEMQQyhFOIUwRUCHWIdYRWBHaEWIx4iHiMeRB4kFiMeAxYkHiMdoRVCFQEdIhUCFUEdIRVhFUEdQh0iHSEdQh0iHOIUoRRhDEEMIQwhDCEMIQwgDCEMIQwhDCEMYQzBFMIVAhUhHWIdgR2hFaAeAx5EFiMeRBZFHiQWRR5FHgIdoRVBHSIdAhUhHUIdYRVhHUIVQR0iFSIdQR1BHOIUohRBDGEUIQQhDCEMQQwhDCEMQQwhDCEMoRTCFQEVIhVCHYEdgh2CHaAeAx5EHiMeZRZlHkUeZhZFFgQVwB1iFSEdAh1CFUEdoRViHWEdQR1BHSIdYRUiFQIcohRhDEIUIAwhDCEMQQxBDGEUYQxBDGEUwhTiFSEdQh1BHYIdgR2BFcEeAhZlHkUWZRaHHmUWZhZGFiQd4B1iFUEdQh1iFUIdoB2hFUIdQR1CHUEdYRUiHQIcohRhDEEUQQwhBCEEgRSBFKIUoRRhFKIVAh0BHUIdYh1iFWIdgR2BFeAeJB5lFmUWhx6HFoYehh5mFiQd4R2BHWIVYR2BHYEdwRWhFUEdIRVCHUEdQhUiHQIUwRSCFIIUQQwhDEEMwhThHOIUwhShFQIVIR0iHWIVgR1hHYIdoR2AFgEeJB5mFmUWpxaIFqcWhxaHFkQeAx3AHYIVgR2hFcAd4R2BFUEdQh1BHWEVYh0hHQIcwhSBFKIUgRRBDIIU4RUiHSEdARTiFSIdYh1BFWEdoR2BHYEdoR3hHgIeRR6FFoYWiBaIFqgWiBanFmYWJB3hHaAdoB3BFgIdwBWCHUEVQR1BFWIdYRUiHQEU4hRBDOIUwRxhF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';
// Exact port of opensmash/pixel_font.py's portrait-caption alphabet. The rows
// were transcribed from the vanilla tile dumps; every label is composed from
// these same native pixels, so arbitrary names use the identical face, outline,
// tracking, fitting, and browser-capture path as the original roster names.
const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const CAPTION_CAP = 7;
const CAPTION_FACE = Object.freeze([146, 139, 114, 255]);
const CAPTION_EDGE = Object.freeze([94, 90, 74, 255]);
const CAPTION_OUTLINE = Object.freeze([42, 40, 33, 255]);
const CAPTION_FALLBACK_ROWS = Object.freeze({
  "A": ["..#..", ".#.#.", "#...#", "#####", "#...#", "#...#", "#...#"],
  "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
  "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
  "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
  "E": ["####", "#...", "#...", "###.", "#...", "#...", "####"],
  "F": ["####", "#...", "#...", "###.", "#...", "#...", "#..."],
  "G": [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."],
  "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
  "I": ["#", "#", "#", "#", "#", "#", "#"],
  "J": ["...#", "...#", "...#", "...#", "...#", "#..#", ".##."],
  "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
  "L": ["#...", "#...", "#...", "#...", "#...", "#...", "####"],
  "M": ["#.....#", "##...##", "#.#.#.#", "#..#..#", "#.....#", "#.....#", "#.....#"],
  "N": ["#....#", "##...#", "#.#..#", "#..#.#", "#...##", "#....#", "#....#"],
  "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
  "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
  "Q": [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
  "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
  "S": [".###", "#...", "#...", ".##.", "...#", "...#", "###."],
  "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
  "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
  "V": ["#...#", "#...#", "#...#", "#...#", ".#.#.", ".#.#.", "..#.."],
  "W": ["#.....#", "#.....#", "#.....#", "#..#..#", "#.#.#.#", "##...##", "#.....#"],
  "X": ["#...#", ".#.#.", "..#..", "..#..", "..#..", ".#.#.", "#...#"],
  "Y": ["#...#", ".#.#.", "..#..", "..#..", "..#..", "..#..", "..#.."],
  "Z": ["####", "...#", "..#.", "..#.", ".#..", "#...", "####"]
});
const CAPTION_GLYPH_ASSET_BASE = 'opensmash/ui_refs/tileglyph_';
const CAPTION_PATCH_CUTS = Object.freeze({
  A: ['mario', 11, 17], B: ['kirby', 18, 23], C: ['captain', 3, 8],
  D: ['dk', 5, 12], E: ['ness', 10, 16], F: ['fox', 4, 9],
  G: ['purin', 9, 14], H: ['yoshi', 23, 29], I: ['link', 9, 12],
  J: ['purin', 3, 7], K: ['dk', 12, 19], L: ['link', 4, 9],
  M: ['mario', 4, 11], N: ['ness', 4, 10], O: ['fox', 9, 16],
  P: ['pikachu', 4, 9], R: ['mario', 17, 23], S: ['yoshi', 17, 23],
  U: ['pikachu', 36, 42], X: ['fox', 17, 25], Y: ['yoshi', 4, 10]
});
const CAPTION_KERNING = Object.freeze({ KI: -1 });
const CELL_IDS = Object.freeze(Array.from(
  { length: CELL_COUNT }, (_, index) => `CELL-${String(index + 1).padStart(3, '0')}`
));
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

function fallbackGlyph(char) {
  const rows = CAPTION_FALLBACK_ROWS[char];
  const width = rows[0].length;
  const pixels = new Uint8ClampedArray(width * 10 * 4);
  rows.forEach((row, y) => [...row].forEach((cell, x) => {
    if (cell === '#') put(pixels, width, x, y + 3, ...CAPTION_FACE);
  }));
  return Object.freeze({ char, width, height: 10, advance: width + 1, pixels, extracted: false });
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

function cropCaptionPixels(source, x0, x1, exactSourceColors) {
  const height = 10;
  const cutWidth = x1 - x0;
  const cut = new Uint8ClampedArray(cutWidth * height * 4);
  for (let y = 0; y < height; y++) for (let x = 0; x < cutWidth; x++) {
    const sourceIndex = (y * source.width + x + x0) * 4;
    const r = source.pixels[sourceIndex];
    const g = source.pixels[sourceIndex + 1];
    const b = source.pixels[sourceIndex + 2];
    const a = source.pixels[sourceIndex + 3];
    const isCaptionPixel = exactSourceColors
      ? a > 0 && r >= 15 && r <= 150 && Math.abs(r - g) <= 15 && g >= b && g - b <= 35
      : a > 0;
    if (!isCaptionPixel) continue;
    const target = (y * cutWidth + x) * 4;
    cut[target] = r;
    cut[target + 1] = g;
    cut[target + 2] = b;
    cut[target + 3] = 255;
  }
  let left = cutWidth, right = 0;
  for (let y = 0; y < height; y++) for (let x = 0; x < cutWidth; x++) {
    if (!cut[(y * cutWidth + x) * 4 + 3]) continue;
    left = Math.min(left, x);
    right = Math.max(right, x + 1);
  }
  const width = Math.max(1, right - left);
  const pixels = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    const sourceIndex = (y * cutWidth + x + left) * 4;
    pixels.set(cut.subarray(sourceIndex, sourceIndex + 4), (y * width + x) * 4);
  }
  return Object.freeze({ width, height, advance: cutWidth, pixels });
}

async function loadExtractedGlyph(char) {
  const patch = CAPTION_PATCH_CUTS[char];
  if (patch) {
    const [sourceName, x0, x1] = patch;
    const source = await loadCaptionImage(
      `opensmash/ui_refs/tile_${sourceName}.png?v=20260828dq`
    );
    return Object.freeze({
      char,
      ...cropCaptionPixels(source, x0, x1, true),
      extracted: true
    });
  }
  const image = new Image();
  image.decoding = 'async';
  image.src = `${CAPTION_GLYPH_ASSET_BASE}${char.charCodeAt(0)}.png?v=20260828dq`;
  await image.decode();
  const canvas = document.createElement('canvas');
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  context.drawImage(image, 0, 0);
  const source = Object.freeze({
    width: canvas.width,
    height: canvas.height,
    pixels: context.getImageData(0, 0, canvas.width, canvas.height).data
  });
  const fallback = cropCaptionPixels(source, 0, source.width, false);
  const outlined = addCaptionOutline(fallback.pixels, fallback.width, fallback.height);
  return Object.freeze({ char, ...outlined, advance: outlined.width, extracted: true });
}

const CAPTION_GLYPHS = new Map(await Promise.all([...ALPHABET].map(async char => {
  try {
    return [char, await loadExtractedGlyph(char)];
  } catch {
    return [char, fallbackGlyph(char)];
  }
})));

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

const CHARACTER_PORTRAITS = new Map(await Promise.all(VANILLA_ROSTER.map(async character => [
  character.portrait,
  cutOutPortrait(await loadCaptionImage(
    `assets/charselect/${character.portrait}.png?v=20260829c`
  ), character.label)
])));

function padExtractedGlyph(char, glyph, left = 0, right = 0) {
  const width = glyph.width + left + right;
  const pixels = new Uint8ClampedArray(width * glyph.height * 4);
  for (let y = 0; y < glyph.height; y++) for (let x = 0; x < glyph.width; x++) {
    const source = (y * glyph.width + x) * 4;
    pixels.set(glyph.pixels.subarray(source, source + 4), (y * width + x + left) * 4);
  }
  return Object.freeze({
    char, width, height: glyph.height, advance: glyph.advance ?? glyph.width,
    pixels, extracted: true
  });
}

function cropExtractedGlyph(char, glyph, x0, x1) {
  const width = Math.max(1, x1 - x0);
  const pixels = new Uint8ClampedArray(width * glyph.height * 4);
  for (let y = 0; y < glyph.height; y++) for (let x = 0; x < width; x++) {
    const source = (y * glyph.width + x + x0) * 4;
    pixels.set(glyph.pixels.subarray(source, source + 4), (y * width + x) * 4);
  }
  return Object.freeze({
    char, width, height: glyph.height, advance: glyph.advance ?? glyph.width,
    pixels, extracted: true
  });
}

function synthesizeExtractedT() {
  const top = CAPTION_GLYPHS.get('F');
  const stem = CAPTION_GLYPHS.get('I');
  const width = top.width;
  const height = Math.max(top.height, stem.height);
  const pixels = new Uint8ClampedArray(width * height * 4);
  // Copy only F's actual top bar. Earlier versions copied a rectangular band,
  // which preserved a dark horizontal fragment inside the T.
  const topY = 3;
  for (let x = 0; x < top.width; x++) {
    const source = (topY * top.width + x) * 4;
    if (top.pixels[source + 3]) {
      pixels.set(top.pixels.subarray(source, source + 4), (topY * width + x) * 4);
    }
  }
  // Use only I's brightest face sample in each row. Its dim side sample is
  // appropriate on a freestanding I, but reads as a dark bar inside T.
  const stemX = Math.floor(width / 2);
  for (let y = topY; y < stem.height; y++) {
    let brightest = -1;
    let brightestValue = -1;
    for (let x = 0; x < stem.width; x++) {
      const source = (y * stem.width + x) * 4;
      if (!stem.pixels[source + 3]) continue;
      const value = stem.pixels[source] + stem.pixels[source + 1] + stem.pixels[source + 2];
      if (value > brightestValue) { brightest = source; brightestValue = value; }
    }
    if (brightest >= 0) {
      const target = (y * width + stemX) * 4;
      pixels.set(stem.pixels.subarray(brightest, brightest + 4), target);
    }
  }
  return Object.freeze({
    char: 'T', width, height, advance: top.advance ?? width,
    pixels, extracted: true
  });
}

function synthesizeExtractedQ() {
  const bowl = CAPTION_GLYPHS.get('O');
  const width = bowl.width + 1;
  const pixels = new Uint8ClampedArray(width * bowl.height * 4);
  for (let y = 0; y < bowl.height; y++) for (let x = 0; x < bowl.width; x++) {
    const source = (y * bowl.width + x) * 4;
    pixels.set(bowl.pixels.subarray(source, source + 4), (y * width + x) * 4);
  }
  // A one-texel diagonal tail keeps Q the same bowl weight as O.
  put(pixels, width, bowl.width - 2, 8, ...CAPTION_FACE);
  put(pixels, width, bowl.width - 1, 9, ...CAPTION_FACE);
  put(pixels, width, bowl.width, 9, ...CAPTION_EDGE);
  return Object.freeze({
    char: 'Q', width, height: bowl.height, advance: (bowl.advance ?? bowl.width) + 1,
    pixels, extracted: true
  });
}

function synthesizeExtractedZ() {
  const rows = CAPTION_FALLBACK_ROWS.Z;
  const width = rows[0].length + 1;
  const height = 10;
  const pixels = new Uint8ClampedArray(width * height * 4);
  rows.forEach((row, rowIndex) => [...row].forEach((cell, x) => {
    if (cell !== '#') return;
    const y = rowIndex + 3;
    put(pixels, width, x, y, ...CAPTION_FACE);
    if (x + 1 < width && row[x + 1] !== '#') {
      put(pixels, width, x + 1, y, ...CAPTION_EDGE);
    }
  }));
  return Object.freeze({ char: 'Z', width, height, advance: width, pixels, extracted: true });
}

// Preserve a transparent right side-bearing so browser reduction cannot crop
// the open C endpoints or L foot. Remove MARIO's borrowed lower-left R column.
CAPTION_GLYPHS.set('C', padExtractedGlyph('C', CAPTION_GLYPHS.get('C'), 0, 1));
CAPTION_GLYPHS.set('L', padExtractedGlyph('L', CAPTION_GLYPHS.get('L'), 0, 1));
CAPTION_GLYPHS.set('R', cropExtractedGlyph('R', CAPTION_GLYPHS.get('R'), 1, CAPTION_GLYPHS.get('R').width));
CAPTION_GLYPHS.set('T', synthesizeExtractedT());
CAPTION_GLYPHS.set('Q', synthesizeExtractedQ());
CAPTION_GLYPHS.set('Z', synthesizeExtractedZ());

function measureCaption(text, tracking = 0) {
  const chars = [...text].filter(char => CAPTION_GLYPHS.has(char));
  if (!chars.length) return 0;
  let width = 0;
  chars.forEach((char, index) => {
    const glyph = CAPTION_GLYPHS.get(char);
    width += glyph.advance ?? glyph.width;
    if (index < chars.length - 1) {
      width += tracking + (CAPTION_KERNING[char + chars[index + 1]] || 0);
    }
  });
  return width;
}

function fitCaption(value, maxWidth = CELL_W - 5) {
  let text = String(value).toUpperCase().replace(/[^A-Z]/g, '');
  for (const tracking of [0, -1]) {
    const width = measureCaption(text, tracking);
    if (width <= maxWidth) return Object.freeze({ text, tracking, width: Math.max(1, width) });
  }
  while (text && measureCaption(text, -1) > maxWidth) text = text.slice(0, -1);
  return Object.freeze({ text, tracking: -1, width: Math.max(1, measureCaption(text, -1)) });
}

function drawGlyph(dst, dstWidth, glyph, originX, originY) {
  for (let y = 0; y < glyph.height; y++) for (let x = 0; x < glyph.width; x++) {
    const source = (y * glyph.width + x) * 4;
    put(
      dst, dstWidth, originX + x, originY + y,
      glyph.pixels[source], glyph.pixels[source + 1],
      glyph.pixels[source + 2], glyph.pixels[source + 3]
    );
  }
}

function addCaptionOutline(facePixels, faceWidth, faceHeight) {
  const width = faceWidth + 2;
  const height = faceHeight + 1;
  const pixels = new Uint8ClampedArray(width * height * 4);
  const faceCells = [];
  for (let y = 0; y < faceHeight; y++) for (let x = 0; x < faceWidth; x++) {
    const source = (y * faceWidth + x) * 4;
    if (facePixels[source + 3] > 0) faceCells.push([x + 1, y, source]);
  }
  for (const [x, y] of faceCells) {
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      if (dx || dy) put(pixels, width, x + dx, y + dy, ...CAPTION_OUTLINE);
    }
  }
  for (const [x, y] of faceCells) {
    for (const [dx, dy] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
      put(pixels, width, x + dx, y + dy, ...CAPTION_EDGE);
    }
  }
  for (const [x, y, source] of faceCells) {
    put(
      pixels, width, x, y,
      facePixels[source], facePixels[source + 1],
      facePixels[source + 2], facePixels[source + 3]
    );
  }
  return Object.freeze({ width, height, pixels });
}

function renderCaption(value, maxWidth = CELL_W - 5) {
  const layout = fitCaption(value, maxWidth);
  const height = Math.max(10, ...[...layout.text].map(char => CAPTION_GLYPHS.get(char)?.height || 0));
  const pixels = new Uint8ClampedArray(layout.width * height * 4);
  let x = 0;
  const chars = [...layout.text];
  chars.forEach((char, index) => {
    const glyph = CAPTION_GLYPHS.get(char);
    if (!glyph) return;
    drawGlyph(pixels, layout.width, glyph, x, 0);
    x += glyph.advance ?? glyph.width;
    if (index < chars.length - 1) {
      x += layout.tracking + (CAPTION_KERNING[char + chars[index + 1]] || 0);
    }
  });
  return Object.freeze({ ...layout, height, pixels });
}

function drawLabel(dst, value) {
  const caption = renderCaption(value);
  if (!caption.text) return;
  // These source cuts retain the character-select tile's native top margin
  // and complete baked edge intensities. The first sampled pixel begins at x=4.
  const originX = 4;
  const originY = 0;
  for (let y = 0; y < caption.height; y++) for (let x = 0; x < caption.width; x++) {
    const source = (y * caption.width + x) * 4;
    put(
      dst, CELL_W, originX + x, originY + y,
      caption.pixels[source], caption.pixels[source + 1],
      caption.pixels[source + 2], caption.pixels[source + 3]
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
function renderRules(gridWidth, gridHeight) {
  const sourceWidth = 96;
  const sourceHeight = 92;
  const reference = decodeReferenceRules();
  const dst = new Uint8ClampedArray(gridWidth * gridHeight * 4);
  const xStride = CELL_W + RULE;
  const yStride = CELL_H + RULE;
  for (let y = 0; y < gridHeight; y++) for (let x = 0; x < gridWidth; x++) {
    const xr = x < RULE || x >= gridWidth - RULE || x % xStride < RULE;
    const yr = y < RULE || y >= gridHeight - RULE || y % yStride < RULE;
    if (!xr && !yr) continue;
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

function renderCellFramebuffer(name, portraitName = null) {
  const native = renderCellBackground();
  compositePortrait(native, portraitName);
  const background = scalePixels2x(native, CELL_W, CELL_H, false);
  if (!name || (portraitName && USE_SOURCE_PORTRAIT_CAPTIONS)) return background;
  const nativeLabel = new Uint8ClampedArray(CELL_W * CELL_H * 4);
  drawLabel(nativeLabel, name);
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
  canvas, pixels, width, height, displayScale = 1,
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

function paintCellCanvas(canvas, label, portraitName) {
  const framebuffer = renderCellFramebuffer(label, portraitName);
  paintPixels(
    canvas, framebuffer.pixels, framebuffer.width, framebuffer.height
  );
}

const grid = document.getElementById('replica-grid');
const introVideoFrame = document.querySelector('.intro-video-frame');
const introVideoRuleCanvas = document.querySelector('.intro-video-rule-layer');
const flameBridge = document.getElementById('flame-bridge');
const flameBridgeCells = [...document.querySelectorAll('.flame-bridge-cell')];
const flameBridgeRuleCanvas = document.querySelector('.flame-bridge-rule-layer');
const cells = new Map();

const flameOnlyFramebuffer = renderCellFramebuffer();
flameBridgeCells.forEach(cell => cell.append(canvasFromPixels(
  flameOnlyFramebuffer.pixels,
  flameOnlyFramebuffer.width,
  flameOnlyFramebuffer.height,
  'flame-bridge-texture-layer'
)));

CELL_IDS.forEach((id, index) => {
  const character = VANILLA_ROSTER[index % VANILLA_ROSTER.length];
  const label = character.label;
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'replica-cell';
  button.dataset.character = id;
  button.dataset.label = label;
  button.dataset.rosterCharacter = character.asset;
  button.dataset.portrait = character.portrait;
  button.setAttribute('role', 'gridcell');
  button.setAttribute('aria-label', character.name);
  button.setAttribute('aria-pressed', 'false');
  const framebuffer = renderCellFramebuffer(label, character.portrait);
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
let flameBridgeRuleSignature = '';

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

function columnsForFlameBridge() {
  const containerWidth = flameBridge?.clientWidth || window.innerWidth;
  return containerWidth >= FLAME_BRIDGE_BREAKPOINT ? 2 : 1;
}

function paintFlameBridgeRule() {
  if (!currentGridLayout || !flameBridge || !flameBridgeRuleCanvas) return;
  const columns = columnsForFlameBridge();
  const rows = Math.ceil(FLAME_BRIDGE_CELL_COUNT / columns);
  const logicalWidth = RULE + columns * (CELL_W + RULE);
  const logicalHeight = RULE + rows * (CELL_H + RULE);
  const width = currentGridLayout.width;
  const height = Math.max(
    RULE * 2 + 1,
    Math.round(width * logicalHeight / logicalWidth * FLAME_BRIDGE_HEIGHT_SCALE)
  );
  const signature = `${width}x${height}:${columns}x${rows}`;

  flameBridge.style.setProperty('--flame-bridge-columns', String(columns));
  flameBridge.style.aspectRatio =
    `${logicalWidth} / ${logicalHeight * FLAME_BRIDGE_HEIGHT_SCALE}`;
  if (signature === flameBridgeRuleSignature) return;
  flameBridgeRuleSignature = signature;
  paintPixels(
    flameBridgeRuleCanvas,
    renderSharedPanelRules(width, height, columns, rows),
    width,
    height
  );
}

function columnsForContainer() {
  const containerWidth = introVideoFrame?.clientWidth
    || grid.closest('.arena-surface')?.clientWidth
    || window.innerWidth;
  return GRID_COLUMN_BREAKPOINTS.find(({ minWidth }) => containerWidth >= minWidth).columns;
}

function applyGridLayout(columns = columnsForContainer()) {
  if (currentGridLayout?.columns === columns) return currentGridLayout;

  const rows = Math.ceil(CELL_COUNT / columns);
  const width = RULE + columns * (CELL_W + RULE);
  const height = RULE + rows * (CELL_H + RULE);
  currentGridLayout = Object.freeze({ columns, rows, width, height });

  document.querySelector('.arena-shell').style.setProperty(
    '--shared-rule-overlap', `${100 * RULE / width}%`
  );
  grid.closest('.arena-surface').style.aspectRatio = `${width} / ${height}`;
  grid.setAttribute('aria-colcount', String(columns));
  grid.setAttribute('aria-rowcount', String(rows));

  [...cells.values()].forEach((button, index) => {
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
      `${VANILLA_ROSTER[index % VANILLA_ROSTER.length].name}, row ${row + 1}, column ${col + 1}`
    );
  });

  paintPixels(ruleCanvas, renderRules(width, height), width, height);
  paintIntroVideoRule();
  paintFlameBridgeRule();

  const metrics = document.getElementById('replica-metrics');
  metrics.textContent =
    `${CELL_COUNT} targetable cells · ${columns}×${rows} · ${width}×${height} native`;

  return currentGridLayout;
}

applyGridLayout();

function syncLayoutToVideoWidth() {
  applyGridLayout(columnsForContainer());
  paintIntroVideoRule();
  paintFlameBridgeRule();
}

if (introVideoFrame && 'ResizeObserver' in window) {
  const videoWidthObserver = new ResizeObserver(syncLayoutToVideoWidth);
  videoWidthObserver.observe(introVideoFrame);
}
window.addEventListener('resize', syncLayoutToVideoWidth);

function getCell(name) {
  const key = String(name).toUpperCase();
  return cells.get(key) || [...cells.values()].find(cell => cell.dataset.label === key) || null;
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
  CELL_IDS.forEach(id => {
    const name = RANDOM_NAME_POOL[Math.floor(Math.random() * RANDOM_NAME_POOL.length)];
    setLabel(id, name);
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
  const selected = name == null ? null : getCell(name);
  cells.forEach(cell => cell.setAttribute('aria-pressed', String(cell === selected)));
  if (selected) {
    grid.dispatchEvent(new CustomEvent('characterselect', {
      bubbles: true,
      detail: {
        name: selected.dataset.character,
        label: selected.dataset.label,
        cell: selected
      }
    }));
  }
  return selected;
}

cells.forEach(cell => cell.addEventListener('click', () => select(cell.dataset.character)));

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
  randomize
});

window.__replicaMetrics = Object.freeze({
  get nativeGrid() { return currentGridLayout.width + 'x' + currentGridLayout.height; },
  get columns() { return currentGridLayout.columns; },
  get rows() { return currentGridLayout.rows; },
  cellInterior: CELL_W + 'x' + CELL_H,
  cellElements: cells.size,
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
  characterPortraits: CHARACTER_PORTRAITS.size,
  runtimePortraitAssetRequests: CHARACTER_PORTRAITS.size,
  portraitSource: 'OpenSmash transparent portrait cutouts',
  portraitsGraded: false
});

document.documentElement.dataset.replicaReady = 'true';
