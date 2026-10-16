const fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path');
global.window=global;global.self=global;global.THREE=require('../web/vendor/three.min.js');
global.MeshoptDecoder=require('../web/vendor/meshopt_decoder.js');
require('../web/vendor/GLTFLoader.js');
const OriginalLoader=THREE.GLTFLoader;
THREE.GLTFLoader=class extends OriginalLoader{
  load(file,ok,progress,error){
    const raw=fs.readFileSync(file),size=raw.readUInt32LE(12),doc=JSON.parse(raw.subarray(20,20+size));
    delete doc.images;delete doc.textures;delete doc.samplers;doc.materials=[{}];
    doc.meshes.forEach(m=>m.primitives.forEach(p=>p.material=0));
    const json=Buffer.from(JSON.stringify(doc)),padded=Buffer.alloc(Math.ceil(json.length/4)*4,32);json.copy(padded);
    const bin=raw.subarray(20+size),out=Buffer.alloc(20+padded.length+bin.length);
    out.write('glTF');out.writeUInt32LE(2,4);out.writeUInt32LE(out.length,8);out.writeUInt32LE(padded.length,12);out.writeUInt32LE(0x4e4f534a,16);padded.copy(out,20);bin.copy(out,20+padded.length);
    this.parse(out.buffer.slice(out.byteOffset,out.byteOffset+out.byteLength),'',ok,error);
  }
};
require('../web/real-character.js');
(async()=>{
  const c=await loadForestCharacter(THREE,path.resolve(__dirname,'../assets/models/forest-doctor.glb'));
  c.update('idle',0,false);c.root.updateMatrixWorld(true);
  const box=new THREE.Box3().setFromObject(c.root,true),size=box.getSize(new THREE.Vector3());
  console.log('Actual neutral world bounds',box.min.toArray(),box.max.toArray(),'size',size.toArray());
  assert.ok(Math.abs(size.y-3.9)<.03,'Neutral model must be 3.9 units tall');
  const bone=c.root.getObjectByName('LeftForeArm');assert.ok(bone,'Forearm bone must be present');
  let mesh;c.root.traverse(o=>{if(o.isSkinnedMesh&&o.morphTargetDictionary&&'mouthRound' in o.morphTargetDictionary)mesh=o;});assert.ok(mesh);
  const jaw=c.root.getObjectByName('Jaw'),jawRest=jaw.quaternion.clone(),forearmRest=bone.quaternion.clone();
  const joint=mesh.skeleton.bones.findIndex(b=>b.name==='LeftForeArm'),js=mesh.geometry.attributes.skinIndex,ws=mesh.geometry.attributes.skinWeight;
  let sample=-1;for(let i=0;i<js.count&&sample<0;i++)for(let j=0;j<4;j++)if(js.getComponent(i,j)===joint&&ws.getComponent(i,j)>.65){sample=i;break;}
  assert.ok(sample>=0,'Forearm vertices must actually be weighted to the forearm bone');
  const point=()=>{c.root.updateMatrixWorld(true);mesh.skeleton.update();return mesh.getVertexPosition(sample,new THREE.Vector3()).applyMatrix4(mesh.matrixWorld);};
  const restPoint=point();global.forestSpeechLevel=()=>.8;
  for(let i=1;i<=40;i++)c.update('speaking',i/30,false);
  assert.ok(mesh.morphTargetInfluences[mesh.morphTargetDictionary.mouthRound]>.1);
  assert.ok(bone.quaternion.angleTo(forearmRest)>.05,'Forearm clip must rotate the actual joint');
  assert.ok(point().distanceTo(restPoint)>.05,'Joint rotation must move the skinned forearm surface');
  assert.ok(jaw.quaternion.angleTo(jawRest)>.05,'Speech amplitude must rotate the real jaw joint');
  assert.ok(c.root.getObjectByName('UpperTooth0'),'Individual upper teeth must exist');
  assert.ok(c.root.getObjectByName('LowerTooth0'),'Individual lower teeth must exist');
  global.forestSpeechLevel=()=>0;for(let i=0;i<40;i++)c.update('idle',2+i/30,false);
  assert.ok(mesh.morphTargetInfluences[0]<.001,'Mouth must close when speech ends');
  assert.ok(jaw.quaternion.angleTo(jawRest)<.001,'Jaw must return to the Blender bind orientation within float32 precision');
  const restError=bone.quaternion.clone().normalize().angleTo(forearmRest.clone().normalize());
  console.log('Forearm normalized rest angle error',restError);
  assert.ok(restError<.02,'Idle restores the relaxed forearm, allowing the authored small breathing motion');
  assert.ok(point().distanceTo(restPoint)<.05,'Idle must relax the actual forearm surface');
  assert.equal(c.root.position.length(),0,'Movement must come from the skeleton, not whole-model bobbing');
  console.log('Passed: GLB decoding, neutral size, actual rig and mouth morph, speaking and reset.');
})().catch(e=>{console.error(e);process.exitCode=1;});
