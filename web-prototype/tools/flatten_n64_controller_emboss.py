"""Remove the Nintendo badge emboss from the N64 controller's packed GLB textures.

The controller shell is already flat geometry. The badge is baked into the
normal and metallic/roughness maps, so this script inpaints only that atlas
region and leaves every mesh buffer untouched.

Usage:
    python3 tools/flatten_n64_controller_emboss.py source.glb output.glb
"""

from __future__ import annotations

import argparse
import io
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image


GLB_MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942

# Atlas bounds around the complete oval badge, with enough clean surface for
# the feather to finish before reaching the baked lettering.
BADGE_BOX = (420, 920, 580, 980)
TEXTURE_NAMES = ("normal", "metallicRoughness")


def read_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    magic, version, total_length = struct.unpack_from("<III", data)
    if magic != GLB_MAGIC or version != 2 or total_length != len(data):
        raise ValueError(f"Not a valid glTF 2.0 binary: {path}")

    chunks: dict[int, bytes] = {}
    cursor = 12
    while cursor < len(data):
        chunk_length, chunk_type = struct.unpack_from("<II", data, cursor)
        cursor += 8
        chunks[chunk_type] = data[cursor : cursor + chunk_length]
        cursor += chunk_length

    document = json.loads(chunks[JSON_CHUNK].rstrip(b" \0"))
    logical_bin_length = document["buffers"][0]["byteLength"]
    return document, chunks[BIN_CHUNK][:logical_bin_length]


def image_buffer_view(document: dict, texture_name: str) -> int:
    material = document["materials"][0]
    if texture_name == "normal":
        texture_index = material["normalTexture"]["index"]
    else:
        texture_index = material["pbrMetallicRoughness"][
            "metallicRoughnessTexture"
        ]["index"]
    image_index = document["textures"][texture_index]["source"]
    return document["images"][image_index]["bufferView"]


def polynomial_surface(
    image: np.ndarray, box: tuple[int, int, int, int]
) -> np.ndarray:
    """Fit the slow surface variation around a box and evaluate it inside."""
    left, top, right, bottom = box
    height, width = image.shape[:2]
    margin_x = 24
    margin_y = 34
    sample_left = max(0, left - margin_x)
    sample_right = min(width, right + margin_x)
    sample_top = max(0, top - margin_y)
    sample_bottom = min(height, bottom + 12)

    yy, xx = np.mgrid[sample_top:sample_bottom, sample_left:sample_right]
    outside = (xx < left) | (xx >= right) | (yy < top) | (yy >= bottom)
    sx = (xx[outside] - (left + right) * 0.5) / (right - left)
    sy = (yy[outside] - (top + bottom) * 0.5) / (bottom - top)
    design = np.column_stack(
        (
            np.ones_like(sx),
            sx,
            sy,
            sx * sx,
            sx * sy,
            sy * sy,
        )
    )

    target_y, target_x = np.mgrid[top:bottom, left:right]
    tx = (target_x - (left + right) * 0.5) / (right - left)
    ty = (target_y - (top + bottom) * 0.5) / (bottom - top)
    target_design = np.stack(
        (
            np.ones_like(tx),
            tx,
            ty,
            tx * tx,
            tx * ty,
            ty * ty,
        ),
        axis=-1,
    )

    fitted = np.empty((*target_x.shape, image.shape[2]), dtype=np.float64)
    for channel in range(image.shape[2]):
        values = image[
            sample_top:sample_bottom, sample_left:sample_right, channel
        ][outside]
        coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
        fitted[..., channel] = target_design @ coefficients
    return fitted


def flatten_badge(image: Image.Image) -> Image.Image:
    array = np.asarray(image.convert("RGB"), dtype=np.float64).copy()
    left, top, right, bottom = BADGE_BOX
    fill = polynomial_surface(array, BADGE_BOX)

    # Reuse only the tiny high-frequency surface variation from a clean patch
    # above the badge, while the polynomial fit supplies the correct local
    # gradient/curvature for the destination.
    patch_height = bottom - top
    source_top = top - patch_height - 10
    source = array[source_top : source_top + patch_height, left:right]
    source_smooth = polynomial_surface(
        array, (left, source_top, right, source_top + patch_height)
    )
    fill += (source - source_smooth) * 0.65

    yy, xx = np.mgrid[top:bottom, left:right]
    edge_distance = np.minimum.reduce(
        (xx - left, right - 1 - xx, yy - top, bottom - 1 - yy)
    ).astype(np.float64)
    alpha = np.clip(edge_distance / 9.0, 0.0, 1.0)
    alpha = alpha * alpha * (3.0 - 2.0 * alpha)
    alpha = alpha[..., None]

    original = array[top:bottom, left:right]
    array[top:bottom, left:right] = original * (1.0 - alpha) + fill * alpha
    return Image.fromarray(np.clip(np.rint(array), 0, 255).astype(np.uint8), "RGB")


def encode_png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def write_glb(path: Path, document: dict, binary: bytes) -> None:
    document["buffers"][0]["byteLength"] = len(binary)
    json_data = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_data += b" " * (-len(json_data) % 4)
    bin_data = binary + b"\0" * (-len(binary) % 4)
    total_length = 12 + 8 + len(json_data) + 8 + len(bin_data)

    output = io.BytesIO()
    output.write(struct.pack("<III", GLB_MAGIC, 2, total_length))
    output.write(struct.pack("<II", len(json_data), JSON_CHUNK))
    output.write(json_data)
    output.write(struct.pack("<II", len(bin_data), BIN_CHUNK))
    output.write(bin_data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(output.getvalue())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    document, binary = read_glb(args.source)
    original_offsets = [view.get("byteOffset", 0) for view in document["bufferViews"]]
    replacements: list[tuple[int, int, int, bytes]] = []

    for texture_name in TEXTURE_NAMES:
        view_index = image_buffer_view(document, texture_name)
        view = document["bufferViews"][view_index]
        start = view.get("byteOffset", 0)
        end = start + view["byteLength"]
        with Image.open(io.BytesIO(binary[start:end])) as image:
            replacement = encode_png(flatten_badge(image))
        replacements.append((start, end, view_index, replacement))

    rebuilt = bytearray()
    cursor = 0
    for start, end, view_index, replacement in sorted(replacements):
        rebuilt.extend(binary[cursor:start])
        new_offset = len(rebuilt)
        rebuilt.extend(replacement)
        document["bufferViews"][view_index]["byteOffset"] = new_offset
        document["bufferViews"][view_index]["byteLength"] = len(replacement)
        cursor = end
    rebuilt.extend(binary[cursor:])

    replaced_indices = {item[2] for item in replacements}
    for view_index, view in enumerate(document["bufferViews"]):
        if view_index in replaced_indices:
            continue
        old_offset = original_offsets[view_index]
        shift = sum(
            len(replacement) - (end - start)
            for start, end, _, replacement in replacements
            if end <= old_offset
        )
        if old_offset or "byteOffset" in view:
            view["byteOffset"] = old_offset + shift

    write_glb(args.output, document, bytes(rebuilt))


if __name__ == "__main__":
    main()
