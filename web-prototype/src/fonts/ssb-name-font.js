// SSB64 character-select name font — bitmap renderer.
//
// Source: the names baked into the character-select portrait tiles
// (MNPlayersPortraits). Tan face (146,139,114), 7 px cap height, 1 px black
// outline (no drop shadow). The data (ssb-name-font-data.js) stores every glyph as
// two float maps:
//   c  face coverage (tan)         s  the glyph's OWN dark alpha (outline)
// Faces compose with max(), dark alpha additively (clamped), then:
//   A = c + s*(1-c)     colour = faceColor * (c / A)     (straight alpha)
// With the per-name glyph variants in `layouts`, all eleven standard-cut names
// reproduce the portrait pixels exactly. Free text uses the default glyph per
// letter plus the measured kerning pairs.
import { SSB_NAME_FONT as FONT } from './ssb-name-font-data.js';

export { FONT as SSB_NAME_FONT };

const q8 = (v) => Math.round(Math.min(1, Math.max(0, v)) * 255);

const LAYOUT_BY_TEXT = new Map();
for (const [name, lay] of Object.entries(FONT.layouts)) LAYOUT_BY_TEXT.set(lay.text, { name, ...lay });

/** Kerning value for a pair of base letters (measured first, then class guesses). */
export function kernFor(a, b, { synthKern = true, condensed = false } = {}) {
  if (condensed) return FONT.condensed.kern[a + b] || 0;
  const k = FONT.kern[a + b];
  if (k !== undefined) return k;
  if (synthKern && FONT.kernSynth[a + b] !== undefined) return FONT.kernSynth[a + b];
  return 0;
}

/** Glyph table for a face: the regular cut or the condensed (JIGGLYPUFF-style) cut. */
export function glyphSet(condensed = false) {
  return condensed ? FONT.condensed.glyphs : FONT.glyphs;
}

/**
 * Lay out text -> { glyphs: [{id, x}], exactName }; x = face origin of each glyph.
 * opts.exact (default true): an original name uses its own glyph variants and
 * positions, reproducing the portrait pixels exactly.
 * opts.tracking: extra pixels added to every advance (negative tightens).
 */
export function layoutText(text, opts = {}) {
  const { exact = true, kern = true, synthKern = true, tracking = 0, condensed = false } = opts;
  const up = text.toUpperCase();
  const glyphTable = glyphSet(condensed);
  const gap = condensed ? FONT.condensed.defaultGap : FONT.defaultGap;
  const space = condensed ? FONT.condensed.spaceAdvance : FONT.spaceAdvance;
  if (exact && !condensed && LAYOUT_BY_TEXT.has(up)) {
    const lay = LAYOUT_BY_TEXT.get(up);
    const x0 = lay.glyphs[0][1];
    return { glyphs: lay.glyphs.map(([id, x]) => ({ id, x: x - x0 })), exactName: lay.name };
  }
  const glyphs = [];
  let pen = 0;
  const chars = [...up];
  for (let i = 0; i < chars.length; i++) {
    const ch = chars[i];
    if (ch === ' ') { pen += space; continue; }
    const g = glyphTable[ch];
    if (!g) continue;
    glyphs.push({ id: ch, x: pen });
    // advance by ink bearings: one empty column between letters by default, plus the pair kern
    const next = chars[i + 1];
    const nextG = next && next !== ' ' ? glyphTable[next] : null;
    // (bearings are fractional: a half-covered edge column counts as half a pixel)
    if (nextG) pen = Math.floor(pen + g.inkR + gap + tracking + (kern ? kernFor(ch, next, { synthKern, condensed }) : 0) - nextG.inkL + 0.5);
    else pen = Math.floor(pen + g.inkR + gap + 0.5);
  }
  return { glyphs, exactName: null, condensed };
}

/**
 * Render to coverage/alpha arrays: { width, height, I, A, originX, originY }.
 * I = face fraction of the pixel colour (0..255), A = alpha (0..255).
 * originX/originY: position of the first glyph's face origin inside the bitmap.
 */
