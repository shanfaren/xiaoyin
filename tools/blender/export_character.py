import bpy,json,math
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'modeling'
bpy.ops.wm.open_mainfile(filepath=str(OUT/'森林小博士.blend'))
scene=bpy.context.scene;arm=bpy.data.objects['ForestDoctorRig']
arm.animation_data.action=bpy.data.actions['Idle'];scene.frame_set(1)
for material in bpy.data.materials:
    if material.use_nodes:
        for node in material.node_tree.nodes:
            if node.type=='NORMAL_MAP':node.inputs['Strength'].default_value=.35
camera=scene.camera;camera.data.type='ORTHO';camera.data.ortho_scale=4.5
camera.location=(3,-7,3.2);camera.rotation_euler=(Vector((0,0,2))-camera.location).to_track_quat('-Z','Y').to_euler()
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_location=(0,0,2)
            area.spaces.active.region_3d.view_distance=6.3
            area.spaces.active.region_3d.view_rotation=(Vector((0,0,2))-Vector((1,-7,3))).to_track_quat('-Z','Y')
            area.spaces.active.shading.type='MATERIAL'
arm.show_in_front=False
scene.frame_end=121;bpy.context.preferences.filepaths.save_version=0
notes=bpy.data.texts.get('森林小博士_说明') or bpy.data.texts.new('森林小博士_说明')
notes.clear();notes.write('森林小博士：18根真实骨骼，完整肩/肘/腕层级，独立下颌骨。\n动作：Idle 待机 / Speaking 讲解 / Listening 倾听。\n嘴部保留原图纹理，仅在真实唇线建立局部接缝；上下排独立牙齿与口腔已绑定。\n手机端播放语音时以实际音量包络驱动下颌，不替换清爽男声音色。\n')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'森林小博士.blend'),compress=True)
for obj in scene.objects:obj.select_set(obj.type in {'MESH','ARMATURE'})
bpy.context.view_layer.objects.active=arm
bpy.ops.export_scene.gltf(filepath=str(OUT/'森林小博士.glb'),export_format='GLB',use_selection=True,
    export_image_format='WEBP',export_image_quality=96,export_animations=True,export_animation_mode='ACTIONS',
    export_force_sampling=True,export_morph=True,export_morph_normal=False,export_skins=True,export_extras=True,
    export_meshopt_compression_enable=True,export_meshopt_extension='EXT_meshopt_compression')
print('MOBILE_GLB_BYTES', (OUT/'森林小博士.glb').stat().st_size)
