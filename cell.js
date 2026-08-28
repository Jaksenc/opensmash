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
// Flame structure fitted to the game tile as truncated Fourier series:
// TOPK gives each column's tongue height, GAINK its brightness. This is a
// compact analytic description of the source's structure, not pixel data.
const TOPK = [22.2000,0.6761,4.3563,3.0921,4.5248,3.8610,-2.7859,2.3247,-2.9957,-1.3683,-2.1821,0.2276,0.5114,0.0274,-0.3185,-0.1728,0.2518,0.3431,1.0482,1.4041,-0.7923];
const GAINK = [1.0682,0.1995,0.3124,0.0419,0.1621,-0.0703,0.0237,-0.0534,-0.0492,-0.0265,-0.0463,-0.0197,-0.0230,-0.0194,-0.0189,-0.0292,-0.0034,-0.0251,-0.0174,-0.0228,-0.0225];

function fourierAt(A, x, n) {
  const t = x / n * 2 * Math.PI;
  let v = A[0];
  for (let k = 1; k <= (A.length - 1) / 2; k++)
    v += A[2*k-1] * Math.cos(k * t) + A[2*k] * Math.sin(k * t);
  return v;
}
const TOPX = Array.from({ length: IW }, (_, x) => fourierAt(TOPK, x, IW));
const GAINX = Array.from({ length: IW }, (_, x) => fourierAt(GAINK, x, IW));

