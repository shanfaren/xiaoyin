"""Author the character, deformation rig, oral anatomy and clips entirely in Blender."""
import bpy, math, json, sys,array
from pathlib import Path
from mathutils import Vector, Matrix, Quaternion

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).resolve().parent))
from character_animation import author_actions
OUT=ROOT/'modeling'; OUT.mkdir(exist_ok=True)
PREVIEW=OUT/'preview'; PREVIEW.mkdir(exist_ok=True)
SOURCE=Path(r'C:\Users\17864\Downloads\b754e05d805849650d454ffcd64b0ab5.glb')
REPORT={}

def smooth(a,b,x):
    t=max(0,min(1,(x-a)/(b-a)));return t*t*(3-2*t)
def lipline(x):
    d=x-.015;return 3.077+.12*d+1.3*d*d
def select_only(obj):
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(SOURCE))
body=next(o for o in bpy.context.scene.objects if o.type=='MESH')
body.name='ForestDoctor_Body'
body.data.transform(body.matrix_world);body.matrix_world=Matrix.Identity(4)
coords=[v.co.copy() for v in body.data.vertices]
lo=Vector([min(v[i] for v in coords) for i in range(3)])
hi=Vector([max(v[i] for v in coords) for i in range(3)])
center=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,lo.z));scale=3.9/(hi.z-lo.z)
for v in body.data.vertices:v.co=(v.co-center)*scale
body.data.update()
REPORT['original_faces']=len(body.data.polygons)
select_only(body)
decimate=body.modifiers.new('Preserve appearance / classroom LOD','DECIMATE');decimate.ratio=.16
decimate.delimit={'UV','NORMAL'}
bpy.ops.object.modifier_apply(modifier=decimate.name)
print('STAGE: Blender reduction complete',flush=True)
body.data.calc_loop_triangles()
source_mesh=body.data
positions=[v.co.copy() for v in source_mesh.vertices]
seam_side={};edge_cache={};faces=[];face_uv=[];face_normals=[];cut=0
uv_layer=source_mesh.uv_layers.active.data
source_normals=array.array('f',[0.0])*(len(source_mesh.loops)*3)
source_mesh.corner_normals.foreach_get('vector',source_normals)
print('STAGE: Original shading normals captured in one batch',flush=True)

def add_polygon(poly,side):
    ids=[];uvs=[];normals=[]
    for v in poly:
        if v.get('index') is None:
            key=(v['edge'],side)
            if key not in edge_cache:
                edge_cache[key]=len(positions);positions.append(v['co']);seam_side[edge_cache[key]]=side
            index=edge_cache[key]
        else:index=v['index']
        ids.append(index);uvs.append(v['uv']);normals.append(v['normal'])
    for j in range(1,len(ids)-1):
        a,b,c=(ids[0],ids[j],ids[j+1])
        if (positions[b]-positions[a]).cross(positions[c]-positions[a]).length>1e-12:
            faces.append((a,b,c));face_uv.append((uvs[0],uvs[j],uvs[j+1]));face_normals.extend((normals[0],normals[j],normals[j+1]))

def distance(v):return v['co'].z-lipline(v['co'].x)
def clip(tri,side):
    result=[]
    for i in range(3):
        a,b=tri[i],tri[(i+1)%3];da,db=distance(a),distance(b)
        ai,bi=da*side>=0,db*side>=0
        if ai:result.append(a)
        if ai!=bi:
            low,high=0.,1.
            for _ in range(26):
                t=(low+high)/2;p=a['co'].lerp(b['co'],t)
                if (p.z-lipline(p.x))*da>0:low=t
                else:high=t
            t=(low+high)/2
            result.append({'co':a['co'].lerp(b['co'],t),'uv':a['uv'].lerp(b['uv'],t),
                           'normal':a['normal'].lerp(b['normal'],t).normalized(),
                           'edge':tuple(sorted((a['index'],b['index'])))})
    return result

