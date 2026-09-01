#!/usr/bin/env python3
"""Convert one low-poly generated GLB prop into an OSB item model.

The selected source axis is mapped onto an item-local axis.  A full 3D hold
point is moved to the drawable origin so the engine can attach that point—not
the model's bounding-box center—to the stock item's hand anchor.

Example:
  python3 pipeline/convert_item.py bat.glb bat.osb --axis y --length 420 \
    --hold-point auto
"""

import argparse
import io
import json
import math
import os
import struct
import tempfile

from PIL import Image

try:
    from .convert_glb import load_glb, write_binary
except ImportError:
    from convert_glb import load_glb, write_binary


COMPONENTS = {
    5120: ("b", 1),
    5121: ("B", 1),
    5122: ("h", 2),
    5123: ("H", 2),
    5125: ("I", 4),
    5126: ("f", 4),
}
COMPONENT_COUNTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
NORMALIZED_DIVISORS = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}


def read_accessor(gltf, binary, index):
    accessor = gltf["accessors"][index]
    if "sparse" in accessor:
        raise ValueError("sparse GLB accessors are not supported by the item MVP")
    view = gltf["bufferViews"][accessor["bufferView"]]
    component_type = accessor["componentType"]
    component_format, component_size = COMPONENTS[component_type]
    component_count = COMPONENT_COUNTS[accessor["type"]]
    packed_size = component_size * component_count
    stride = view.get("byteStride", packed_size)
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    fmt = "<" + component_format * component_count
    values = []

    for i in range(accessor["count"]):
        value = list(struct.unpack_from(fmt, binary, offset + i * stride))
        if accessor.get("normalized") and component_type in NORMALIZED_DIVISORS:
            divisor = NORMALIZED_DIVISORS[component_type]
            value = [max(-1.0, v / divisor) for v in value]
        values.append(tuple(value))
    return values


def load_base_color_image(gltf, binary, primitive):
    material_index = primitive.get("material")
    if material_index is None:
        return None, (1.0, 1.0, 1.0, 1.0)
    material = gltf.get("materials", [])[material_index]
    pbr = material.get("pbrMetallicRoughness") or {}
    factor = tuple(pbr.get("baseColorFactor", (1.0, 1.0, 1.0, 1.0)))
    texture_info = pbr.get("baseColorTexture")
    if texture_info is None:
        return None, factor
    image_index = gltf["textures"][texture_info["index"]]["source"]
    image_desc = gltf["images"][image_index]
    if "bufferView" not in image_desc:
        raise ValueError("external GLB images are not supported; export an embedded GLB")
    view = gltf["bufferViews"][image_desc["bufferView"]]
    start = view.get("byteOffset", 0)
    raw = binary[start:start + view["byteLength"]]
    return Image.open(io.BytesIO(raw)).convert("RGB"), factor


def sample_color(image, uv, factor, vertex_color=None):
    rgb = [255.0, 255.0, 255.0]
    if image is not None and uv is not None:
        u = min(0.999999, max(0.0, uv[0]))
        v = min(0.999999, max(0.0, uv[1]))
        rgb = list(image.getpixel((min(image.width - 1, int(u * image.width)),
                                   min(image.height - 1, int((1.0 - v) * image.height)))))
    for i in range(3):
        rgb[i] *= factor[i]
        if vertex_color is not None:
            component = vertex_color[i]
            rgb[i] *= component if isinstance(component, float) else component / 255.0
    return [max(0, min(255, int(round(channel)))) for channel in rgb]


