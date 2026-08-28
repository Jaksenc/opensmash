// Shared character-select cell renderer — pure procedure, no game assets.
// Consumed by charselect.html (the grid) and compare.html (the grader view).
// ---------------------------------------------------------------------------
// OpenSmash character-select grid — everything drawn from scratch.
// No game assets are loaded: the font, the fire, and the frame are all
// generated procedurally into a 51x49 pixel buffer per cell, then upscaled
// with nearest-neighbour so it keeps the chunky N64 look at any size.
//   ?n=100    slot count      ?cols=10  columns
//   ?grade=1  emit reference tiles for tools/grade_grid.py
// ---------------------------------------------------------------------------

const FIRE_SEED = 9;             // one shared flame tile, as in-game
const EDGE = 2;                  // shared lattice rule, right + bottom only
const FRAME = 0;                 // no per-cell frame: neighbours share edges
const IW = 45, IH = 43;          // interior = the game's portrait tile size
const TW = IW + EDGE, TH = IH + EDGE;

// ── our font ──────────────────────────────────────────────────────────────
// Authored to the metrics of the game's own menu alphabet: a 5px-tall,
// variable-width (3-5px) caps face with 1px stems — pointed 'A' with a low
// crossbar, barred 'X', splayed 'M'/'W'. Drawn at 2x with a 1px dark
// outline, which is how the select screen presents it.
const GLYPHS = {
A:"..#../..#../.#.#./.###./#...#",
B:"####/#..#/###./#..#/####",
C:".##./##.#/#.../##.#/.##.",
D:"###./#.##/#..#/#.##/###.",
E:"####/#.../###./#.../####",
F:"####/#.../###./#.../#...",
G:".###/#.../#.##/#..#/.##.",
H:"#..#/#..#/####/#..#/#..#",
I:".#./.#./.#./.#./.#.",
J:"...#/...#/#..#/#..#/.##.",
K:"#..#/#.#./##../#.#./#..#",
L:"#.../#.../#.../#.../####",
M:"#...#/##.##/#.#.#/#...#/#...#",
N:"#...#/##..#/#.#.#/#..##/#...#",
O:".##./#..#/#..#/#..#/.##.",
P:"###./#..#/###./#.../#...",
Q:".##../#..#./#..#./#.#../.#.#.",
R:"####/#..#/####/#.#./#..#",
S:".##./#..#/.##./#..#/.##.",
T:"#####/..#../..#../..#../..#..",
U:"#..#/#..#/#..#/#..#/.##.",
V:"#...#/.#.#./.#.#./..#../..#..",
W:"#...#/#.#.#/#.#.#/##.##/#...#",
X:"#...#/#####/..#../#####/#...#",
Y:"#...#/.#.#./..##./..#../..#..",
Z:"####/..##/.#../##../####",
"0":".##./#..#/#..#/#..#/.##.",
"1":".#../##../.#../.#../###.",
"2":"###./...#/.##./#.../####",
"3":"###./...#/.##./...#/###.",
"4":"#..#/#..#/####/...#/...#",
"5":"####/#.../###./...#/###.",
"6":".##./#.../###./#..#/.##.",
"7":"####/...#/..#./.#../.#..",
"8":".##./#..#/.##./#..#/.##.",
"9":".##./#..#/.###/...#/.##.",
"?":".##./#..#/..#./..../..#.",
};
const GH = 5;
const gw = ch => ch === ' ' ? 2 : (GLYPHS[ch] ? GLYPHS[ch].indexOf('/') : 4);
const rows = ch => (GLYPHS[ch] || '').split('/');

// width of a string at horizontal scale sx with a `gap`-pixel rule between
function textWidth(s, sx, gap) {
  let w = 0;
  for (let i = 0; i < s.length; i++) w += gw(s[i]) * sx + (i ? gap : 0);
  return w;
}

