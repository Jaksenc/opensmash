"""Add FUN light pipes and a cartridge snap anchor to the Tripo console.

Run with Blender:

    blender --background --python tools/build_console_cartridge_system.py

The source GLBs are left untouched. The generated console preserves the Tripo
shell, ports, switches, and authored cartridge slot. Only the small front
indicator is covered by three light-pipe letters, and a named snap anchor is
added for the Three.js interaction.
"""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
CARTRIDGE_SOURCE = ROOT / "website" / "assets" / "n64-cartridge-tripo.glb"
CONSOLE_SOURCE = ROOT / "website" / "assets" / "generated" / "hybrid-four-port-console.glb"
CONSOLE_OUTPUT = ROOT / "website" / "assets" / "hybrid-four-port-console-fitted.glb"

CARTRIDGE_FIT_SCALE = 0.44
SLOT_CLEARANCE = 0.012
SLOT_CENTER_X = -0.15
SLOT_TOP_Z = 0.137
SLOT_INSERT_DEPTH = 0.055


def material(name: str, color: tuple[float, float, float], roughness: float = 0.82):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    return mat


def bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    low = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return low, high


def bevelled_box(
    name: str,
    location: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    mat: bpy.types.Material,
    *,
    bevel: float = 0.0012,
    rotation_x: float = 0.0,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=(rotation_x, 0, 0))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        modifier = obj.modifiers.new("Molded edge", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
        modifier.limit_method = "ANGLE"
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    return obj


def join_parts(name: str, parts: list[bpy.types.Object]) -> bpy.types.Object:
    bpy.ops.object.select_all(action="DESELECT")
    for part in parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    parts[0].name = name
    return parts[0]


def measure_cartridge() -> Vector:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(CARTRIDGE_SOURCE))
    source_meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    low, high = bounds(source_meshes)
    return high - low


def add_fun_indicator(front_x: float) -> None:
    """Cover only the source indicator and add three tiny light pipes."""

    cover_mat = material("Original indicator cover", (0.038, 0.042, 0.050), 0.82)
    letter_mat = material("FUN dark light pipe", (0.055, 0.062, 0.075), 0.6)
    indicator_z = 0.058
    cover_depth = 0.004
    cover_x = front_x + cover_depth * 0.45
    bevelled_box(
        "OriginalIndicatorCover",
        (cover_x, 0, indicator_z),
        (cover_depth, 0.068, 0.024),
        cover_mat,
        bevel=0.003,
    )

    # +X is the front of this asset. Y runs left/right across the face and Z
    # is vertical. These retain the existing FUN mesh names used by Three.js.
    face_x = cover_x + cover_depth * 0.75
    letter_z = indicator_z
    letter_height = 0.019
    letter_width = 0.012
    stroke = 0.003
    depth = 0.004
    centers = {"F": -0.0165, "U": 0.0, "N": 0.0165}
    side_offset = (letter_width - stroke) * 0.5

    f_y = centers["F"]
    f_parts = [
        bevelled_box("F stem", (face_x, f_y + side_offset, letter_z),
                     (depth, stroke, letter_height), letter_mat),
        bevelled_box("F top", (face_x, f_y, letter_z + letter_height * 0.42),
                     (depth, letter_width, stroke), letter_mat),
        bevelled_box("F middle", (face_x, f_y + stroke * 0.12, letter_z + 0.002),
                     (depth, letter_width * 0.76, stroke), letter_mat),
    ]
    join_parts("FUN_F", f_parts)

    u_y = centers["U"]
    u_parts = [
        bevelled_box("U left", (face_x, u_y + side_offset, letter_z + 0.002),
                     (depth, stroke, letter_height - stroke), letter_mat),
        bevelled_box("U right", (face_x, u_y - side_offset, letter_z + 0.002),
                     (depth, stroke, letter_height - stroke), letter_mat),
        bevelled_box("U base", (face_x, u_y, letter_z - letter_height * 0.42),
                     (depth, letter_width, stroke), letter_mat),
    ]
    join_parts("FUN_U", u_parts)

    n_y = centers["N"]
    diagonal_dy = letter_width - stroke
    diagonal_dz = letter_height - stroke
    diagonal_length = math.hypot(diagonal_dy, diagonal_dz)
    n_parts = [
        bevelled_box("N left", (face_x, n_y + side_offset, letter_z),
                     (depth, stroke, letter_height), letter_mat),
        bevelled_box("N right", (face_x, n_y - side_offset, letter_z),
                     (depth, stroke, letter_height), letter_mat),
        bevelled_box("N diagonal", (face_x, n_y, letter_z),
                     (depth, stroke, diagonal_length), letter_mat,
                     rotation_x=math.atan2(diagonal_dy, diagonal_dz)),
    ]
    join_parts("FUN_N", n_parts)


def build_fitted_console(cartridge_size: Vector) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(CONSOLE_SOURCE))
    source_meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    _, console_high = bounds(source_meshes)
    aperture_x = cartridge_size.x * CARTRIDGE_FIT_SCALE + SLOT_CLEARANCE
    aperture_y = cartridge_size.y * CARTRIDGE_FIT_SCALE + SLOT_CLEARANCE
    add_fun_indicator(console_high.x)

    cartridge_center_z = (
        SLOT_TOP_Z - SLOT_INSERT_DEPTH - cartridge_size.z * CARTRIDGE_FIT_SCALE * -0.5
    )
    anchor = bpy.data.objects.new("CartridgeSnapAnchor", None)
    anchor.empty_display_type = "PLAIN_AXES"
    anchor.location = (SLOT_CENTER_X, 0, cartridge_center_z)
    anchor["cartridge_fit_scale"] = CARTRIDGE_FIT_SCALE
    anchor["slot_clearance"] = SLOT_CLEARANCE
    anchor["slot_aperture_x"] = aperture_x
    anchor["slot_aperture_y"] = aperture_y
    bpy.context.collection.objects.link(anchor)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=str(CONSOLE_OUTPUT),
        export_format="GLB",
        export_apply=True,
        export_materials="EXPORT",
        export_extras=True,
        export_yup=True,
    )
    print(
        f"Wrote {CONSOLE_OUTPUT}; aperture=({aperture_x:.6f}, {aperture_y:.6f}); "
        f"cartridge scale={CARTRIDGE_FIT_SCALE:.3f}"
    )


if __name__ == "__main__":
    build_fitted_console(measure_cartridge())
