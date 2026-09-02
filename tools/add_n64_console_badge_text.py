"""Add the colored Comic Sans ``fun`` wordmark to the console badge.

The text is composited into the embedded diffuse PNG. All mesh, UV, normal,
AO, material, and scene data in the GLB remain untouched.

Usage:
    python3 tools/add_n64_console_badge_text.py model.glb [model.glb ...]
"""

from __future__ import annotations

import argparse
import io
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from flatten_n64_controller_emboss import read_glb, write_glb
from remove_n64_console_branding import diffuse_buffer_view


REFERENCE_SIZE = (1024, 1024)
BADGE_CENTER = (230, 865)
FONT_SIZE = 36
TEXT = "fun"
LETTER_COLORS = (
    "#FF3B30",
    "#FFD000",
    "#008CFF",
)
FONT_PATH = Path("/System/Library/Fonts/Supplemental/Comic Sans MS.ttf")
SUPERSAMPLE = 4


def colored_word(width: int, height: int) -> Image.Image:
    scale = max(width / REFERENCE_SIZE[0], height / REFERENCE_SIZE[1])
    font = ImageFont.truetype(
        str(FONT_PATH), max(1, round(FONT_SIZE * scale * SUPERSAMPLE))
    )
    bbox = font.getbbox(TEXT)
    word_width = max(1, bbox[2] - bbox[0])
    word_height = max(1, bbox[3] - bbox[1])
    word = Image.new("RGBA", (word_width, word_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(word)

    cursor = -bbox[0]
    for character, color in zip(TEXT, LETTER_COLORS, strict=True):
        draw.text((round(cursor), -bbox[1]), character, font=font, fill=color)
        cursor += font.getlength(character)

    target_size = (
        max(1, round(word.width / SUPERSAMPLE)),
        max(1, round(word.height / SUPERSAMPLE)),
    )
    word = word.resize(target_size, Image.Resampling.LANCZOS)

    # glTF's texture-coordinate convention vertically flips this atlas image
    # when it is sampled. Store the artwork upside down here so it reads
    # normally on the rendered front of the console.
    return word.transpose(Image.Transpose.FLIP_TOP_BOTTOM)


def add_badge_text(image: Image.Image) -> Image.Image:
    canvas = image.convert("RGBA")
    width, height = canvas.size
    word = colored_word(width, height)
    center_x = round(BADGE_CENTER[0] * width / REFERENCE_SIZE[0])
    center_y = round(BADGE_CENTER[1] * height / REFERENCE_SIZE[1])
    position = (
        round(center_x - word.width * 0.5),
        round(center_y - word.height * 0.5),
    )
    canvas.alpha_composite(word, position)
    return canvas


def encode_png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def patch_glb(path: Path) -> None:
    if not FONT_PATH.is_file():
        raise FileNotFoundError(f"Comic Sans MS is missing: {FONT_PATH}")

    document, binary = read_glb(path)
    view_index = diffuse_buffer_view(document)
    view = document["bufferViews"][view_index]
    start = view.get("byteOffset", 0)
    end = start + view["byteLength"]

    with Image.open(io.BytesIO(binary[start:end])) as image:
        replacement = encode_png(add_badge_text(image))

    original_offsets = [item.get("byteOffset", 0) for item in document["bufferViews"]]
    rebuilt = binary[:start] + replacement + binary[end:]
    difference = len(replacement) - (end - start)
    view["byteLength"] = len(replacement)
    for index, item in enumerate(document["bufferViews"]):
        if index != view_index and original_offsets[index] >= end:
            item["byteOffset"] = original_offsets[index] + difference

    temporary = path.with_name(f".{path.name}.badge-text.tmp")
    write_glb(temporary, document, rebuilt)
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+", type=Path)
    args = parser.parse_args()

    for model in args.models:
        patch_glb(model.resolve())
        print(f"Added colored Comic Sans {TEXT!r} badge text to {model}")


if __name__ == "__main__":
    main()
