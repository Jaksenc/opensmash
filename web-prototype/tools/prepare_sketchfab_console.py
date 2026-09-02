"""Normalize the recovered Sketchfab N64 for the fitted console pipeline.

The recovered file uses X for width and -Y for its front.  The site pipeline
expects +X front, Y width, and Z up.  This script rotates and uniformly scales
the model, recenters it, and reduces embedded maps to a web-friendly maximum
edge while retaining the recovered GLB unchanged as the archival source.

Run with Blender:

    blender --background --python tools/prepare_sketchfab_console.py
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "asset-sources" / "n64-console-sketchfab-recovered.glb"
OUTPUT = ROOT / "asset-sources" / "generated" / "hybrid-four-port-console.glb"
TARGET_WIDTH = 0.998
MAX_TEXTURE_EDGE = 1024
PLASTIC_ROUGHNESS = 0.52
SOURCE_URL = (
    "https://sketchfab.com/3d-models/"
    "nintendo-64-f2c33b268270498fbdb48dcc4752f13b"
)


def bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        for corner in obj.bound_box
    ]
    low = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return low, high


def main() -> None:
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Recovered Sketchfab source is missing: {SOURCE}")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(SOURCE))
    roots = [obj for obj in bpy.context.scene.objects if obj.parent is None]
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"No meshes found in {SOURCE}")

    # +90 degrees maps source -Y front to pipeline +X front and source X
    # width to pipeline Y width.
    rotation = Matrix.Rotation(math.pi * 0.5, 4, "Z")
    for root in roots:
        root.matrix_world = rotation @ root.matrix_world
    bpy.context.view_layer.update()

    low, high = bounds(meshes)
    scale = TARGET_WIDTH / (high.y - low.y)
    uniform_scale = Matrix.Scale(scale, 4)
    for root in roots:
        root.matrix_world = uniform_scale @ root.matrix_world
    bpy.context.view_layer.update()

    low, high = bounds(meshes)
    center = (low + high) * 0.5
    translation = Matrix.Translation(-center)
    for root in roots:
        root.matrix_world = translation @ root.matrix_world
        root["source_url"] = SOURCE_URL
        root["source_author"] = "NeoZeroo"
        root["source_model_uid"] = "f2c33b268270498fbdb48dcc4752f13b"
    bpy.context.view_layer.update()

    for image in bpy.data.images:
        width, height = image.size
        if max(width, height) <= MAX_TEXTURE_EDGE:
            continue
        ratio = MAX_TEXTURE_EDGE / max(width, height)
        image.scale(max(1, round(width * ratio)), max(1, round(height * ratio)))

    # The viewer used a separate glossiness map that glTF cannot bind directly
    # without repacking it into an ORM texture.  Retain the recovered color,
    # normal, and AO maps, and use a stable molded-plastic roughness instead of
    # the mirror-like zero fallback from the recovery converter.
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        shader = mat.node_tree.nodes.get("Principled BSDF")
        if shader is None:
            continue
        shader.inputs["Metallic"].default_value = 0.0
        shader.inputs["Roughness"].default_value = PLASTIC_ROUGHNESS

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_name(f".{OUTPUT.name}.tmp.glb")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=str(temporary),
        export_format="GLB",
        export_apply=True,
        export_materials="EXPORT",
        export_extras=True,
        export_yup=True,
    )
    os.replace(temporary, OUTPUT)

    low, high = bounds(meshes)
    size = high - low
    print(
        f"Wrote {OUTPUT}; size=({size.x:.6f}, {size.y:.6f}, {size.z:.6f}); "
        f"meshes={len(meshes)}; triangles="
        f"{sum(len(obj.data.polygons) for obj in meshes)}"
    )


if __name__ == "__main__":
    main()
