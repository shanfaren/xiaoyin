import bpy,sys
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'modeling'
bpy.ops.wm.open_mainfile(filepath=str(OUT/'森林小博士.blend'))
scene=bpy.context.scene;arm=bpy.data.objects['ForestDoctorRig'];camera=scene.camera
scene.cycles.samples=20;camera.data.type='ORTHO';camera.data.ortho_scale=1.4
cases=[('face_closed','Idle',1),('face_open','Speaking',13)]
if '--open-only' in sys.argv:cases=cases[1:]
for name,clip,frame in cases:
    arm.animation_data.action=bpy.data.actions[clip];scene.frame_set(frame)
    camera.location=(0,-6,3.40);camera.rotation_euler=(Vector((0,-.1,3.40))-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(OUT/'preview'/(name+'.png'));bpy.ops.render.render(write_still=True)
