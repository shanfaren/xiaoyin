import bpy,sys
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from character_animation import author_actions
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'modeling'
bpy.ops.wm.open_mainfile(filepath=str(OUT/'森林小博士.blend'))
arm=bpy.data.objects['ForestDoctorRig'];scene=bpy.context.scene
arm.animation_data.action=bpy.data.actions['Idle'];scene.frame_set(1)
for obj in scene.objects:
    if obj.name.startswith(('UpperTooth','LowerTooth')):
        for v in obj.data.vertices:v.co.y+=.035
    elif obj.name in ('UpperGum','LowerGum'):
        for v in obj.data.vertices:v.co.y+=.032
    elif obj.name=='Tongue':
        for v in obj.data.vertices:v.co.y+=.055
    elif obj.name=='OralCavity':
        old=Vector((.015,-.438,3.045));new=Vector((.015,-.400,3.060))
        for v in obj.data.vertices:
            d=v.co-old;v.co=new+Vector((d.x*.092/.108,d.y*.060/.070,d.z*.040/.065))
actions=author_actions(arm);scene.frame_end=121
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'森林小博士.blend'),compress=True)
for obj in scene.objects:obj.select_set(obj.type in {'MESH','ARMATURE'})
bpy.context.view_layer.objects.active=arm
bpy.ops.export_scene.gltf(filepath=str(OUT/'森林小博士.glb'),export_format='GLB',use_selection=True,
    export_image_format='WEBP',export_image_quality=96,export_animations=True,export_animation_mode='ACTIONS',
    export_force_sampling=True,export_morph=True,export_skins=True,export_extras=True)
cam=scene.camera;scene.cycles.samples=20
for name,clip,frame,location,target in [('face_closed','Idle',1,(0,-6,3.40),(0,-.1,3.40)),
    ('face_open','Speaking',29,(0,-6,3.40),(0,-.1,3.40)),('body_gesture','Speaking',29,(3,-7,3.2),(0,0,2.0))]:
    arm.animation_data.action=actions[clip];scene.frame_set(frame);cam.location=location
    cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=1.4 if name.startswith('face') else 4.5
    scene.render.filepath=str(OUT/'preview'/(name+'.png'));bpy.ops.render.render(write_still=True)
print('BLENDER_REFINEMENT_COMPLETE')
