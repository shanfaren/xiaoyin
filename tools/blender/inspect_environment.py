import bpy,json
from pathlib import Path
from mathutils import Vector
root=Path(__file__).resolve().parents[2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=r'C:\Users\17864\Downloads\b754e05d805849650d454ffcd64b0ab5.glb')
objects=[]
for obj in bpy.data.objects:
    if obj.type=='MESH':
        corners=[obj.matrix_world@Vector(v) for v in obj.bound_box]
        objects.append(dict(name=obj.name,vertices=len(obj.data.vertices),faces=len(obj.data.polygons),
          minimum=[min(v[i] for v in corners) for i in range(3)],maximum=[max(v[i] for v in corners) for i in range(3)]))
export={}
for p in bpy.ops.export_scene.gltf.get_rna_type().properties:
    if p.identifier in ['export_image_format','export_animation_mode','export_actions','export_nla_strips','export_force_sampling','export_morph','export_draco_mesh_compression_enable']:
        export[p.identifier]=[x.identifier for x in p.enum_items] if p.type=='ENUM' else p.default
report={'version':bpy.app.version_string,'objects':objects,'export_options':export}
(root/'data/blender_environment.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
