/* Real mesh only: GLB/GLTF scene, never a photo plane or video substitute. */
(function(root){
  'use strict';
  root.loadForestCharacter=function(T,url){
    return new Promise(function(resolve,reject){
      var loader=new T.GLTFLoader();
      if(root.MeshoptDecoder)loader.setMeshoptDecoder(root.MeshoptDecoder);
      loader.load(url,function(gltf){
        var model=gltf.scene;model.updateMatrixWorld(true);
        model.traverse(function(o){if(o.isSkinnedMesh)o.skeleton.update();});
        var box=new T.Box3().setFromObject(model),size=new T.Vector3(),center=new T.Vector3();
        box.getSize(size);box.getCenter(center);
        if(!isFinite(size.y)||size.y<=0)return reject(new Error('Invalid model bounds'));
        var meshes=0,vertices=0;
        model.traverse(function(o){if(o.isMesh){meshes++;vertices+=o.geometry.attributes.position.count;o.castShadow=true;o.receiveShadow=true;}});
        if(!meshes||Math.min(size.x,size.y,size.z)<Math.max(size.x,size.y,size.z)*.02)return reject(new Error('A flat image is not a 3D character'));
        var wrapper=new T.Group(),normalized=new T.Group(),scale=3.9/size.y;
        // Preserve imported root transforms, including transforms targeted by clips.
        normalized.scale.setScalar(scale);
        normalized.position.set(-center.x*scale,-box.min.y*scale,-center.z*scale);
        normalized.add(model);wrapper.add(normalized);
        var mixer=gltf.animations.length?new T.AnimationMixer(model):null;
        var clips=gltf.animations,action=null,last=-1,mouths=[],mouthLevel=0;
        var bones={};model.traverse(function(o){if(o.isBone)bones[o.name]=o;});
        var jawBind=bones.Jaw?bones.Jaw.quaternion.clone():null;
        var axis=bones.Jaw&&bones.Jaw.userData.forestSpeechAxis||[1,0,0];
        var jawAxis=new T.Vector3(axis[0],axis[1],axis[2]).normalize(),jawDelta=new T.Quaternion();
        model.traverse(function(o){
          if(o.morphTargetDictionary&&o.morphTargetInfluences){
            Object.keys(o.morphTargetDictionary).forEach(function(name){
              if(/^(jawOpen|mouthOpen|viseme_aa|aa|mouthRound)$/i.test(name))mouths.push({mesh:o,index:o.morphTargetDictionary[name],gain:name==='mouthRound'?.40:1});
            });
          }
        });
        function select(state){
          if(!mixer)return;
          var pattern=state==='speaking'?/talk|speak|chat/i:state==='listening'?/listen/i:/idle|breath|stand/i;
          var clip=clips.find(function(c){return pattern.test(c.name);})||clips[0];
          var next=mixer.clipAction(clip);
          if(next!==action){if(action)action.fadeOut(.2);next.reset().fadeIn(.2).play();action=next;}
        }
        resolve({root:wrapper,meshes:meshes,vertices:vertices,update:function(state,t,reduced){
          select(reduced?'idle':state);
          if(mixer){mixer.update(last<0?0:Math.min(.1,t-last));}last=t;
          wrapper.position.y=0;wrapper.rotation.z=0;
          var speaking=state==='speaking',level=speaking?(root.forestSpeechLevel?root.forestSpeechLevel():0):0;
          mouthLevel+=(level-mouthLevel)*.5;
          mouths.forEach(function(m){m.mesh.morphTargetInfluences[m.index]=Math.max(0,Math.min(1,mouthLevel*m.gain));});
          // Compose on Blender's bind orientation; replacing Euler angles would break this rig.
          if(bones.Jaw)bones.Jaw.quaternion.copy(jawBind).multiply(jawDelta.setFromAxisAngle(jawAxis,.13*mouthLevel));
        }});
      },undefined,reject);
    });
  };
})(window);
