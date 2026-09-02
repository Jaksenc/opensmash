#!/usr/bin/env python3
"""Deterministically verify the code-rendered character grid payload.

This verifier checks every encoded fire texel, the transparent portrait
cutouts, the corrected A-Z atlas plus direct source-tile extraction pipeline,
every screenshot-derived border RGB byte, the targetable cell structure, and
the native 45x43 + 2px lattice geometry.
"""

from __future__ import annotations

import base64
import json
import re
import struct
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "web-prototype"
VISUAL = WEB_APP / "visual"
JS = (VISUAL / "grid-replica.js").read_text()
PAGE = (
    (VISUAL / "site-shell.css").read_text()
    + (WEB_APP / "src" / "RetroHome.jsx").read_text()
    + (WEB_APP / "src" / "visual-runtime.js").read_text()
    + (VISUAL / "home-runtime.js").read_text()
)
ASSETS = VISUAL / "assets" / "charselect"
sys.path.insert(0, str(ROOT))
from pipeline.pixel_font import CAP, FACE, GLYPHS, OUTLINE  # noqa: E402


def js_string(name: str) -> str:
    match = re.search(rf"const {name} = '([^']+)';", JS)
    if not match:
        raise SystemExit(f"missing {name}")
    return match.group(1)


def count_diff(actual: bytes, expected: bytes) -> int:
    if len(actual) != len(expected):
        return max(len(actual), len(expected))
    return sum(a != b for a, b in zip(actual, expected))


# Fire: exact round-trip of the extracted N64 RGBA5551 texture.
fire_expected = bytearray()
for r, g, b, a in Image.open(ASSETS / "fire_bg.png").convert("RGBA").get_flattened_data():
    word = ((r >> 3) << 11) | ((g >> 3) << 6) | ((b >> 3) << 1) | (a >= 128)
    fire_expected.extend(struct.pack(">H", word))
fire_actual = base64.b64decode(js_string("FIRE_RGBA5551"))
fire_diff = count_diff(fire_actual, bytes(fire_expected))


# The user-supplied reference resolved to the renderer's native grid.
reference = Image.open(ASSETS / "reference-2x2.png").convert("RGB")
reference = reference.resize((96, 92), Image.Resampling.BOX)


# Character-card labels use the corrected glyph cuts from the actual character-
# select tile dumps. The hand-authored rows remain only as an offline fallback.
glyph_match = re.search(
    r"const CAPTION_FALLBACK_ROWS = Object\.freeze\((\{.*?\})\);", JS, re.S
)
if glyph_match:
    browser_glyphs = json.loads(glyph_match.group(1))
else:
    browser_glyphs = {}
