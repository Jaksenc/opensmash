"""Remove the printed Nintendo 64 branding from derived console GLBs.

The console badge is flat geometry. Its wordmark and multicolor N are baked
only into the diffuse texture, so this edits that embedded PNG while leaving
the mesh buffers, UVs, normal map, AO map, and material settings untouched.

Usage:
    python3 tools/remove_n64_console_branding.py model.glb [model.glb ...]
"""

from __future__ import annotations

import argparse
import io
import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from flatten_n64_controller_emboss import read_glb, write_glb


# Pixel bounds in the derived 1024x1024 diffuse atlas. They surround only the
# multicolor N and the white Nintendo 64 wordmark, not the dark molded badge.
REFERENCE_SIZE = (1024, 1024)
BRANDING_BOXES = (
    (211, 838, 252, 874),
    (187, 870, 273, 892),
)


def diffuse_buffer_view(document: dict) -> int:
    for image in document.get("images", []):
        if image.get("name", "").casefold() == "diffuse":
            return image["bufferView"]

    for material in document.get("materials", []):
        texture_info = material.get("pbrMetallicRoughness", {}).get(
            "baseColorTexture"
        )
        if texture_info is None:
            continue
        texture = document["textures"][texture_info["index"]]
        return document["images"][texture["source"]]["bufferView"]

    raise ValueError("GLB has no embedded diffuse/base-color texture")


def remove_branding(image: Image.Image) -> tuple[Image.Image, np.ndarray]:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    rgb = rgba[..., :3]
    height, width = rgb.shape[:2]
    ref_width, ref_height = REFERENCE_SIZE

    channel_max = rgb.max(axis=2).astype(np.int16)
    channel_min = rgb.min(axis=2).astype(np.int16)
    luminance = rgb.mean(axis=2)
    printed_pixel = ((channel_max - channel_min) > 16) | (luminance > 56)

    mask = np.zeros((height, width), dtype=np.uint8)
    for left, top, right, bottom in BRANDING_BOXES:
        left = round(left * width / ref_width)
        right = round(right * width / ref_width)
        top = round(top * height / ref_height)
        bottom = round(bottom * height / ref_height)
        mask[top:bottom, left:right] = np.where(
            printed_pixel[top:bottom, left:right], 255, 0
        ).astype(np.uint8)

    # Include the anti-aliased fringe around detected ink without touching the
    # badge outline or the clean surface beyond the two branding areas.
    dilation = max(1, round(max(width, height) / 1024))
    mask = cv2.dilate(
        mask,
        np.ones((dilation * 2 + 1, dilation * 2 + 1), dtype=np.uint8),
        iterations=1,
    )
    radius = max(2, round(4 * max(width, height) / 1024))
    rgba[..., :3] = cv2.inpaint(rgb, mask, radius, cv2.INPAINT_TELEA)
    return Image.fromarray(rgba, "RGBA"), mask


def encode_png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def patch_glb(path: Path) -> int:
    document, binary = read_glb(path)
    view_index = diffuse_buffer_view(document)
    view = document["bufferViews"][view_index]
    start = view.get("byteOffset", 0)
    end = start + view["byteLength"]

    with Image.open(io.BytesIO(binary[start:end])) as image:
        cleaned, mask = remove_branding(image)
        replacement = encode_png(cleaned)

    original_offsets = [item.get("byteOffset", 0) for item in document["bufferViews"]]
    rebuilt = binary[:start] + replacement + binary[end:]
    difference = len(replacement) - (end - start)
    view["byteLength"] = len(replacement)
    for index, item in enumerate(document["bufferViews"]):
        if index == view_index:
            continue
        if original_offsets[index] >= end:
            item["byteOffset"] = original_offsets[index] + difference

    temporary = path.with_name(f".{path.name}.branding-clean.tmp")
    write_glb(temporary, document, rebuilt)
    os.replace(temporary, path)
    return int(np.count_nonzero(mask))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+", type=Path)
    args = parser.parse_args()

    for model in args.models:
        changed = patch_glb(model.resolve())
        print(f"Cleaned {changed} diffuse texels in {model}")


if __name__ == "__main__":
    main()