for tri in source_mesh.loop_triangles:
    verts=[{'co':positions[index],'uv':uv_layer[loop].uv.copy(),'normal':Vector(source_normals[loop*3:loop*3+3]),'index':index} for index,loop in zip(tri.vertices,tri.loops)]
    near=all(abs(v['co'].x-.015)<.152 and 3.005<v['co'].z<3.155 and v['co'].y<-.43 for v in verts)
    if near and min(distance(v) for v in verts)<0<max(distance(v) for v in verts):
        cut+=1
        for side in (-1,1):add_polygon(clip(verts,side),side)
    else:add_polygon(verts,0)

mesh=bpy.data.meshes.new('OriginalFace_WithLocalLipSeam');mesh.from_pydata(positions,[],faces);mesh.update()
for mat in source_mesh.materials:mesh.materials.append(mat)
uv=mesh.uv_layers.new(name='UVMap')
for poly,values in zip(mesh.polygons,face_uv):
    poly.use_smooth=True
    for loop,value in zip(poly.loop_indices,values):uv.data[loop].uv=value
mesh.normals_split_custom_set([tuple(v) for v in face_normals]);body.data=mesh
for material in mesh.materials:
    if material.use_nodes:
        for node in material.node_tree.nodes:
            if node.type=='NORMAL_MAP':node.inputs['Strength'].default_value=.35
print('STAGE: Preserved face, UV atlas, and imported shading',flush=True)
REPORT.update(working_faces=len(faces),lip_seam_triangles=cut,lip_seam_vertices=len(seam_side))

# Preserve the original texture atlas and face; no replacement face patch or atlas interpolation.
for image in bpy.data.images:
    if image.source=='FILE' and max(image.size)>2048:
        aspect=image.size[1]/image.size[0]
        if image.size[0]>=image.size[1]:image.scale(2048,max(1,round(2048*aspect)))
        else:image.scale(max(1,round(2048/aspect)),2048)
    if image.source in {'FILE','GENERATED'}:
        try:image.pack()
        except RuntimeError:pass

arm_data=bpy.data.armatures.new('ForestDoctor_AnatomicalRig')
arm=bpy.data.objects.new('ForestDoctorRig',arm_data);bpy.context.collection.objects.link(arm)
arm.show_in_front=True;arm.data.display_type='OCTAHEDRAL'
select_only(arm);bpy.ops.object.mode_set(mode='EDIT')
definitions={}
def bone(name,head,tail,parent=None):
    b=arm.data.edit_bones.new(name);b.head=head;b.tail=tail
    if parent:b.parent=arm.data.edit_bones[parent]
    definitions[name]=(Vector(head),Vector(tail));return b
bone('Hips',(0,0,1.80),(0,0,2.13))
bone('Spine',(0,0,2.13),(0,0,2.46),'Hips')
bone('Chest',(0,0,2.46),(0,-.02,2.82),'Spine')
bone('Neck',(0,-.02,2.82),(0,-.04,3.04),'Chest')
bone('Head',(0,-.04,3.04),(0,-.04,3.68),'Neck')
bone('Jaw',(.015,-.30,3.057),(.015,-.54,3.057),'Head')
for sign,side in ((1,'Left'),(-1,'Right')):
    bone(side+'Arm',(sign*.44,-.04,2.69),(sign*.61,-.12,2.20),'Chest')
    bone(side+'ForeArm',(sign*.61,-.12,2.20),(sign*.68,-.14,1.78),side+'Arm')
    bone(side+'Hand',(sign*.68,-.14,1.78),(sign*.69,-.15,1.50),side+'ForeArm')
    bone(side+'UpLeg',(sign*.22,0,1.75),(sign*.25,-.02,1.03),'Hips')
    bone(side+'Leg',(sign*.25,-.02,1.03),(sign*.28,-.10,.29),side+'UpLeg')
    bone(side+'Foot',(sign*.28,-.10,.29),(sign*.28,-.38,.16),side+'Leg')
