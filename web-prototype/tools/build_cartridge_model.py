"""Build the original, unbranded retro cartridge used by the site.

Run with Blender so the generated GLB stays reproducible:

    blender --background --python tools/build_cartridge_model.py
"""

from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "web-prototype" / "visual" / "assets" / "n64-cartridge-original.glb"


def material(name, color, roughness=0.78, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    return mat


def bevelled_box(name, location, dimensions, mat, bevel=0.04):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        modifier = obj.modifiers.new("Soft molded edges", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
        modifier.limit_method = "ANGLE"
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    return obj


def cartridge_shell(mat):
    # Front silhouette in X/Z, extruded along Y. The stepped shoulders evoke
    # a 1990s console cartridge without reproducing the unavailable reference.
    outline = [
        (-1.50, -1.05), (1.50, -1.05), (1.50, 0.47),
        (1.38, 0.70), (1.15, 0.88), (0.92, 1.08),
        (-0.92, 1.08), (-1.15, 0.88), (-1.38, 0.70), (-1.50, 0.47),
    ]
    depth = 0.54
    vertices = [(x, -depth / 2, z) for x, z in outline]
    vertices += [(x, depth / 2, z) for x, z in outline]
    count = len(outline)
    faces = [tuple(reversed(range(count))), tuple(range(count, count * 2))]
    faces += [
        (i, (i + 1) % count, (i + 1) % count + count, i + count)
        for i in range(count)
    ]
    mesh = bpy.data.meshes.new("Cartridge shell mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Cartridge shell", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    bevel = obj.modifiers.new("Rounded shell edges", "BEVEL")
    bevel.width = 0.085
    bevel.segments = 3
    bevel.limit_method = "ANGLE"
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    obj.select_set(False)
    return obj


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    shell_mat = material("Warm charcoal plastic", (0.20, 0.19, 0.22), 0.92)
    inset_mat = material("Deep label inset", (0.055, 0.045, 0.055), 0.88)
    label_mat = material("OpenSmash label", (0.62, 0.075, 0.035), 0.73)
    gold_mat = material("Amber label bar", (0.96, 0.48, 0.055), 0.64)
    cream_mat = material("Cream label bar", (0.94, 0.82, 0.58), 0.76)
    connector_mat = material("Connector shadow", (0.035, 0.03, 0.035), 0.9)
    contact_mat = material("Connector contacts", (0.52, 0.31, 0.10), 0.58, 0.25)

    cartridge_shell(shell_mat)

    # Front label stack. Blender's -Y face exports toward the Three.js camera.
    bevelled_box("Label recess", (0, -0.303, 0.12), (2.30, 0.075, 1.12), inset_mat, 0.075)
    bevelled_box("Label face", (0, -0.349, 0.13), (2.08, 0.035, 0.91), label_mat, 0.055)
    bevelled_box("Amber stripe", (0, -0.374, 0.32), (1.82, 0.018, 0.12), gold_mat, 0.025)
    bevelled_box("Cream stripe", (0, -0.376, 0.08), (1.52, 0.018, 0.09), cream_mat, 0.02)
    bevelled_box("Dark title block", (0, -0.378, -0.18), (1.18, 0.018, 0.22), inset_mat, 0.035)

    # Molded side ribs and the lower connector details sell the silhouette
    # after it passes through the site's deliberately tiny render target.
    for x in (-1.28, 1.28):
        bevelled_box("Molded side rail", (x, -0.322, -0.20), (0.12, 0.075, 1.28), shell_mat, 0.035)
    bevelled_box("Connector recess", (0, -0.315, -0.90), (1.62, 0.10, 0.25), connector_mat, 0.035)
    for x in (-0.58, -0.29, 0, 0.29, 0.58):
        bevelled_box("Contact", (x, -0.377, -0.91), (0.12, 0.025, 0.16), contact_mat, 0.015)

    # Two shallow fastener impressions.
    for x in (-1.05, 1.05):
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.065, depth=0.025,
                                           location=(x, -0.367, -0.72),
                                           rotation=(1.57079632679, 0, 0))
        screw = bpy.context.object
        screw.name = "Fastener impression"
        screw.data.materials.append(connector_mat)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.shade_smooth_by_angle()
    bpy.ops.export_scene.gltf(
        filepath=str(OUTPUT),
        export_format="GLB",
        export_apply=True,
        export_materials="EXPORT",
        export_yup=True,
    )
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    build()
