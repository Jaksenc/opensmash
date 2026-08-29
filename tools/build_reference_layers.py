#!/usr/bin/env python3
"""Extract exact, transparent framebuffer layers from the supplied capture.

The reference PNG is a nearest-neighbour enlargement of a 198x191 captured
framebuffer.  Working on that collapsed framebuffer preserves its real
antialias/dither pixels; expanding through the capture's original run table
then gives the browser the same 1294x1246 sampling lattice as the source.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "charselect"
REFERENCE = ASSETS / "reference-2x2.png"
SOFT_LABEL_OUTPUT = ASSETS / "reference-labels-soft.png"
RULE_OUTPUT = ASSETS / "reference-rules.png"
BOTTOM_SHADOW_NAMES = ("mario", "yoshi")


def run_starts(image: np.ndarray, axis: int) -> np.ndarray:
    other_axes = tuple(index for index in range(image.ndim) if index != axis)
    changed = ~np.all(np.diff(image, axis=axis) == 0, axis=other_axes)
    return np.r_[0, np.where(changed)[0] + 1]


def components(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    found: list[list[tuple[int, int]]] = []
    for start_y, start_x in zip(*np.where(mask)):
        if seen[start_y, start_x]:
            continue
        queue = deque([(int(start_y), int(start_x))])
        seen[start_y, start_x] = True
        points: list[tuple[int, int]] = []
        while queue:
            y, x = queue.popleft()
            points.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if (
                    0 <= ny < height
                    and 0 <= nx < width
                    and mask[ny, nx]
                    and not seen[ny, nx]
                ):
                    seen[ny, nx] = True
                    queue.append((ny, nx))
        found.append(points)
    return found


def dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    result = mask.copy()
    for _ in range(radius):
        expanded = result.copy()
        expanded[1:] |= result[:-1]
        expanded[:-1] |= result[1:]
        expanded[:, 1:] |= result[:, :-1]
        expanded[:, :-1] |= result[:, 1:]
        result = expanded
    return result


def main() -> None:
    reference = np.asarray(Image.open(REFERENCE).convert("RGBA"))
    row_starts = run_starts(reference, 0)
    column_starts = run_starts(reference, 1)
    framebuffer = reference[row_starts][:, column_starts]
    if framebuffer.shape[:2] != (191, 198):
        raise RuntimeError(f"unexpected framebuffer shape: {framebuffer.shape[:2]}")

    rgb = framebuffer[..., :3].astype(np.float64)
    red, green, blue = (rgb[..., index] for index in range(3))
    luminance = rgb.mean(axis=2)
    neutral_face = (
        (luminance > 68)
        & (np.abs(red - green) < 29)
        & (green > red * 0.72)
        & (blue > red * 0.52)
        & (blue < red * 0.94)
    )

    # Tight word bands keep neutral portrait highlights out of the masks.
    bands = {
        "MARIO": (7, 4, 78, 27),
        "DK": (101, 5, 151, 27),
        "YOSHI": (7, 99, 76, 121),
        "KIRBY": (101, 99, 169, 121),
    }
    faces = np.zeros(neutral_face.shape, dtype=bool)
    counts: dict[str, int] = {}
    for name, (x0, y0, x1, y1) in bands.items():
        region = np.zeros_like(faces)
        region[y0:y1, x0:x1] = neutral_face[y0:y1, x0:x1]
        # Real letter faces are the substantial connected components. Tiny
        # isolated portrait/fire specks are deliberately excluded.
        kept = np.zeros_like(faces)
        for points in components(region):
            if len(points) < 3:
                continue
            for y, x in points:
                kept[y, x] = True
        counts[name] = int(kept.sum())
        faces |= kept

    # In the 2x captured framebuffer Mario's hat touches the word at row 23.
    # The actual caption ends on row 22; keeping later neutral pixels is what
    # produced the little white/pink "teeth" below I/O in earlier passes.
    faces[23:99] = False

    soft_two = dilate(faces, 2)
    soft_three = dilate(faces, 3)
    soft_two[24:99] = False
    soft_three[24:99] = False
    soft_two[119:] = False
    soft_three[119:] = False

    # Expand the mask through the exact non-uniform 6/7px run table used by
    # the supplied capture, then retain the already-rasterized source pixels.
    row_ends = np.r_[row_starts[1:], reference.shape[0]]
    column_ends = np.r_[column_starts[1:], reference.shape[1]]
    expanded_soft_two = np.zeros(reference.shape[:2], dtype=bool)
    expanded_soft_three = np.zeros(reference.shape[:2], dtype=bool)
    for y, (top, bottom) in enumerate(zip(row_starts, row_ends)):
        for x, (left, right) in enumerate(zip(column_starts, column_ends)):
            if soft_two[y, x]:
                expanded_soft_two[top:bottom, left:right] = True
            if soft_three[y, x]:
                expanded_soft_three[top:bottom, left:right] = True

    source_rgb = reference[..., :3].astype(np.float64)
    source_luminance = source_rgb.mean(axis=2)
    source_chroma = source_rgb.max(axis=2) - source_rgb.min(axis=2)
    source_red = source_rgb[..., 0]
    source_blue = source_rgb[..., 2]
    edge_color = (
        (source_luminance < 55)
        | (
            (source_luminance < 210)
            & (source_chroma < 40)
            & (source_blue > source_red * 0.45)
            & (source_blue < source_red * 0.96)
        )
    )
    soft_alpha = np.zeros(reference.shape[:2], dtype=np.uint8)
    soft_alpha[expanded_soft_three & edge_color] = 64
    soft_alpha[expanded_soft_three & ~edge_color] = 16
    soft_alpha[expanded_soft_two & edge_color] = 255
    soft_alpha[expanded_soft_two & ~edge_color] = 32
    # YOSHI's green portrait touches SHI.  Keep neutral/dark glyph shading,
    # but do not admit colored portrait texels into the reusable text mask.
    bottom = slice(row_starts[99], reference.shape[0])
    soft_alpha[bottom] = np.where(edge_color[bottom], soft_alpha[bottom], 0)

    soft = reference.copy()
    soft[..., 3] = soft_alpha
    Image.fromarray(soft, "RGBA").save(SOFT_LABEL_OUTPUT, optimize=True)

    # Isolate the real word silhouettes before the browser sees them.  CSS
    # clipping creates its own straight antialiased boundary, so these files
    # contain no rectangular clip at all: just the last two extracted glyph
    # rows, shifted down one native texel to act as the missing dark contour.
    for name in BOTTOM_SHADOW_NAMES:
        word = np.asarray(
            Image.open(ASSETS / f"grid_{name}.png").convert("RGBA")
        ).copy()
        shadow = np.zeros_like(word)
        if name == "yoshi":
            # Only SHI is occluded. Darken its existing final row and carry a
            # softer copy one texel lower; Y/O already match the clean source.
            shadow[9, 16:] = word[9, 16:]
            shadow[10, 16:] = word[9, 16:]
            shadow[9, 16:, 3] = np.minimum(
                255, np.round(shadow[9, 16:, 3] * 1.8)
            ).astype(np.uint8)
            shadow[10, 16:, 3] = np.round(
                shadow[10, 16:, 3] * 0.8
            ).astype(np.uint8)
        else:
            shadow[10:11] = word[9:10]
            shadow[10, :, 3] = np.minimum(
                255, np.round(shadow[10, :, 3] * 1.25)
            ).astype(np.uint8)
        shadow[shadow[..., 3] > 0, :3] = (48, 45, 37)
        Image.fromarray(shadow, "RGBA").save(
            ASSETS / f"grid_{name}_bottom.png", optimize=True
        )

    height, width = reference.shape[:2]
    native_x = np.floor(np.arange(width) * 96 / width).astype(int)
    native_y = np.floor(np.arange(height) * 92 / height).astype(int)
    x_rule = (native_x < 2) | ((native_x >= 47) & (native_x < 49)) | (native_x >= 94)
    y_rule = (native_y < 2) | ((native_y >= 45) & (native_y < 47)) | (native_y >= 90)
    rule_mask = y_rule[:, None] | x_rule[None, :]
    rules = reference.copy()
    rules[..., 3] = np.where(rule_mask, 255, 0).astype(np.uint8)
    Image.fromarray(rules, "RGBA").save(RULE_OUTPUT, optimize=True)
    print(
        f"framebuffer={framebuffer.shape[1]}x{framebuffer.shape[0]} "
        f"labels={counts} outputs={SOFT_LABEL_OUTPUT.relative_to(ROOT)},"
        f"bottom-shadows={len(BOTTOM_SHADOW_NAMES)},{RULE_OUTPUT.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
