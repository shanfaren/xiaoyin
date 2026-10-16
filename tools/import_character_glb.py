"""Validate and install the approved character's real GLB mesh for the scan client."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import struct
import itertools

ROOT=Path(__file__).resolve().parents[1]


def scene_dimensions(doc):
    identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
    def multiply(a,b):
        return [sum(a[k*4+r]*b[c*4+k] for k in range(4)) for c in range(4) for r in range(4)]
    def local(n):
        if 'matrix' in n:return n['matrix']
        x,y,z,w=n.get('rotation',[0,0,0,1]);sx,sy,sz=n.get('scale',[1,1,1]);tx,ty,tz=n.get('translation',[0,0,0])
        return [(1-2*y*y-2*z*z)*sx,(2*x*y+2*z*w)*sx,(2*x*z-2*y*w)*sx,0,
                (2*x*y-2*z*w)*sy,(1-2*x*x-2*z*z)*sy,(2*y*z+2*x*w)*sy,0,
                (2*x*z+2*y*w)*sz,(2*y*z-2*x*w)*sz,(1-2*x*x-2*y*y)*sz,0,tx,ty,tz,1]
    lo=[float('inf')]*3;hi=[float('-inf')]*3
    def visit(index,parent):
        n=doc['nodes'][index];m=multiply(parent,local(n))
        if 'mesh' in n:
            for p in doc['meshes'][n['mesh']]['primitives']:
                a=doc['accessors'][p['attributes']['POSITION']]
                limits=[a['min'],a['max']]
                if a.get('normalized'):
                    div={5120:127,5121:255,5122:32767,5123:65535}[a['componentType']]
                    limits=[[max(-1,v/div) for v in row] for row in limits]
                for corner in itertools.product(*zip(*limits)):
                    for r in range(3):
                        v=sum(m[k*4+r]*corner[k] for k in range(3))+m[12+r]
                        lo[r]=min(lo[r],v);hi[r]=max(hi[r],v)
        for child in n.get('children',[]):visit(child,m)
    for root in doc['scenes'][doc.get('scene',0)]['nodes']:visit(root,identity)
    return [b-a for a,b in zip(lo,hi)]


def inspect_glb(path):
    raw=Path(path).read_bytes()
    if len(raw)<20 or raw[:4]!=b'glTF':raise ValueError('需要真实GLB文件，不能使用图片或视频改扩展名')
    magic,version,length=struct.unpack_from('<4sII',raw)
    if version!=2 or length!=len(raw):raise ValueError('GLB版本或长度无效')
    size,kind=struct.unpack_from('<II',raw,12)
    if kind!=0x4e4f534a:raise ValueError('GLB缺少JSON结构')
    doc=json.loads(raw[20:20+size].decode('utf-8'))
    meshes=doc.get('meshes',[]);accessors=doc.get('accessors',[])
    vertices=triangles=0;lo=[float('inf')]*3;hi=[float('-inf')]*3
    for mesh in meshes:
        for primitive in mesh.get('primitives',[]):
            if primitive.get('mode',4)!=4:raise ValueError('角色网格必须包含三角面')
            position=accessors[primitive['attributes']['POSITION']]
            vertices+=position['count']
            triangles+=(accessors[primitive['indices']]['count'] if 'indices' in primitive else position['count'])//3
            if 'min' in position and 'max' in position:
                for axis in range(3):
                    lo[axis]=min(lo[axis],position['min'][axis]);hi[axis]=max(hi[axis],position['max'][axis])
    dimensions=scene_dimensions(doc)
    if not meshes or not vertices or not all(0<d<float('inf') for d in dimensions):raise ValueError('没有有效三维网格或空间边界')
    if min(dimensions)<max(dimensions)*.02:raise ValueError('检测到近似平面，不能把图片卡片当成三维角色')
    if len(raw)>30*1024*1024:raise ValueError('模型超过30MB，请先优化后再用于手机')
    if any(b.get('uri') for b in doc.get('buffers',[])):raise ValueError('请导出内嵌数据的单个GLB文件')
    if any(i.get('uri') and not i['uri'].startswith('data:') for i in doc.get('images',[])):raise ValueError('纹理必须内嵌，不能依赖第三方外链')
    unsupported=set(doc.get('extensionsRequired',[]))&{'KHR_draco_mesh_compression','KHR_texture_basisu'}
    if 'EXT_meshopt_compression' in doc.get('extensionsRequired',[]) and not (ROOT/'web/vendor/meshopt_decoder.js').exists():
        raise ValueError('缺少Meshopt解码器')
    if unsupported:raise ValueError('请先导出未压缩GLB，或添加对应解码器：'+','.join(sorted(unsupported)))
    return dict(meshes=len(meshes),vertices=vertices,triangles=triangles,dimensions=dimensions,
                textures=len(doc.get('images',[])),animations=[c.get('name','') for c in doc.get('animations',[])],
                skinned=bool(doc.get('skins')),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--source',required=True)
    parser.add_argument('--license',required=True)
    args=parser.parse_args()
    details=inspect_glb(args.input)
    out=ROOT/'assets/models';out.mkdir(parents=True,exist_ok=True)
    shutil.copy2(args.input,out/'forest-doctor.glb')
    details.update(url='/assets/models/forest-doctor.glb?v='+details['sha256'][:12],source=args.source,license=args.license)
    (out/'character.json').write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(details,ensure_ascii=False))


if __name__=='__main__':main()
