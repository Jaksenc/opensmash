"""Render four clay previews of a GLB for geometry QA.

Usage:
    blender --background --python tools/render_glb_preview.py -- model.glb output-dir [textured]
"""

import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


def mesh_bounds(objects):
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    low = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return low, high


def look_at(camera, target):
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    source = Path(args[0]).expanduser().resolve()
    output = Path(args[1]).expanduser().resolve()
    use_textures = len(args) > 2 and args[2] == "textured"
    output.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    low, high = mesh_bounds(meshes)
    center = (low + high) * 0.5
    size = high - low
    for obj in bpy.context.scene.objects:
        if obj.parent is None and obj.type != "CAMERA":
            obj.location -= center

    if not use_textures:
        clay = bpy.data.materials.new("Clay")
        clay.diffuse_color = (0.18, 0.21, 0.24, 1)
        clay.use_nodes = True
        shader = clay.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = (0.18, 0.21, 0.24, 1)
        shader.inputs["Roughness"].default_value = 0.86
        for obj in meshes:
            obj.data.materials.clear()
            obj.data.materials.append(clay)

    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.lens = 55
    bpy.context.scene.camera = camera

    bpy.ops.object.light_add(type="AREA")
    key = bpy.context.object
    key.data.energy = 80
    key.data.shape = "DISK"
    key.data.size = max(size) * 2.5

    bpy.ops.object.light_add(type="AREA", location=(-2, 1, 2))
    fill = bpy.context.object
    fill.data.energy = 40
    fill.data.size = max(size) * 2

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 640
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new("Preview world")
    scene.world.color = (0.055, 0.055, 0.065)
    scene.view_settings.look = "AgX - Medium High Contrast"

    radius = max(size) * 0.55
    distance = radius / math.tan(camera.data.angle / 2) * 1.45
    views = {
        "pos_x": Vector((distance, 0, distance * 0.08)),
        "neg_x": Vector((-distance, 0, distance * 0.08)),
        "pos_y": Vector((0, distance, distance * 0.08)),
        "neg_y": Vector((0, -distance, distance * 0.08)),
        "top": Vector((0, 0, distance)),
        "three_quarter": Vector((distance * 0.75, -distance * 0.75, distance * 0.28)),
    }
    for name, location in views.items():
        camera.location = location
        look_at(camera, Vector((0, 0, 0)))
        key.location = camera.location * 0.7 + Vector((-radius * 0.4, 0, radius * 0.8))
        look_at(key, Vector((0, 0, 0)))
        scene.render.filepath = str(output / f"{name}.png")
        bpy.ops.render.render(write_still=True)

    for obj in meshes:
        obj.data.calc_loop_triangles()
    edge_counts = {"boundary": 0, "non_manifold": 0, "wire": 0}
    for obj in meshes:
        mesh = bmesh.new()
        mesh.from_mesh(obj.data)
        bmesh.ops.remove_doubles(mesh, verts=list(mesh.verts), dist=1e-6)
        edge_counts["boundary"] += sum(edge.is_boundary for edge in mesh.edges)
        edge_counts["non_manifold"] += sum(not edge.is_manifold for edge in mesh.edges)
        edge_counts["wire"] += sum(edge.is_wire for edge in mesh.edges)
        mesh.free()
    print(f"bounds={tuple(round(v, 4) for v in size)}")
    print(f"meshes={len(meshes)}")
    print(f"vertices={sum(len(obj.data.vertices) for obj in meshes)}")
    print(f"triangles={sum(len(obj.data.loop_triangles) for obj in meshes)}")
    print(f"materials={sum(len(obj.data.materials) for obj in meshes)}")
    print(f"boundary_edges={edge_counts['boundary']}")
    print(f"non_manifold_edges={edge_counts['non_manifold']}")
    print(f"wire_edges={edge_counts['wire']}")
    print(f"renders={output}")


if __name__ == "__main__":
    main()