export function renderIA(text, opts = {}) {
  const { glyphs } = layoutText(text, opts);
  const table = glyphSet(opts.condensed);
  const H = FONT.boxH;
  if (!glyphs.length) return { width: 0, height: H, I: new Uint8Array(0), A: new Uint8Array(0), originX: 0, originY: 0 };
  let xmin = Infinity, xmax = -Infinity;
  for (const { id, x } of glyphs) {
    const g = table[id];
    xmin = Math.min(xmin, x + g.ox); xmax = Math.max(xmax, x + g.ox + g.w);
  }
  const W = xmax - xmin;
  const C = new Float64Array(W * H), S = new Float64Array(W * H);
  for (const { id, x } of glyphs) {
    const g = table[id];
    const gx = x + g.ox - xmin;
    for (let by = 0; by < g.h; by++) {
      for (let bx = 0; bx < g.w; bx++) {
        const k = by * g.w + bx, o = by * W + gx + bx;
        if (g.c[k] > C[o]) C[o] = g.c[k];
        S[o] += g.s[k];
      }
    }
  }
  const I = new Uint8Array(W * H), A = new Uint8Array(W * H);
  for (let o = 0; o < W * H; o++) {
    const c = C[o], s = Math.min(1, S[o]);
    const a = c + s * (1 - c);
    if (a > 1e-9) { A[o] = q8(a); I[o] = q8(c / a); }
  }
  return { width: W, height: H, I, A, originX: -xmin, originY: FONT.faceRow - FONT.boxRow };
}

/** Straight-alpha RGBA ImageData in the font's face colour. */
export function toImageData(r, faceColor = FONT.faceColor) {
  const img = new ImageData(Math.max(1, r.width), r.height);
  const [fr, fg, fb] = faceColor;
  for (let o = 0; o < r.width * r.height; o++) {
    const k = r.I[o] / 255;
    img.data[o * 4] = Math.round(fr * k); img.data[o * 4 + 1] = Math.round(fg * k); img.data[o * 4 + 2] = Math.round(fb * k);
    img.data[o * 4 + 3] = r.A[o];
  }
  return img;
}

export function renderImageData(text, opts = {}) {
  const r = renderIA(text, opts);
  return Object.assign(r, { imageData: toImageData(r, opts.faceColor) });
}

/** One of the 12 original portrait name strips (top 16 rows of the tile), as IA + RGBA + art mask. */
export function spriteIA(name) {
  const sp = FONT.sprites[name];
  if (!sp) return null;
  const n = sp.w * sp.h, I = new Uint8Array(n), A = new Uint8Array(n), art = new Uint8Array(n);
  for (let o = 0; o < n; o++) { I[o] = sp.ia[o * 2]; A[o] = sp.ia[o * 2 + 1]; art[o] = sp.art[o]; }
  const img = new ImageData(sp.w, sp.h);
  img.data.set(sp.rgba);
  return { width: sp.w, height: sp.h, I, A, art, text: sp.text, imageData: img };
}

let scratch = null;
/**
 * Draw text on a 2D context with integer nearest-neighbour scaling.
 * (x, y) = face origin of the first glyph in unscaled pixels.
 */
export function drawText(ctx, text, x, y, opts = {}) {
  const { scale = 1 } = opts;
  const r = renderImageData(text, opts);
  if (!r.width) return r;
  if (!scratch) scratch = document.createElement('canvas');
  scratch.width = r.width; scratch.height = r.height;
  scratch.getContext('2d').putImageData(r.imageData, 0, 0);
  ctx.save();
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(scratch, (x - r.originX) * scale, (y - r.originY) * scale, r.width * scale, r.height * scale);
  ctx.restore();
  return r;
}

export const FONT_LETTERS = Object.keys(FONT.glyphs).filter((k) => k.length === 1).sort();