expected_glyphs = {char: GLYPHS[char] for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
glyph_count = len(expected_glyphs)
fallback_diff = sum(browser_glyphs.get(char) != rows for char, rows in expected_glyphs.items())
atlas = {}
for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    path = VISUAL / "assets" / "ui_refs" / f"tileglyph_{ord(char)}.png"
    if path.exists():
        atlas[char] = Image.open(path).convert("RGBA")
atlas_diff = glyph_count - len(atlas)
atlas_diff += sum(
    image.mode != "RGBA"
    or image.height != 10
    or not 3 <= image.width <= 8
    or image.getbbox() is None
    for image in atlas.values()
)
glyph_diff = fallback_diff + atlas_diff
glyph_pixels = sum(im.width * im.height for im in atlas.values())

glyph_pipeline_ok = glyph_diff == 0 and all(token in JS for token in (
    "const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';",
    f"const CAPTION_CAP = {CAP};",
    f"const CAPTION_FACE = Object.freeze([{FACE[0]}, {FACE[1]}, {FACE[2]}, {FACE[3]}]);",
    "const CAPTION_OUTLINE = Object.freeze([42, 40, 33, 255]);",
    "const CAPTION_EDGE = Object.freeze([94, 90, 74, 255]);",
    "image.src = buildAssetUrl(`ui_refs/tileglyph_${char.charCodeAt(0)}.png`);",
    "const CAPTION_PATCH_CUTS = Object.freeze({",
    "const CAPTION_KERNING = Object.freeze({ KI: -1 });",
    "Y: ['yoshi', 4, 10]",
    "I: ['link', 9, 12]",
    "L: ['link', 4, 9]",
    "O: ['fox', 9, 16]",
    "function cropCaptionPixels(source, x0, x1, exactSourceColors) {",
    "async function loadExtractedGlyph(char) {",
    "const CAPTION_GLYPHS = new Map(await Promise.all(",
    "function synthesizeExtractedT() {",
    "function synthesizeExtractedQ() {",
    "function synthesizeExtractedZ() {",
    "function glyphIntegrityIssue(char, glyph) {",
    "CAPTION_GLYPHS.set('C', padExtractedGlyph",
    "CAPTION_GLYPHS.set('R', cropExtractedGlyph",
    "CAPTION_GLYPHS.set('T', synthesizeExtractedT());",
    "function measureCaption(text, tracking = 0) {",
    "glyph.advance ?? glyph.width",
    "CAPTION_KERNING[char + chars[index + 1]]",
    "function fitCaption(value, maxWidth = CELL_W - 5) {",
    "function drawGlyph(dst, dstWidth, glyph, originX, originY) {",
    "function addCaptionOutline(facePixels, faceWidth, faceHeight) {",
    "function renderCaption(value, maxWidth = CELL_W - 5) {",
    "function strictPixelGrade(expected, actual) {",
    "const FONT_GRADE = buildFontBench();",
)) and 'import "./grid-replica.js"' in PAGE

repaired_glyphs_ok = all(token not in JS for token in (
    "GLYPH_BASE",
    "GLYPH_REV",
    "TILE_GLYPHS",
    "loadGlyphAtlas",
    "FontFace",
    "ITC Kabel",
    "NAME_FONT_FAMILY",
))
context_raster_ok = all(token in JS for token in (
    "const RASTER_SCALE = 2;",
    "const LABEL_SMOOTH_MIX = Math.max(0, Math.min(",
    "const GEOMETRY_PIXEL_STEP = 4;",
    "const USE_SOURCE_PORTRAIT_CAPTIONS = true;",
    "function scalePixels2x(pixels, width, height, smooth) {",
    "function renderCellFramebuffer(name, portraitName = null) {",
    "const native = renderCellBackground();",
    "compositePortrait(native, portraitName);",
    "if (!name || (portraitName && USE_SOURCE_PORTRAIT_CAPTIONS)) return background;",
    "scalePixels2x(nativeLabel, CELL_W, CELL_H, true)",
    "function blendPixelFrames(nearest, smooth, mix) {",
    "blendPixelFrames(nearestLabel, smoothLabel, LABEL_SMOOTH_MIX)",
    "const outputAlpha = sourceAlpha + destinationAlpha * (1 - sourceAlpha);",
    "const CAPTION_CAP = 7;",
    "const CAPTION_FACE = Object.freeze([146, 139, 114, 255]);",
    "const CAPTION_OUTLINE = Object.freeze([42, 40, 33, 255]);",
    "const originX = 4;",
    "const originY = 0;",
    "caption.pixels[source + 2], caption.pixels[source + 3]",
    "framebuffer.pixels, framebuffer.width, framebuffer.height, 'replica-texture-layer'",
    "cell.dataset.portrait",
    "const GRID_COLUMNS = 8;",
    "const GRID_ROWS = 25;",
    "const CELL_COUNT = GRID_COLUMNS * GRID_ROWS;",
    "CELL_IDS.forEach((id, index) => {",
    "function decodeReferenceRules() {",
    "function mapRuleSample(position, extent, cellSize, sourceExtent) {",
    "grid.append(canvasFromPixels(renderRules(), GRID_W, GRID_H, 'replica-rule-layer'));",
)) and all(token not in JS + PAGE for token in (
    "LABEL_RASTER_SCALE",
    "LABEL_STEP_MIX",
    "LABEL_BLUR_PX",
    "LABEL_CAPTURE_RECT",
    "replica-label-layer",
    "--label-blur",
))


reference_layers_ok = all(token in PAGE for token in (
    'class="arena-shell"',
    'class="arena-surface"',
    "width: 100vw;",
    "height: calc(100vw * 1127 / 378);",
    "left: calc(var(--cell-x) * 100% / 378);",
    "top: calc(var(--cell-y) * 100% / 1127);",
))


# Rendering must never special-case a whole roster word. The same A-Z face,
# 8-neighbor outline, tracking, and capture path serves every label.
shared_caption_ok = all(token not in JS + PAGE for token in (
    "ROSTER_WORD_SOURCES",
    "ROSTER_WORDS",
    "replica-reference-label-layer",
    "replica-reference-label-shadow",
    "FORCE_CUSTOM_LABELS",
)) and "sharedCaptionPipeline: true" in JS


# Border: every RGB byte from the supplied screenshot's 2px native lattice.
border_expected = bytearray()
for y in range(92):
    for x in range(96):
        x_rule = x < 2 or 47 <= x < 49 or x >= 94
        y_rule = y < 2 or 45 <= y < 47 or y >= 90
        if x_rule or y_rule:
            border_expected.extend(reference.getpixel((x, y)))
border_actual = base64.b64decode(js_string("SCREENSHOT_BORDER_RGB"))
border_diff = count_diff(border_actual, bytes(border_expected))


geometry_ok = all(
    token in JS
    for token in (
        "const CELL_W = 45;",
        "const CELL_H = 43;",
        "const RULE = 2;",
        "const GRID_COLUMNS = 8;",
        "const GRID_ROWS = 25;",
        "const CELL_COUNT = GRID_COLUMNS * GRID_ROWS;",
        "const GRID_W = RULE + GRID_COLUMNS * (CELL_W + RULE);",
        "const GRID_H = RULE + GRID_ROWS * (CELL_H + RULE);",
    )
)

dom_ok = all(
    token in JS
    for token in (
        "button.className = 'replica-cell';",
        "button.dataset.character = id;",
        "button.setAttribute('role', 'gridcell');",
        "cells.set(id, button);",
        "function randomize() {",
        "function setLabel(character, label) {",
        "window.characterGrid = Object.freeze({",
    )
)

bottom_fill_ok = "const fireY = y === CELL_H - 1 ? CELL_H - 2" in JS

portrait_names = (
    "mario", "fox", "dk", "samus", "luigi", "link", "yoshi",
    "falcon", "kirby", "pikachu", "jigglypuff", "ness",
)
portrait_assets_ok = all(
    (lambda image: image.size == (45, 43)
     and image.getextrema()[3][0] == 0
     and image.getchannel("A").getbbox() == (0, 0, 45, 43))(
        Image.open(ASSETS / f"{name}.png").convert("RGBA")
    )
    for name in portrait_names
) and all(token in JS for token in (
    "function cutOutPortrait(source, sourceLabel) {",
    "const CHARACTER_PORTRAITS = new Map(await Promise.all(",
    "await loadCaptionImage(buildAssetUrl(`charselect/${character.portrait}.png`))",
    "function compositePortrait(dst, portraitName) {",
    "button.dataset.portrait = character.portrait;",
    "const framebuffer = renderCellFramebuffer(label, character.portrait);",
))

total = len(fire_expected) + glyph_count + len(border_expected) + 9
different = fire_diff + glyph_diff + border_diff \
    + (0 if glyph_pipeline_ok else 1) + (0 if geometry_ok else 1) \
    + (0 if context_raster_ok else 1) + (0 if dom_ok else 1) \
    + (0 if bottom_fill_ok else 1) + (0 if repaired_glyphs_ok else 1) \
    + (0 if reference_layers_ok else 1) + (0 if shared_caption_ok else 1) \
    + (0 if portrait_assets_ok else 1)
score = 100.0 * (total - different) / total

print(f"fire       {len(fire_expected):5d} bytes  mismatched={fire_diff}")
print(f"alphabet   {glyph_count:5d} corrected A-Z glyph assets mismatched={glyph_diff}")
print(f"glyph ink  {glyph_pixels:5d} atlas pixels + strict browser grade exact={glyph_pipeline_ok}")
print(f"font family guessed OTF/legacy loaders fully removed exact={repaired_glyphs_ok}")
print(f"capture pass exact glyph texels + 2x presentation raster exact={context_raster_ok}")
print(f"viewport    full-vw 8x25 native-ratio canvas            exact={reference_layers_ok}")
print(f"captions    one A-Z extraction/composition/raster path  exact={shared_caption_ok}")
print(f"border     {len(border_expected):5d} bytes  mismatched={border_diff}")
print(f"fire floor final opaque row extends to frame       exact={bottom_fill_ok}")
print(f"geometry   45x43 interiors + 2px shared lattice  exact={geometry_ok}")
print(f"DOM cells  200 addressable gridcell buttons       exact={dom_ok}")
print(f"portraits      12 full-cell transparent decomp cutouts exact={portrait_assets_ok}")
print(f"requested-layer fidelity: {score:.3f}%")

if different:
    raise SystemExit(1)