bpy.ops.object.mode_set(mode='OBJECT')
groups={n:body.vertex_groups.new(name=n) for n in definitions}
for i,p in enumerate(positions):
    x,forward,height=p.x,-p.y,p.z;side='Left' if x>=0 else 'Right';w={}
    def add(name,value):
        if value>1e-7:w[name]=w.get(name,0)+value
    boundary=min(.510,.425+max(0,2.65-height)*.10)
    arm_w=smooth(boundary,boundary+.060,abs(x))*(1-smooth(2.72,2.87,height))*smooth(1.25,1.40,height)*smooth(-.43,-.24,forward)
    fore=1-smooth(2.10,2.30,height);hand=1-smooth(1.73,1.84,height)
    add(side+'Arm',arm_w*(1-fore));add(side+'ForeArm',arm_w*fore*(1-hand));add(side+'Hand',arm_w*fore*hand)
    remain=1-arm_w
    h=smooth(2.90,3.14,height)*(smooth(-.22,.02,forward)+(1-smooth(-.22,.02,forward))*smooth(3.12,3.28,height))
    d=height-lipline(x);lower=seam_side.get(i,-1 if d<0 else 1)<0
    jaw=(1-smooth(.065,.120,abs(x-.015)))*smooth(.40,.51,forward)*math.exp(-((d/.115)**2)) if lower else 0
    add('Jaw',remain*h*jaw);add('Head',remain*h*(1-jaw));remain*=1-h
    if height<1.80:
        leg=1-smooth(.93,1.13,height);foot=1-smooth(.25,.43,height)
        add(side+'UpLeg',remain*(1-leg));add(side+'Leg',remain*leg*(1-foot));add(side+'Foot',remain*leg*foot)
    else:
        c=smooth(2.08,2.48,height);add('Chest',remain*c);add('Spine',remain*(1-c))
    selected=sorted(w.items(),key=lambda pair:pair[1],reverse=True)[:4];total=sum(v for _,v in selected)
    for name,value in selected:groups[name].add([i],value/total,'REPLACE')
modifier=body.modifiers.new('True bone deformation','ARMATURE');modifier.object=arm;modifier.use_deform_preserve_volume=False
body.parent=arm
body.shape_key_add(name='Basis')
round_key=body.shape_key_add(name='mouthRound')
for i,p in enumerate(positions):
    d=p.z-lipline(p.x);mask=(1-smooth(.06,.13,abs(p.x-.015)))*smooth(.4,.51,-p.y)*math.exp(-((d/.06)**2))
    round_key.data[i].co.x-=(p.x-.015)*.08*mask;round_key.data[i].co.y-=.003*mask

def material(name,color,roughness):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    shader=m.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=(*color,1);shader.inputs['Roughness'].default_value=roughness
    return m
ivory=material('Natural ivory enamel',(.89,.86,.78),.30)
gum=material('Soft gum',(.25,.035,.045),.82)
dark=material('Shadowed oral cavity',(.035,.004,.008),1)
tongue_mat=material('Tongue',(.34,.055,.070),.88)

def bind_rigid(obj,name):
    group=obj.vertex_groups.new(name=name);group.add(list(range(len(obj.data.vertices))),1,'REPLACE')
    mod=obj.modifiers.new('Jaw / head articulation','ARMATURE');mod.object=arm;obj.parent=arm
    for p in obj.data.polygons:p.use_smooth=True

def sphere(name,position,radius,mat,group):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=12,location=position)
    obj=bpy.context.object;obj.name=name;obj.scale=radius;select_only(obj);bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    obj.data.materials.append(mat);bind_rigid(obj,group);return obj

# All interior surfaces sit behind the original facial surface.
sphere('OralCavity',(.015,-.400,3.060),(.092,.060,.040),dark,'Head')
sphere('UpperGum',(.015,-.471,3.078),(.082,.011,.009),gum,'Head')
sphere('LowerGum',(.015,-.466,3.051),(.078,.011,.009),gum,'Jaw')
sphere('Tongue',(.015,-.430,3.046),(.063,.025,.009),tongue_mat,'Jaw')
for row in ('Upper','Lower'):
    for i in range(8):
        dx=(i-3.5)*.0185;h=lipline(.015+dx);depth=-.485+.014*(dx/.08)**2
        z=h-.010 if row=='Upper' else h-.024
        width=.0168 if abs(dx)<.04 else .0152;height=.018 if row=='Upper' else .013
        bpy.ops.mesh.primitive_cube_add(size=1,location=(.015+dx,depth,z))
        tooth=bpy.context.object;tooth.name=f'{row}Tooth{i}';tooth.dimensions=(width,.012,height)
        select_only(tooth);bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        bevel=tooth.modifiers.new('Rounded enamel edges','BEVEL');bevel.width=.0032;bevel.segments=4
        bpy.ops.object.modifier_apply(modifier=bevel.name)
        bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
        tooth.data.materials.append(ivory);bind_rigid(tooth,'Head' if row=='Upper' else 'Jaw')