// Flame shape function: a 22x22 cosine (DCT) series fitted to the game tile.
// An analytic surface rather than pixel data — it evaluates at any
// resolution, so a cell stays crisp at any size on the responsive grid.
const SHAPE = [
  [54.711,9.576,-22.245,-3.371,3.703,-6.110,-2.750,-3.330,-0.484,-1.052,0.135,-0.307,-0.106,-0.653,-0.074,-0.134,-1.061,-0.693,-0.073,-0.380,-0.112,0.100],
  [-21.179,-12.945,1.875,-0.048,-2.366,11.492,-2.170,4.891,-0.385,1.551,0.292,1.596,0.351,-0.385,0.356,-0.394,0.032,-0.242,-0.075,0.244,0.244,0.565],
  [4.211,5.808,2.462,0.141,0.349,-8.023,1.693,-0.998,1.040,-1.271,1.438,0.359,0.551,0.977,0.458,-0.075,-0.396,-0.058,0.273,-0.502,1.163,0.037],
  [10.966,4.777,-0.135,0.605,1.345,-5.810,0.306,-1.207,-2.466,-1.638,-0.360,-0.681,-0.862,1.522,-0.431,-0.239,-0.537,0.403,-0.125,-0.042,0.046,-0.623],
  [2.342,1.273,0.901,0.026,3.070,-0.747,-1.973,0.253,-0.083,-1.037,0.999,-0.727,1.820,-0.515,-0.715,-0.047,0.065,0.077,0.295,-0.459,-0.365,-0.176],
  [8.460,4.064,-2.757,-0.322,0.577,-3.267,0.205,-2.199,1.815,0.726,-0.470,-0.005,-0.061,-0.562,-0.420,0.500,-0.113,-0.034,-0.580,-0.253,-0.006,-0.177],
  [1.634,1.245,0.641,-1.243,-0.634,-1.034,-1.754,0.807,-0.022,-0.371,-0.250,-0.666,0.520,0.168,-0.073,0.435,0.007,0.158,-0.267,0.511,0.097,0.160],
  [8.657,3.744,-2.200,-0.542,1.404,-3.174,0.629,-1.148,0.422,-1.337,0.628,-0.447,0.605,-0.486,-0.089,-0.247,0.384,-0.411,0.795,0.115,-0.110,-0.121],
  [1.123,0.558,0.592,0.198,0.616,-0.987,-0.118,-0.113,-0.032,-0.015,-0.056,-0.087,0.270,-0.181,-0.092,0.195,-0.614,0.164,-0.061,0.351,-0.605,-0.062],
  [8.367,4.387,-1.104,-0.469,0.769,-2.975,-0.412,-1.146,0.459,-0.233,0.220,-0.529,0.282,-0.477,0.156,0.255,-0.267,0.044,0.422,-0.255,-0.378,0.503],
  [0.483,0.844,0.502,-0.192,-0.218,-0.977,-0.633,-0.326,0.040,0.032,-0.213,-0.288,0.077,-0.073,-0.036,-0.032,-0.403,-0.142,-0.040,-0.200,0.251,-0.207],
  [7.382,2.498,-1.903,-0.590,0.810,-2.539,-0.257,-0.637,0.391,-0.033,0.171,-0.561,0.493,0.129,-0.054,-0.045,-0.087,0.179,0.028,0.116,0.155,-0.010],
  [-0.217,0.451,0.625,0.052,0.189,-0.289,-0.124,0.097,0.230,-0.061,-0.067,-0.368,0.142,-0.153,-0.079,0.148,0.024,-0.080,0.390,-0.123,-0.177,0.302],
  [7.024,2.885,-1.260,-0.469,0.765,-2.260,-0.545,-0.754,0.242,-0.417,0.123,-0.319,0.484,-0.320,0.102,0.397,-0.303,0.038,0.141,-0.347,0.202,0.080],
  [-0.815,0.229,0.689,0.082,-0.085,-0.064,0.017,-0.124,0.027,0.044,-0.218,-0.105,0.281,-0.004,-0.110,-0.171,-0.188,0.085,-0.036,0.026,-0.105,0.061],
  [5.869,2.150,-1.370,-0.443,0.566,-1.975,-0.407,-0.477,0.110,-0.331,0.228,-0.231,0.273,0.020,-0.169,-0.005,-0.305,-0.148,0.067,-0.087,-0.003,-0.099],
  [-1.484,-0.250,0.657,0.255,-0.312,0.028,0.248,-0.126,-0.047,0.348,-0.211,-0.016,-0.133,-0.045,0.039,-0.041,0.227,0.053,0.152,-0.069,0.128,-0.044],
  [4.958,1.927,-0.987,-0.344,0.419,-1.565,-0.408,-0.218,0.237,-0.261,0.091,-0.249,0.458,0.089,0.137,0.057,-0.178,0.010,0.209,-0.060,0.096,0.239],
  [-2.168,-0.514,0.689,0.065,-0.207,0.491,0.304,0.013,0.184,0.109,-0.111,-0.095,-0.026,0.054,-0.030,0.025,0.121,0.163,-0.187,0.045,0.024,-0.174],
  [4.053,1.310,-0.962,-0.308,0.498,-1.199,-0.311,-0.195,-0.020,-0.225,0.089,-0.258,0.135,-0.124,-0.215,0.006,-0.096,0.012,-0.041,-0.138,0.023,-0.029],
  [-2.594,-0.671,0.755,0.196,-0.322,0.663,0.178,0.028,-0.089,0.296,0.061,0.032,-0.327,0.001,0.023,0.002,0.222,0.094,0.110,0.157,-0.140,0.065],
  [3.244,1.051,-0.838,-0.286,0.274,-0.956,-0.269,-0.170,0.159,-0.205,0.214,-0.133,0.366,-0.054,0.104,0.055,-0.223,0.100,-0.005,0.016,0.008,0.151]
];
const SHAPE_K = 22;

// evaluate the shape function at normalised (u,v) in [0,1) — any resolution
const _cx = [], _cy = [];
function shapeAt(x, y, w, h) {
  for (let k = 0; k < SHAPE_K; k++) {
    _cx[k] = Math.cos((x + 0.5) * k * Math.PI / w);
    _cy[k] = Math.cos((y + 0.5) * k * Math.PI / h);
  }
  let v = 0;
  for (let u = 0; u < SHAPE_K; u++) {
    const row = SHAPE[u], cy = _cy[u];
    for (let k = 0; k < SHAPE_K; k++) v += row[k] * cy * _cx[k];
  }
  return v;
}

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
    for (let y = 0; y < IH; y++) {
      // the fitted flame surface, plus a little grain for the dithered feel
      let L = shapeAt(x, y, IW, IH);
      L += 2.5 * (noise2(x * 1.7, y * 1.4, seed + 5) - 0.5);
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


const glyphRows = ch => rows(ch);
const glyphW = ch => gw(ch);
export { IW, IH, TW, TH, EDGE, FIRE_SEED, renderTile, bufToCanvas, drawText,
         textWidth, GLYPHS, glyphRows, glyphW };