def make_textured_lit_atlas(image, factor, uvs, triangles, output, size):
    """Apply the proven fighter texture cleanup at item scale.

    Provider base-color maps contain baked AO/highlights and narrow empty UV
    gutters.  Keeping those texels verbatim double-lights the prop and makes
    dark gutter colors bleed into silhouettes after downscaling.  A guided
    filter removes only low-amplitude value mottle, then UV-island dilation
    fills the gutters before the intentionally tiny N64-style atlas is made.
    """
    import numpy as np
    from PIL import ImageDraw
    from scipy.ndimage import uniform_filter

    rgb = np.asarray(image.convert("RGB"), np.float32).copy()
    rgb *= np.asarray(factor[:3], np.float32)[None, None, :]
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    cleaned = Image.fromarray(rgb, "RGB")

    hsv = np.asarray(cleaned.convert("HSV"), np.uint8).copy()
    value = hsv[..., 2].astype(np.float64) / 255.0
    radius = max(8, cleaned.size[0] // 64)
    epsilon = (14.0 / 255.0) ** 2
    mean = uniform_filter(value, 2 * radius + 1, mode="nearest")
    variance = np.maximum(
        uniform_filter(value * value, 2 * radius + 1, mode="nearest") - mean * mean,
        0.0,
    )
    coeff = variance / (variance + epsilon)
    intercept = mean * (1.0 - coeff)
    filtered = (uniform_filter(coeff, 2 * radius + 1, mode="nearest") * value +
                uniform_filter(intercept, 2 * radius + 1, mode="nearest"))
    hsv[..., 2] = np.clip(filtered * 255.0, 0, 255).astype(np.uint8)
    cleaned = Image.fromarray(hsv, "HSV").convert("RGB")

    work_size = max(512, size * 8)
    base = cleaned.resize((work_size, work_size), Image.Resampling.LANCZOS)
    coverage = Image.new("L", (work_size, work_size), 0)
    draw = ImageDraw.Draw(coverage)
    for triangle in triangles:
        draw.polygon([
            (min(work_size - 1, max(0, uvs[index][0] * work_size)),
             min(work_size - 1, max(0, uvs[index][1] * work_size)))
            for index in triangle
        ], fill=255)

    pixels = np.asarray(base, np.float32).copy()
    known = np.asarray(coverage, np.float32) / 255.0
    for _ in range(max(12, work_size // size * 2)):
        neighbor_count = (np.roll(known, 1, 0) + np.roll(known, -1, 0) +
                          np.roll(known, 1, 1) + np.roll(known, -1, 1))
        neighbor_color = (
            np.roll(pixels * known[..., None], 1, 0) +
            np.roll(pixels * known[..., None], -1, 0) +
            np.roll(pixels * known[..., None], 1, 1) +
            np.roll(pixels * known[..., None], -1, 1)
        )
        grow = (neighbor_count > 0) & (known < 0.5)
        pixels[grow] = neighbor_color[grow] / neighbor_count[grow, None]
        known[neighbor_count > 0] = 1.0

    atlas = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), "RGB")
    atlas = atlas.resize((size, size), Image.Resampling.LANCZOS)
    atlas.save(output)
    return atlas


def smooth_welded_normals(positions, triangles):
    """Area-weight smooth normals across UV-seam duplicate positions."""
    groups = {}
    for index, position in enumerate(positions):
        key = tuple(round(component, 5) for component in position)
        groups.setdefault(key, []).append(index)

    accum = [[0.0, 0.0, 0.0] for _ in positions]
    for a, b, c in triangles:
        pa, pb, pc = positions[a], positions[b], positions[c]
        edge_a = [pb[i] - pa[i] for i in range(3)]
        edge_b = [pc[i] - pa[i] for i in range(3)]
        normal = [edge_a[1] * edge_b[2] - edge_a[2] * edge_b[1],
                  edge_a[2] * edge_b[0] - edge_a[0] * edge_b[2],
                  edge_a[0] * edge_b[1] - edge_a[1] * edge_b[0]]
        for index in (a, b, c):
            for component in range(3):
                accum[index][component] += normal[component]

    normals = [None] * len(positions)
    for group in groups.values():
        total = [sum(accum[index][component] for index in group)
                 for component in range(3)]
        length = math.sqrt(sum(component * component for component in total)) or 1e-9
        normal = [component / length for component in total]
        for index in group:
            normals[index] = normal
    return normals


def pack_rgba16_dithered(atlas):
    """Pack a small atlas as N64 RGBA16 with fighter-pipeline dithering."""
    import numpy as np

    rgba = np.asarray(atlas.convert("RGBA"), np.float32)
    bayer = (np.array([[0, 8, 2, 10], [12, 4, 14, 6],
                       [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) /
             16.0 - 0.46875) * 8.0
    height, width = rgba.shape[:2]
    offset = np.tile(bayer, (height // 4 + 1, width // 4 + 1))[:height, :width]
    luma = rgba[..., :3].max(2)
    gate = np.clip((luma - 48.0) / 48.0, 0.0, 1.0)
    rgb = np.clip(rgba[..., :3] + (offset * gate)[..., None], 0, 255).astype(np.uint16) >> 3
    alpha = (rgba[..., 3] >= 128).astype(np.uint16)
    packed = (rgb[..., 0] << 11) | (rgb[..., 1] << 6) | (rgb[..., 2] << 1) | alpha
    return packed.astype(">u2").tobytes()


def write_textured_lit_binary(output, vertices, triangles, atlas):
    """Write one-part OSB4: textured geometry with real vertex normals."""
    texture_width, texture_height = atlas.size
    batches = []
    current_map, current_vertices, current_triangles = {}, [], []
    for triangle in triangles:
        needed = [index for index in triangle if index not in current_map]
        if len(current_vertices) + len(needed) > 30:
            if current_triangles:
                batches.append((current_vertices, current_triangles))
            current_map, current_vertices, current_triangles = {}, [], []
            needed = list(triangle)
        for index in needed:
            current_map[index] = len(current_vertices)
            current_vertices.append(vertices[index])
        current_triangles.append(tuple(current_map[index] for index in triangle))
    if current_triangles:
        batches.append((current_vertices, current_triangles))

    with open(output, "wb") as file:
        file.write(b"OSB4")
        file.write(struct.pack("<III", 1, texture_width, texture_height))
        file.write(pack_rgba16_dithered(atlas))
        file.write(struct.pack("<II", 0, len(batches)))
        for batch_vertices, batch_triangles in batches:
            file.write(struct.pack("<II", len(batch_vertices), len(batch_triangles)))
            for vertex in batch_vertices:
                x, y, z, u, v, nx, ny, nz = vertex
                s = max(0, min(texture_width * 32 - 1,
                               int(round(u * texture_width * 32))))
                t = max(0, min(texture_height * 32 - 1,
                               int(round(v * texture_height * 32))))
                file.write(struct.pack(
                    "<hhhhhbbbB", int(round(x)), int(round(y)), int(round(z)), s, t,
                    int(max(-127, min(127, nx * 127))),
                    int(max(-127, min(127, ny * 127))),
                    int(max(-127, min(127, nz * 127))), 0,
                ))
            for triangle in batch_triangles:
                file.write(struct.pack("<BBBB", *triangle, 0))
    print(f"batches: {len(batches)}, atlas {texture_width}x{texture_height}")


def remap_position(position, axis, target_axis, roll):
    source_index = {"x": 0, "y": 1, "z": 2}[axis]
    target_index = {"x": 0, "y": 1, "z": 2}[target_axis]
    remaining_source = [i for i in range(3) if i != source_index]
    remaining_target = [i for i in range(3) if i != target_index]
    mapped = [0.0, 0.0, 0.0]
    mapped[target_index] = position[source_index]
    for destination, source in zip(remaining_target, remaining_source):
        mapped[destination] = position[source]

    # Rotate around the item's chosen game-space length axis so broad props
    # can present their useful face without changing grip/tip direction.
    radians = math.radians(roll)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    if target_axis == "x":
        mapped[1], mapped[2] = (mapped[1] * cosine + mapped[2] * sine,
                                -mapped[1] * sine + mapped[2] * cosine)
    elif target_axis == "z":
        mapped[0], mapped[1] = (mapped[0] * cosine + mapped[1] * sine,
                                -mapped[0] * sine + mapped[1] * cosine)
    else:
        mapped[0], mapped[2] = (mapped[0] * cosine + mapped[2] * sine,
                                -mapped[0] * sine + mapped[2] * cosine)
    return mapped


def percentile(values, amount):
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot measure an empty handle sample")
    index = (len(ordered) - 1) * amount
    low = int(math.floor(index))
    high = int(math.ceil(index))
    if low == high:
        return ordered[low]
    blend = index - low
    return ordered[low] * (1.0 - blend) + ordered[high] * blend


def infer_handle_point(positions, target_index, inset):
    """Find the narrow end of a tool and return its full 3D grip point.

    Bounds-only pivots fail for clubs, hammers, and axes because their bulky
    heads pull the two transverse centers away from the shaft.  Compare robust
    cross-sections at both ends, choose the narrower end, then take the median
    center of that end's vertices.  The small axial inset puts the glove around
    the handle rather than exactly against its cap.
    """
    axis_min = min(position[target_index] for position in positions)
    axis_max = max(position[target_index] for position in positions)
    span = axis_max - axis_min
    transverse = [index for index in range(3) if index != target_index]
    band = 0.12
    samples = {
        "base": [position for position in positions
                 if position[target_index] <= axis_min + span * band],
        "tip": [position for position in positions
                if position[target_index] >= axis_max - span * band],
    }

    def score(sample):
        widths = [percentile([position[index] for position in sample], 0.9) -
                  percentile([position[index] for position in sample], 0.1)
                  for index in transverse]
        return math.sqrt(max(widths[0], 1e-9) * max(widths[1], 1e-9))

    scores = {side: score(sample) for side, sample in samples.items()}
    side = min(scores, key=scores.get)
    point = [0.0, 0.0, 0.0]
    point[target_index] = (axis_min + span * inset if side == "base"
                           else axis_max - span * inset)
    for index in transverse:
        point[index] = percentile([position[index] for position in samples[side]], 0.5)
    return point, side, scores


def convert(args):
    gltf, binary = load_glb(args.input)
    meshes = gltf.get("meshes") or []
    if len(meshes) != 1 or len(meshes[0].get("primitives", [])) != 1:
        raise ValueError("item MVP requires exactly one mesh with one primitive")
    primitive = meshes[0]["primitives"][0]
    if primitive.get("mode", 4) != 4:
        raise ValueError("item MVP requires a triangle-list primitive")

    attributes = primitive["attributes"]
    positions = read_accessor(gltf, binary, attributes["POSITION"])
    uvs = read_accessor(gltf, binary, attributes["TEXCOORD_0"]) if "TEXCOORD_0" in attributes else None
    colors = read_accessor(gltf, binary, attributes["COLOR_0"]) if "COLOR_0" in attributes else None
    if "indices" in primitive:
        indices = [value[0] for value in read_accessor(gltf, binary, primitive["indices"])]
    else:
        indices = list(range(len(positions)))
    if len(indices) % 3:
        raise ValueError("triangle index count is not divisible by three")

    triangles = [indices[i:i + 3] for i in range(0, len(indices), 3)]
    triangles = [triangle for triangle in triangles if len(set(triangle)) == 3]
    if len(triangles) > args.max_tris:
        raise ValueError(f"model has {len(triangles)} triangles; regenerate or simplify to <= {args.max_tris}")

    target_index = {"x": 0, "y": 1, "z": 2}[args.target_axis]
    mapped = [remap_position(position, args.axis, args.target_axis, args.roll)
              for position in positions]
    if args.flip:
        for position in mapped:
            position[target_index] *= -1.0
    axis_min = min(position[target_index] for position in mapped)
    axis_max = max(position[target_index] for position in mapped)
    source_length = axis_max - axis_min
    if source_length <= 1e-8:
        raise ValueError("selected item axis has zero length")
    scale = args.length / source_length
    centers = [(min(position[i] for position in mapped) +
                max(position[i] for position in mapped)) * 0.5 for i in range(3)]
    hold_mode = args.hold_point or args.pivot or "auto"
    hold_note = hold_mode
    if args.hold_position is not None:
        hold = remap_position(args.hold_position, args.axis, args.target_axis, args.roll)
        if args.flip:
            hold[target_index] *= -1.0
        hold_note = "explicit"
    elif hold_mode == "auto":
        hold, handle_side, handle_scores = infer_handle_point(
            mapped, target_index, args.hold_inset)
        hold_note = (f"auto:{handle_side} "
                     f"(base={handle_scores['base']:.4g}, tip={handle_scores['tip']:.4g})")
    else:
        hold = list(centers)
        hold[target_index] = {
            "base": axis_min,
            "center": (axis_min + axis_max) * 0.5,
            "tip": axis_max,
        }[hold_mode]

    image, factor = load_base_color_image(gltf, binary, primitive)
    normals = smooth_welded_normals(mapped, triangles) if args.shading == "textured-lit" else None
    vertices = []
    for index, position in enumerate(mapped):
        offsets = [args.offset_x, args.offset_y, args.offset_z]
        xyz = [((position[i] - hold[i]) * scale +
                offsets[i]) for i in range(3)]
        if max(abs(value) for value in xyz) > 32760:
            raise ValueError("scaled item exceeds OSB2 signed-16-bit coordinates")
        if args.shading == "textured-lit":
            if image is None or uvs is None:
                raise ValueError("textured-lit items require an embedded base-color texture and UVs")
            uv = [min(1.0, max(0.0, component)) for component in uvs[index][:2]]
            vertices.append([*xyz, *uv, *normals[index]])
        else:
            color = sample_color(image, uvs[index] if uvs else None, factor,
                                 colors[index] if colors else None)
            vertices.append([*xyz, *color])

    output_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(output_dir, exist_ok=True)
    if args.shading == "textured-lit":
        atlas_path = os.path.splitext(os.path.abspath(args.output))[0] + "-atlas.png"
        atlas = make_textured_lit_atlas(image, factor, uvs, triangles,
                                        atlas_path, args.texture_size)
        write_textured_lit_binary(args.output, vertices, triangles, atlas)
    else:
        bundle = {"parts": [{"joint": 0, "verts": vertices, "tris": triangles}]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", dir=output_dir, delete=False) as temp:
            json.dump(bundle, temp)
            temp_path = temp.name
        try:
            write_binary(temp_path, args.output)
        finally:
            os.unlink(temp_path)
    print(f"item: {len(vertices)} vertices, {len(triangles)} triangles, "
          f"axis={args.axis}, roll={args.roll:g}, hold={hold_note}, "
          f"target_axis={args.target_axis}, "
          f"length={args.length:g}, "
          f"offset=({args.offset_x:g},{args.offset_y:g},{args.offset_z:g}), "
          f"shading={args.shading} -> {args.output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="one-mesh, one-primitive generated GLB")
    parser.add_argument("output", help="output OSB2 item bundle")
    parser.add_argument("--axis", choices=("x", "y", "z"), default="y",
                        help="source model's long axis")
    parser.add_argument("--target-axis", choices=("x", "y", "z"), default="y",
                        help="game-space axis that receives the source long axis")
    parser.add_argument("--roll", type=float, default=0.0,
                        help="degrees to rotate around the item length axis")
    parser.add_argument("--flip", action="store_true", help="reverse the selected long axis")
    parser.add_argument("--length", type=float, default=420.0, help="game-space item length")
    hold_group = parser.add_mutually_exclusive_group()
    hold_group.add_argument("--hold-point", choices=("auto", "base", "center", "tip"),
                            help="grip placed at the item origin (default: auto)")
    hold_group.add_argument("--hold-position", type=float, nargs=3,
                            metavar=("X", "Y", "Z"),
                            help="explicit grip in the source model's coordinates")
    hold_group.add_argument("--pivot", choices=("base", "center", "tip"),
                            help="legacy alias for --hold-point")
    parser.add_argument("--hold-inset", type=float, default=0.06,
                        help="fraction inset from the narrow end for auto grip (default: 0.06)")
    parser.add_argument("--offset-x", type=float, default=0.0,
                        help="game-space X grip offset applied after scaling")
    parser.add_argument("--offset-y", type=float, default=0.0,
                        help="game-space Y grip offset applied after scaling")
    parser.add_argument("--offset-z", type=float, default=0.0,
                        help="game-space Z grip offset applied after scaling")
    parser.add_argument("--max-tris", type=int, default=2000,
                        help="reject denser models instead of silently degrading them")
    parser.add_argument("--shading", choices=("vertex", "textured-lit"), default="vertex",
                        help="vertex colors (OSB2) or cleaned texture + dynamic lighting (OSB4)")
    parser.add_argument("--texture-size", type=int, default=64,
                        help="square RGBA16 atlas size for --shading textured-lit")
    args = parser.parse_args()
    if args.length <= 0 or args.max_tris <= 0 or args.texture_size <= 0:
        parser.error("--length, --max-tris, and --texture-size must be positive")
    if not 0.0 <= args.hold_inset <= 0.25:
        parser.error("--hold-inset must be between 0 and 0.25")
    if args.texture_size > 1024 or args.texture_size % 4:
        parser.error("--texture-size must be a multiple of 4 and no larger than 1024")
    convert(args)


if __name__ == "__main__":
    main()