local_axes={}
for b in arm.data.bones:
    local_axes[b.name]=b.matrix_local.to_3x3().inverted()@Vector((1,0,0))
jaw_axis=local_axes['Jaw'];arm.data.bones['Jaw']['forestSpeechAxis']=list(jaw_axis)
arm['forestSpeechAxis']=list(jaw_axis);arm['forestBlenderRig']=True
def pose_world(name,axis,angle):
    b=arm.pose.bones[name];b.rotation_mode='QUATERNION';local=arm.data.bones[name].matrix_local.to_3x3().inverted()@Vector(axis)
    b.rotation_quaternion=Quaternion(local,angle)

scene=bpy.context.scene;scene.render.fps=30
actions=author_actions(arm);scene.frame_start=1;scene.frame_end=121;scene.frame_set(1)
REPORT.update(bones=len(arm.data.bones),jaw_axis=list(jaw_axis),animations=list(actions),oral_objects=20)

# Warm studio setup in the editable project; export selects only character objects.
character_objects=[o for o in scene.objects if o.type in {'MESH','ARMATURE'}]
world=bpy.data.worlds.new('Warm studio');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.78,.73,.65,1);world.node_tree.nodes['Background'].inputs[1].default_value=.55;scene.world=world
def area(name,location,power,size,target=(0,0,2.3)):
    data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape='DISK';data.size=size
    obj=bpy.data.objects.new(name,data);scene.collection.objects.link(obj);obj.location=location;obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
area('Large soft key',(-3,-5,7),450,5);area('Soft fill',(4,-2,4),240,4);area('Rim',(-2,3,5),350,3)
cam_data=bpy.data.cameras.new('Review camera');cam=bpy.data.objects.new('Review camera',cam_data);scene.collection.objects.link(cam);scene.camera=cam
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=24;scene.cycles.use_denoising=True
scene.render.resolution_x=640;scene.render.resolution_y=800;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False
scene.view_settings.view_transform='AgX'
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'森林小博士.blend'),compress=True)
for obj in scene.objects:obj.select_set(obj in character_objects)
bpy.context.view_layer.objects.active=arm
bpy.ops.export_scene.gltf(filepath=str(OUT/'森林小博士.glb'),export_format='GLB',use_selection=True,
    export_image_format='WEBP',export_image_quality=96,export_animations=True,export_animation_mode='ACTIONS',
    export_force_sampling=True,export_morph=True,export_morph_normal=False,export_skins=True,export_extras=True,
    export_meshopt_compression_enable=True,export_meshopt_extension='EXT_meshopt_compression')
(OUT/'Blender检查结果.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding='utf-8')
if '--skip-render' in sys.argv:
    print('FOREST_BLENDER_BUILD_COMPLETE',json.dumps(REPORT));sys.exit(0)

def render(name,clip,frame,location,target):
    arm.animation_data.action=actions[clip];scene.frame_set(frame)
    cam.location=location;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.type='ORTHO';cam.data.ortho_scale=1.40 if name.startswith('face') else 4.50
    scene.render.filepath=str(PREVIEW/(name+'.png'));bpy.ops.render.render(write_still=True)
for args in [('face_closed','Idle',1,(0,-6,3.40),(0,-.1,3.40)),
             ('face_open','Speaking',13,(0,-6,3.40),(0,-.1,3.40)),
             ('body_gesture','Speaking',33,(3,-7,3.2),(0,0,2.0))]:render(*args)
print('FOREST_BLENDER_BUILD_COMPLETE',json.dumps(REPORT))
