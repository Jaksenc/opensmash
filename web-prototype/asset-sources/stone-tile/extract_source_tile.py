#!/usr/bin/env python3
"""Extract the original 64x32 CSS stone tile from the local BattleShip O2R."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import zipfile

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "BattleShip/build-wasm/BattleShip.o2r"
RESOURCE = "reloc_menus/MNSelectCommon"
OUTPUT = Path(__file__).resolve().parent

LUS_HEADER_SIZE = 0x40
TEXTURE_OFFSET = 0x08
TEXTURE_SIZE = 64 * 32 // 2  # CI4: two palette indices per byte
PALETTE_OFFSET = 0x410
PALETTE_COLORS = 16
WIDTH = 64
HEIGHT = 32


def rgba5551(value: int) -> tuple[int, int, int, int]:
    """Convert one big-endian N64 RGBA5551 palette entry to RGBA8888."""
    red = (value >> 11) & 0x1F
    green = (value >> 6) & 0x1F
    blue = (value >> 1) & 0x1F
    alpha = value & 1
    return (
        (red << 3) | (red >> 2),
        (green << 3) | (green >> 2),
        (blue << 3) | (blue >> 2),
        255 if alpha else 0,
    )


def read_reloc_blob(archive_path: Path = ARCHIVE) -> bytes:
    with zipfile.ZipFile(archive_path) as archive:
        raw = archive.read(RESOURCE)

    offset = LUS_HEADER_SIZE
    file_id = struct.unpack_from("<I", raw, offset)[0]
    offset += 4
    reloc_intern, reloc_extern = struct.unpack_from("<HH", raw, offset)
    offset += 4
    extern_count = struct.unpack_from("<I", raw, offset)[0]
    offset += 4 + extern_count * 2
    data_size = struct.unpack_from("<I", raw, offset)[0]
    offset += 4

    if file_id != 21 or reloc_intern != 0x010E or reloc_extern != 0xFFFF:
        raise ValueError("unexpected MNSelectCommon resource header")
    return raw[offset : offset + data_size]


def main(archive_path: Path = ARCHIVE, output: Path = OUTPUT) -> None:
    """Write source-stone-tile{,-8x,-4up}.png + source-analysis.json to
    `output`, reading the MNSelectCommon reloc from `archive_path`."""
    archive_path, output = Path(archive_path), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    data = read_reloc_blob(archive_path)
    texture = data[TEXTURE_OFFSET : TEXTURE_OFFSET + TEXTURE_SIZE]
    palette_bytes = data[PALETTE_OFFSET : PALETTE_OFFSET + PALETTE_COLORS * 2]
    palette = [
        rgba5551(struct.unpack_from(">H", palette_bytes, index * 2)[0])
        for index in range(PALETTE_COLORS)
    ]

    pixels: list[tuple[int, int, int, int]] = []
    indices: list[int] = []
    for value in texture:
        indices.extend((value >> 4, value & 0x0F))
    pixels.extend(palette[index] for index in indices)

    tile = Image.new("RGBA", (WIDTH, HEIGHT))
    tile.putdata(pixels)
    tile.save(output / "source-stone-tile.png")
    tile.resize((WIDTH * 8, HEIGHT * 8), Image.Resampling.NEAREST).save(
        output / "source-stone-tile-8x.png"
    )

    four_up = Image.new("RGBA", (WIDTH * 2, HEIGHT * 2))
    for y in (0, HEIGHT):
        for x in (0, WIDTH):
            four_up.paste(tile, (x, y))
    four_up.resize((WIDTH * 16, HEIGHT * 16), Image.Resampling.NEAREST).save(
        output / "source-stone-tile-4up.png"
    )

    # Provenance label: "<checkout>/<archive name>" -- the o2r's build dir
    # (build-us / build-wasm ship identical reloc entries) is deliberately
    # left out so the record does not depend on which build produced it.
    archive_label = f"{archive_path.resolve().parent.parent.name}/{archive_path.name}"
    analysis = {
        "source_archive": archive_label,
        "source_resource": RESOURCE,
        "sprite_name": "StoneBackground",
        "width": WIDTH,
        "height": HEIGHT,
        "square": False,
        "format": "N64 CI4",
        "palette_format": "N64 RGBA5551",
        "wrap_mask_s": 6,
        "wrap_mask_t": 5,
        "used_palette_indices": sorted(set(indices)),
        "recreation_attempted": False,
        "stop_reason": "The source is a 64x32 rectangular tile, not a square tile.",
    }
    (output / "source-analysis.json").write_text(json.dumps(analysis, indent=2) + "\n")
    print(json.dumps(analysis, indent=2))


if __name__ == "__main__":
    main()
