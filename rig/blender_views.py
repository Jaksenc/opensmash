"""Render calibrated ortho views of the GLB for joint placement."""
import bpy, math, sys
from pathlib import Path

GLB = str(Path(__file__).resolve().parents[1] / "website" / "assets" / "hand-cursor-meshy.glb")
OUT = "/private/tmp/claude-501/-Users-joey-Claude-Code-smash-weights/f08c86ec-b792-43d7-81d5-37ec45a424ce/scratchpad"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

mesh_obj = next(o for o in bpy.data.objects if o.type == 'MESH')
# world-space bbox
from mathutils import Vector
coords = [mesh_obj.matrix_world @ Vector(c) for c in mesh_obj.bound_box]
mn = Vector((min(c.x for c in coords), min(c.y for c in coords), min(c.z for c in coords)))
mx = Vector((max(c.x for c in coords), max(c.y for c in coords), max(c.z for c in coords)))
ctr = (mn + mx) / 2
print("BBOX min", tuple(round(v, 3) for v in mn), "max", tuple(round(v, 3) for v in mx))

scene = bpy.context.scene
scene.render.resolution_x = 800
scene.render.resolution_y = 800
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'

# simple lighting
light_data = bpy.data.lights.new("sun", type='SUN')
light = bpy.data.objects.new("sun", light_data)
scene.collection.objects.link(light)
light.rotation_euler = (math.radians(45), 0, math.radians(30))

span = max(mx.x - mn.x, mx.y - mn.y, mx.z - mn.z) * 1.1
print("ORTHO_SCALE", round(span, 4), "CENTER", tuple(round(v, 4) for v in ctr))

cam_data = bpy.data.cameras.new("cam")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = span
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

views = {
    # name: (location offset, rotation euler)
    'front': (Vector((0, -5, 0)), (math.radians(90), 0, 0)),          # looking +Y
    'side':  (Vector((5, 0, 0)),  (math.radians(90), 0, math.radians(90))),  # looking -X
    'top':   (Vector((0, 0, 5)),  (0, 0, 0)),                          # looking -Z
}
for name, (off, rot) in views.items():
    cam.location = ctr + off
    cam.rotation_euler = rot
    scene.render.filepath = f"{OUT}/glb_{name}.png"
    bpy.ops.render.render(write_still=True)
    print("rendered", name)
