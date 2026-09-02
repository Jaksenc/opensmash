#!/usr/bin/env python3
"""Build an exact, beveled 3D logo sign from a transparent PNG.

The normal Python stage reads the alpha channel and reduces its outer silhouette
to a clean polygon.  It then launches Blender to extrude that silhouette, map
the source image pixel-for-pixel to the front, and export both GLB and BLEND.

Usage:
    python3 tools/build_logo_glb.py \
        --input logo.png \
        --output logo.glb \
        --blend logo.blend
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path


def point_line_distance(point, start, end):
    px, py = point
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    if dx == 0 and dy == 0:
        return math.hypot(px - sx, py - sy)
    return abs(dy * px - dx * py + ex * sy - ey * sx) / math.hypot(dx, dy)


def simplify(points, epsilon):
    """Ramer-Douglas-Peucker simplification for an open profile."""
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    farthest_index = 0
    farthest_distance = 0.0
    for index, point in enumerate(points[1:-1], start=1):
        distance = point_line_distance(point, start, end)
        if distance > farthest_distance:
            farthest_index = index
            farthest_distance = distance
    if farthest_distance <= epsilon:
        return [start, end]
    left = simplify(points[: farthest_index + 1], epsilon)
    right = simplify(points[farthest_index:], epsilon)
    return left[:-1] + right


def median_smooth(values, radius=3):
    result = []
    for index in range(len(values)):
        window = values[max(0, index - radius) : index + radius + 1]
        result.append(sorted(window)[len(window) // 2])
    return result


def extract_silhouette(image_path: Path, threshold: int, epsilon: float):
    from PIL import Image

    image = Image.open(image_path).convert("RGBA")
    width, height = image.size
    alpha = image.getchannel("A")
    pixels = alpha.load()

    columns = []
    for x in range(width):
        ys = [y for y in range(height) if pixels[x, y] >= threshold]
        if ys:
            columns.append((x, min(ys), max(ys)))
    if not columns:
        raise SystemExit("The input image contains no opaque pixels")

    # Ignore isolated one-pixel antialias fragments at either horizontal edge.
    runs = []
    current = [columns[0]]
    for item in columns[1:]:
        if item[0] == current[-1][0] + 1:
            current.append(item)
        else:
            runs.append(current)
            current = [item]
    runs.append(current)
    columns = max(runs, key=len)

    xs = [item[0] for item in columns]
    tops = median_smooth([item[1] for item in columns])
    bottoms = median_smooth([item[2] for item in columns])
    top_profile = simplify(list(zip(xs, tops)), epsilon)
    bottom_profile = simplify(list(zip(xs, bottoms)), epsilon)

    # Image Y points down. Reversing the top/bottom order produces a CCW
    # polygon after conversion into Blender's Y-up object plane.
    polygon = list(reversed(top_profile)) + bottom_profile
    return {
        "width": width,
        "height": height,
        "polygon": polygon,
    }


def build_in_blender(args):
    import bpy

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    blend_path = Path(args.blend).resolve() if args.blend else None
    data = json.loads(Path(args.contour).read_text())
    image_width = data["width"]
    image_height = data["height"]
    scale = args.width / image_width
    depth = args.depth

    polygon = []
    uvs_2d = []
    for pixel_x, pixel_y in data["polygon"]:
        x = (pixel_x - image_width * 0.5) * scale
        y = (image_height * 0.5 - pixel_y) * scale
        polygon.append((x, y))
        uvs_2d.append((pixel_x / image_width, 1.0 - pixel_y / image_height))

    count = len(polygon)
    vertices = [(x, y, depth * 0.5) for x, y in polygon]
    vertices += [(x, y, -depth * 0.5) for x, y in polygon]
    vertex_uvs = uvs_2d + uvs_2d

    front = tuple(range(count))
    back = tuple(reversed(range(count, count * 2)))
    faces = [front, back]
    for index in range(count):
        following = (index + 1) % count
        faces.append((index + count, following + count, following, index))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    mesh = bpy.data.meshes.new("Super Weights Bros Logo Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    logo = bpy.data.objects.new("Super Weights Bros Logo", mesh)
    bpy.context.collection.objects.link(logo)

    uv_layer = mesh.uv_layers.new(name="Logo UV")
    for polygon_face in mesh.polygons:
        for loop_index in polygon_face.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            uv_layer.data[loop_index].uv = vertex_uvs[vertex_index]

    artwork = bpy.data.materials.new("Original Logo Artwork")
    artwork.use_nodes = True
    artwork.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    try:
        artwork.surface_render_method = "DITHERED"
    except AttributeError:
        pass
    nodes = artwork.node_tree.nodes
    links = artwork.node_tree.links
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(str(input_path), check_existing=False)
    texture.image.pack()
    texture.interpolation = "Linear"
    links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    links.new(texture.outputs["Alpha"], shader.inputs["Alpha"])
    if "Emission Color" in shader.inputs:
        links.new(texture.outputs["Color"], shader.inputs["Emission Color"])
        shader.inputs["Emission Strength"].default_value = 0.45
    shader.inputs["Roughness"].default_value = 0.42
    shader.inputs["Metallic"].default_value = 0.03
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])

    side = bpy.data.materials.new("Black Beveled Sides")
    side.use_nodes = True
    side_shader = side.node_tree.nodes.get("Principled BSDF")
    side_shader.inputs["Base Color"].default_value = (0.003, 0.003, 0.004, 1.0)
    side_shader.inputs["Roughness"].default_value = 0.36
    side_shader.inputs["Metallic"].default_value = 0.12

    mesh.materials.append(artwork)
    mesh.materials.append(side)
    mesh.polygons[0].material_index = 0
    for polygon_face in mesh.polygons[1:]:
        polygon_face.material_index = 1

    bpy.context.view_layer.objects.active = logo
    logo.select_set(True)
    bevel = logo.modifiers.new("Small rounded edge", "BEVEL")
    bevel.width = args.bevel
    bevel.segments = 3
    bevel.limit_method = "ANGLE"
    bevel.angle_limit = math.radians(20)
    bevel.material = 1
    try:
        bevel.harden_normals = True
    except AttributeError:
        pass
    bpy.ops.object.modifier_apply(modifier=bevel.name)

    # A stable object transform makes the GLB convenient in Blender, Three.js,
    # and game engines. The artwork faces +Z before glTF's Y-up conversion.
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(output_path),
        export_format="GLB",
        export_materials="EXPORT",
        export_texcoords=True,
        export_normals=True,
        export_apply=True,
        export_yup=True,
    )

    if blend_path:
        blend_path.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    triangles = sum(len(face.vertices) - 2 for face in logo.data.polygons)
    print(
        json.dumps(
            {
                "output": str(output_path),
                "blend": str(blend_path) if blend_path else None,
                "vertices": len(logo.data.vertices),
                "triangles": triangles,
                "silhouette_points": count,
            }
        )
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--blend")
    parser.add_argument("--width", type=float, default=10.0)
    parser.add_argument("--depth", type=float, default=0.26)
    parser.add_argument("--bevel", type=float, default=0.035)
    parser.add_argument("--threshold", type=int, default=48)
    parser.add_argument("--simplify", type=float, default=2.0)
    parser.add_argument("--contour")
    parser.add_argument("--blender-stage", action="store_true")
    return parser.parse_args(argv)


def main():
    raw_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else None
    args = parse_args(raw_args)
    if args.blender_stage:
        build_in_blender(args)
        return

    source = Path(args.input).expanduser().resolve()
    destination = Path(args.output).expanduser().resolve()
    blend = Path(args.blend).expanduser().resolve() if args.blend else None
    silhouette = extract_silhouette(source, args.threshold, args.simplify)
    with tempfile.TemporaryDirectory(prefix="logo-glb-") as directory:
        contour_path = Path(directory) / "contour.json"
        contour_path.write_text(json.dumps(silhouette))
        command = [
            "blender",
            "--background",
            "--python",
            str(Path(__file__).resolve()),
            "--",
            "--blender-stage",
            "--input",
            str(source),
            "--output",
            str(destination),
            "--contour",
            str(contour_path),
            "--width",
            str(args.width),
            "--depth",
            str(args.depth),
            "--bevel",
            str(args.bevel),
        ]
        if blend:
            command.extend(("--blend", str(blend)))
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
