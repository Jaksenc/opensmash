"""Normalize bone rolls, auto-weight (bone heat), test-pose render, export GLB."""
import bpy, math
from pathlib import Path
from mathutils import Vector

OUT = "/private/tmp/claude-501/-Users-joey-Claude-Code-smash-weights/f08c86ec-b792-43d7-81d5-37ec45a424ce/scratchpad"
DEST = str(
    Path(__file__).resolve().parents[2]
    / "visual" / "assets" / "hand-rigged.glb"
)

bpy.ops.wm.open_mainfile(filepath=f"{OUT}/hand_rig.blend")
mesh_obj = bpy.data.objects['hand']
arm = bpy.data.objects['HandRig']

# ── consistent rolls: local Z toward -Y (knuckle side) for every bone ──────
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
for eb in arm.data.edit_bones:
    eb.align_roll(Vector((0, -1, 0)))
bpy.ops.object.mode_set(mode='OBJECT')

# ── scripted distance weights (bone heat fails on this mesh) ───────────────
# weld duplicates first so weights are consistent across seams
bpy.ops.object.select_all(action='DESELECT')
mesh_obj.select_set(True)
bpy.context.view_layer.objects.active = mesh_obj
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.remove_doubles(threshold=1e-4)
bpy.ops.object.mode_set(mode='OBJECT')

def seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
    return (p - (a + ab * t)).length

bones_ws = []   # (name, head, tail) in world space
for bone in arm.data.bones:
    bones_ws.append((bone.name,
                     arm.matrix_world @ bone.head_local,
                     arm.matrix_world @ bone.tail_local))

groups = {name: mesh_obj.vertex_groups.new(name=name) for name, _, _ in bones_ws}
mw = mesh_obj.matrix_world
for v in mesh_obj.data.vertices:
    p = mw @ v.co
    ds = [(name, seg_dist(p, h, t)) for name, h, t in bones_ws]
    ds.sort(key=lambda x: x[1])
    top = ds[:4]
    ws = [(name, (d + 0.05) ** -3) for name, d in top]
    total = sum(w for _, w in ws)
    for name, w in ws:
        if w / total > 0.02:
            groups[name].add([v.index], w / total, 'REPLACE')

# smooth the weight transitions
bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
bpy.ops.object.vertex_group_smooth(group_select_mode='ALL', factor=0.5, repeat=4)
bpy.ops.object.mode_set(mode='OBJECT')

mod = mesh_obj.modifiers.new('Armature', 'ARMATURE')
mod.object = arm
mesh_obj.parent = arm
print("WEIGHTED (scripted), verts:", len(mesh_obj.data.vertices))

# ── test pose: curl all fingers (fist) and render front ────────────────────
scene = bpy.context.scene
scene.render.resolution_x = 800
scene.render.resolution_y = 800
scene.render.film_transparent = True
light_data = bpy.data.lights.new("sun2", type='SUN')
light = bpy.data.objects.new("sun2", light_data)
scene.collection.objects.link(light)
light.rotation_euler = (math.radians(60), 0, math.radians(20))
cam_data = bpy.data.cameras.new("cam2")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = 2.3
cam = bpy.data.objects.new("cam2", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
cam.location = Vector((0, -5, 0))
cam.rotation_euler = (math.radians(90), 0, 0)

bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='POSE')

def set_curl(prefix, per_joint):
    for i, ang in enumerate(per_joint, start=1):
        pb = arm.pose.bones.get(f"{prefix}_{i:02d}")
        if pb:
            pb.rotation_mode = 'XYZ'
            pb.rotation_euler = (math.radians(ang), 0, 0)

# rest render first
scene.render.filepath = f"{OUT}/posed_rest.png"
bpy.ops.render.render(write_still=True)

# curl index + thumb toward a fist; slight extra curl on already-curled digits
set_curl('index', [45, 55, 45])
set_curl('thumb', [30, 35, 30])
set_curl('middle', [25, 30])
set_curl('ring', [25, 30])
set_curl('pinky', [25, 30])
scene.render.filepath = f"{OUT}/posed_fist.png"
bpy.ops.render.render(write_still=True)

# open-hand test: extend the curled digits backwards
set_curl('index', [0, 0, 0])
set_curl('thumb', [0, 0, 0])
set_curl('middle', [-40, -50])
set_curl('ring', [-40, -50])
set_curl('pinky', [-40, -50])
scene.render.filepath = f"{OUT}/posed_open.png"
bpy.ops.render.render(write_still=True)

# reset pose for export
for pb in arm.pose.bones:
    pb.rotation_euler = (0, 0, 0)
bpy.ops.object.mode_set(mode='OBJECT')

# light smoothing to match our soft style
mod = mesh_obj.modifiers.new("smooth", 'SMOOTH')
mod.factor = 0.5
mod.iterations = 2
bpy.context.view_layer.objects.active = mesh_obj
bpy.ops.object.modifier_apply(modifier="smooth")

bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=DEST, export_format='GLB',
                          export_animations=False, export_skins=True,
                          export_yup=True)
print("EXPORTED", DEST)
