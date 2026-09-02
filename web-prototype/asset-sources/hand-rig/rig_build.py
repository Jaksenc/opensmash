"""Build a proper hand armature inside the Meshy glove GLB.

Joint guesses (Blender world space: X right, Y depth(-Y=front/knuckles), Z up)
are snapped to the local mesh centroid so bones sit centered in each digit,
then overlay renders (front/side) visualize bones for iteration.
Saves hand_rig.blend for the weighting/export step.
"""
import bpy, math, json
from pathlib import Path
from mathutils import Vector

GLB = str(
    Path(__file__).resolve().parents[2]
    / "visual" / "assets" / "hand-cursor-meshy.glb"
)
OUT = "/private/tmp/claude-501/-Users-joey-Claude-Code-smash-weights/f08c86ec-b792-43d7-81d5-37ec45a424ce/scratchpad"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
mesh_obj = next(o for o in bpy.data.objects if o.type == 'MESH')
mesh_obj.name = "hand"
# apply transforms so mesh data is in world space
bpy.context.view_layer.objects.active = mesh_obj
mesh_obj.select_set(True)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

verts = [mesh_obj.matrix_world @ v.co for v in mesh_obj.data.vertices]

def snap(p, radius=0.09, lock_z=False):
    """Snap point to centroid of nearby vertices (digit centering)."""
    p = Vector(p)
    for _ in range(3):
        near = [v for v in verts if (v - p).length < radius]
        if len(near) < 8:
            radius *= 1.4
            continue
        c = sum(near, Vector()) / len(near)
        if lock_z:
            c.z = p.z
        p = p.lerp(c, 0.7)
    return p

# name: chain of joints (head..tail sequence). Depth (Y) mostly auto-snapped.
# -Y = knuckle side (front toward viewer in our web cam), +Y = palm side.
CHAINS = {
    'index':  [(0.17, 0.05, 0.27), (0.24, 0.0, 0.55), (0.28, 0.0, 0.72), (0.31, 0.0, 0.90)],
    'thumb':  [(-0.05, -0.1, 0.05), (-0.12, -0.1, 0.35), (-0.16, -0.1, 0.55), (-0.19, -0.1, 0.71)],
    'middle': [(0.48, 0.0, 0.33), (0.56, -0.18, 0.20), (0.50, 0.05, 0.06)],
    'ring':   [(0.55, 0.0, 0.17), (0.62, -0.18, 0.04), (0.55, 0.05, -0.07)],
    'pinky':  [(0.56, 0.0, 0.01), (0.61, -0.18, -0.11), (0.55, 0.05, -0.21)],
}
PALM = [(-0.20, 0.0, -0.45), (0.12, 0.0, 0.10)]   # wrist -> palm center
ROOT = [(-0.30, 0.0, -0.60), (-0.20, 0.0, -0.45)]  # cuff -> wrist

snapped = {}
for name, chain in CHAINS.items():
    snapped[name] = [snap(p) for p in chain]
snapped['palm'] = [Vector(PALM[0]), Vector(PALM[1])]
snapped['root'] = [Vector(ROOT[0]), Vector(ROOT[1])]
print("SNAPPED:", json.dumps({k: [[round(c, 3) for c in v] for v in ch] for k, ch in snapped.items()}))

# ── armature ───────────────────────────────────────────────────────────────
arm_data = bpy.data.armatures.new("HandRig")
arm = bpy.data.objects.new("HandRig", arm_data)
bpy.context.scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')

def add_bone(name, head, tail, parent=None):
    b = arm_data.edit_bones.new(name)
    b.head, b.tail = head, tail
    if parent:
        b.parent = arm_data.edit_bones[parent]
        b.use_connect = (b.head - b.parent.tail).length < 1e-4
    return b

add_bone('root', snapped['root'][0], snapped['root'][1])
add_bone('palm', snapped['palm'][0], snapped['palm'][1], 'root')
for name, ch in snapped.items():
    if name in ('palm', 'root'):
        continue
    for i in range(len(ch) - 1):
        add_bone(f"{name}_{i+1:02d}", ch[i], ch[i+1],
                 'palm' if i == 0 else f"{name}_{i:02d}")
bpy.ops.object.mode_set(mode='OBJECT')

# ── overlay renders ────────────────────────────────────────────────────────
# bone proxies: red emission cylinders (armatures don't render)
proxy_mat = bpy.data.materials.new("proxy")
proxy_mat.use_nodes = True
bsdf = proxy_mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Emission Color"].default_value = (1, 0.1, 0.1, 1)
bsdf.inputs["Emission Strength"].default_value = 5

mesh_mat = bpy.data.materials.new("semi")
mesh_mat.use_nodes = True
mb = mesh_mat.node_tree.nodes["Principled BSDF"]
mb.inputs["Alpha"].default_value = 0.5
mesh_mat.blend_method = 'BLEND'
mesh_obj.data.materials.clear()
mesh_obj.data.materials.append(mesh_mat)

proxies = []
for name, ch in snapped.items():
    for i in range(len(ch) - 1):
        h, t = ch[i], ch[i+1]
        mid = (h + t) / 2
        d = t - h
        cyl = bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=d.length, location=mid)
        ob = bpy.context.active_object
        ob.rotation_mode = 'QUATERNION'
        ob.rotation_quaternion = d.to_track_quat('Z', 'Y')
        ob.data.materials.append(proxy_mat)
        proxies.append(ob)
        sph = bpy.ops.mesh.primitive_uv_sphere_add(radius=0.03, location=h)
        ob2 = bpy.context.active_object
        ob2.data.materials.append(proxy_mat)
        proxies.append(ob2)

scene = bpy.context.scene
scene.render.resolution_x = 800
scene.render.resolution_y = 800
scene.render.film_transparent = True
light_data = bpy.data.lights.new("sun", type='SUN')
light = bpy.data.objects.new("sun", light_data)
scene.collection.objects.link(light)
light.rotation_euler = (math.radians(45), 0, math.radians(30))

cam_data = bpy.data.cameras.new("cam")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = 2.1
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
for vname, loc, rot in [
    ('front', Vector((0, -5, 0)), (math.radians(90), 0, 0)),
    ('side', Vector((5, 0, 0)), (math.radians(90), 0, math.radians(90))),
]:
    cam.location = loc
    cam.rotation_euler = rot
    scene.render.filepath = f"{OUT}/rig_{vname}.png"
    bpy.ops.render.render(write_still=True)

for ob in proxies:
    bpy.data.objects.remove(ob)
mesh_obj.data.materials.clear()

bpy.ops.wm.save_as_mainfile(filepath=f"{OUT}/hand_rig.blend")
print("SAVED hand_rig.blend")