// draw with an automatic 1px dark outline (dilate, then fill)
function drawText(buf, s, x0, y0, fill, outline, sx, sy, gap) {
  const F = hex(fill), O = hex(outline);
  const blit = (gx, gy, c, ox, oy) => {
    for (let py = 0; py < sy; py++)
      for (let px = 0; px < sx; px++)
        buf.set(x0 + gx + px + ox, y0 + gy * sy + py + oy, c[0], c[1], c[2], 255);
  };
  for (const pass of [0, 1]) {
    let cx = 0;
    for (const ch of s) {
      const g = rows(ch), w = gw(ch);
      for (let y = 0; y < g.length; y++)
        for (let x = 0; x < w; x++)
          if (g[y] && g[y][x] === '#') {
            if (pass === 0) {
              for (let dy = -1; dy <= 1; dy++)
                for (let dx = -1; dx <= 1; dx++)
                  blit(cx + x * sx, y, O, dx, dy);
            } else {
              blit(cx + x * sx, y, F, 0, 0);
            }
          }
      cx += w * sx + gap;
    }
  }
}


// ── tiny pixel canvas we composite into ───────────────────────────────────
function Buf(w, h) {
  const d = new Uint8ClampedArray(w * h * 4);
  return {
    w, h, d,
    set(x, y, r, g, b, a) {
      if (x < 0 || y < 0 || x >= w || y >= h) return;
      const i = (y * w + x) * 4;
      if (a === undefined) a = 255;
      if (a >= 255) { d[i] = r; d[i+1] = g; d[i+2] = b; d[i+3] = 255; return; }
      const k = a / 255, ik = 1 - k;
      d[i] = d[i]*ik + r*k; d[i+1] = d[i+1]*ik + g*k; d[i+2] = d[i+2]*ik + b*k;
      d[i+3] = Math.max(d[i+3], a);
    },
  };
}
const hex = h => [parseInt(h.slice(1,3),16), parseInt(h.slice(3,5),16), parseInt(h.slice(5,7),16)];


// ── deterministic noise ───────────────────────────────────────────────────
function rnd(n) {
  let t = (n + 0x6D2B79F5) | 0;
  t = Math.imul(t ^ (t >>> 15), 1 | t);
  t ^= t + Math.imul(t ^ (t >>> 7), 61 | t);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}
function noise1(x, seed) {
  const i = Math.floor(x), f = x - i;
  const a = rnd(i * 374761 + seed * 66826), b = rnd((i + 1) * 374761 + seed * 66826);
  const u = f * f * (3 - 2 * f);
  return a + (b - a) * u;
}
function noise2(x, y, seed) {
  return (noise1(x + noise1(y * 1.7, seed + 31) * 3.1, seed) * 0.65
        + noise1(y * 0.9 + 11.3, seed + 17) * 0.35);
}

// fire colour curve: luminance -> RGB, fitted to the game's crimson->ember
// ramp (deep red midtones with almost no green, gold only at the hottest tips)
const CURVE = [[0,6,6,6],[9,20,9,10],[18,40,11,16],[27,62,13,19],[36,91,10,21],
  [45,115,6,23],[53,131,19,22],[62,144,36,22],[71,160,52,18],[80,173,67,14],
  [89,187,86,5],[98,199,104,1],[107,206,125,1],[116,213,142,6],[125,213,151,19],
  [134,216,157,33]];
function rampColor(L) {
  if (L <= CURVE[0][0]) return [CURVE[0][1], CURVE[0][2], CURVE[0][3]];
  for (let i = 1; i < CURVE.length; i++) {
    if (L <= CURVE[i][0]) {
      const a = CURVE[i-1], b = CURVE[i];
      const t = (L - a[0]) / (b[0] - a[0]);
      return [a[1]+(b[1]-a[1])*t, a[2]+(b[2]-a[2])*t, a[3]+(b[3]-a[3])*t];
    }
  }
  const z = CURVE[CURVE.length-1];
  return [z[1], z[2], z[3]];
}

// tile luminance field, fitted to the game tile's measured structure:
//  - a bright lip across the top two rows
//  - dark upper body brightening toward the base (25 -> 90, gamma 1.26)
//  - a broad hot mass centred right of middle, falling off to dark edges
const HPROF = (() => {
  const a = [];
  for (let x = 0; x < IW; x++) {
    const t = Math.max(-1, Math.min(1, (x - 23) / 22));
    a.push(0.48 + 1.02 * Math.pow(0.5 + 0.5 * Math.cos(Math.PI * t), 1.3));
  }
  const m = a.reduce((p, c) => p + c, 0) / a.length;
  return a.map(v => v / m);
})();
function vprof(y) {
  if (y >= IH - 1) return 0;
  const t = Math.max(0, (y - 2) / 39);   // clamp: rows 0-1 sit under the lattice
  return 25 + 65 * Math.pow(t, 1.26);
}

// ── one cell ──────────────────────────────────────────────────────────────
function renderTile(seed, name, showQ) {
  const b = Buf(TW, TH);

  // interior: statistical envelope (vertical ramp x horizontal hot mass)
  // shaped by discrete flame tongues, so the tile gets the game's hard-edged
  // licks and dark gaps rather than a soft glow
  for (let x = 0; x < IW; x++) {
    // how high this column's tongue reaches (0 = top of tile)
    const top0 = IH * (0.16 + 0.46 * noise1(x * 0.33, seed)
                            + 0.14 * noise1(x * 0.85, seed + 3));
    for (let y = 0; y < IH; y++) {
      // striations waver with height instead of running dead vertical
      const streak = 0.86 + 0.28 * noise2(x * 1.7, y * 0.22, seed + 11);
      // the tongue edge wanders, so licks lean rather than sit in columns
      const top = top0 + 4.5 * (noise2(x * 0.35, y * 0.13, seed + 13) - 0.5);
      let L = vprof(y) * HPROF[x] * streak;
      const edge = Math.max(-1, Math.min(1, (y - top) / 3.5));
      // blend the tongue field with the smooth envelope: keeps the
      // game's licks visible without breaking its tonal statistics
      const tongue = 0.70 + 0.56 * (0.5 + 0.5 * edge);
      L *= 1 + 0.72 * (tongue - 1);
      // broad soot patches, like the dark pockets in the game tile
      const patch = noise2(x * 0.18, y * 0.16, seed + 23);
      L *= 1 - 0.42 * Math.max(0, patch - 0.55) / 0.45;
      L *= 1 + 0.22 * (noise2(x * 0.7, y * 0.38, seed + 7) - 0.5);  // mottling
      L += 3.0 * (noise2(x * 1.7, y * 1.4, seed + 5) - 0.5);        // fine grain
      const c = rampColor(Math.max(0, L));
      b.set(x + FRAME, y + FRAME, c[0], c[1], c[2], 255);
    }
  }

  // "?" placeholder for empty slots, same face at 3x
  if (showQ) {
    const w = textWidth('?', 2, 0);
    drawText(b, '?', Math.round((IW - w) / 2), Math.round((IH - GH * 2) / 2) + 3,
             '#efe6d2', '#1a0d06', 2, 2, 0);
  }

  // name across the top: 2x like the select screen, condensing horizontally
  // (never vertically) when a long name would run past the cell
  if (name) {
    let sx = 2, gap = 1;
    if (textWidth(name, sx, gap) > IW + 4) { sx = 1; gap = 1; }
    const w = textWidth(name, sx, gap);
    drawText(b, name, Math.round((IW - w) / 2), 2, '#afa286', '#170c05', sx, 2, gap);
  }

  // shared lattice: only the right and bottom rules are drawn, so touching
  // cells form one continuous 2px line like the game's grid. The line is
  // jittered a little because the original is a low-res texture, not vector.
  const LIT = hex('#8a6b3a'), DRK = hex('#3a2411');
  for (let y = 0; y < TH; y++) {
    const j = noise1(y * 0.9, 21) < 0.22 ? 1 : 0;            // ragged edge
    const c1 = j ? DRK : LIT;
    b.set(IW, y, DRK[0], DRK[1], DRK[2], 255);
    b.set(IW + 1, y, c1[0], c1[1], c1[2], 255);
  }
  for (let x = 0; x < TW; x++) {
    const j = noise1(x * 0.9, 37) < 0.22 ? 1 : 0;
    const c1 = j ? DRK : LIT;
    b.set(x, IH, DRK[0], DRK[1], DRK[2], 255);
    b.set(x, IH + 1, c1[0], c1[1], c1[2], 255);
  }
  return b;
}

function bufToCanvas(b) {
  const cv = document.createElement('canvas');
  cv.width = b.w; cv.height = b.h;
  const ctx = cv.getContext('2d');
  ctx.imageSmoothingEnabled = false;
  ctx.putImageData(new ImageData(b.d, b.w, b.h), 0, 0);
  return cv;
}


export { IW, IH, TW, TH, EDGE, FIRE_SEED, renderTile, bufToCanvas, drawText, textWidth };
