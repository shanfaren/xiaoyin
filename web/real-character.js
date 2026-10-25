/* Real mesh only: GLB/GLTF scene, never a photo plane or video substitute.
   Performance layer: natural blinking, audio-driven jaw + lip rounding,
   head prosody (nods / sway / tilt). All additive, rig stays intact. */
(function(root){
  'use strict';

  /* ---------- Eyelid textures (v6, settled in face-upgrade lab) ---------- */
  // Upper lid: an inverted bowl that covers the upper ~80% of the eye, with a
  // soft warm-skin gradient and a curved lash line along its lower edge.
  function makeUpperLidTexture(T){
    var W=288,H=200,c=document.createElement('canvas');c.width=W;c.height=H;var x=c.getContext('2d');
    x.clearRect(0,0,W,H);
    var cx=W/2,cy=138,rx=106,ry=104;
    x.save();
    for(var i=20;i>=0;i--){
      var t=i/20,rr=1+t*0.14;
      var g=x.createRadialGradient(cx,cy-30,rx*0.1,cx,cy-20,rx*rr);
      g.addColorStop(0,'#d9b68d');g.addColorStop(0.4,'#c69e74');g.addColorStop(0.7,'#b28a5e');g.addColorStop(0.9,'#9c7248');g.addColorStop(1,'rgba(126,88,58,0)');
      x.globalAlpha=t<0.26?0.06:1;x.fillStyle=g;
      x.beginPath();x.ellipse(cx,cy,rx*rr,ry*rr,0,0,Math.PI*2);x.fill();
    }
    x.globalAlpha=1;
    var lashY=H-14;
    x.strokeStyle='#2c180d';x.lineCap='round';
    for(var w=0;w<6;w++){
      x.lineWidth=11-w*1.6;x.globalAlpha=0.98-w*0.12;
      x.beginPath();x.moveTo(cx-rx*0.94,lashY);x.quadraticCurveTo(cx,lashY-26,cx+rx*0.94,lashY);x.stroke();
    }
    x.globalAlpha=1;x.restore();
    var tex=new T.CanvasTexture(c);tex.colorSpace=T.SRGBColorSpace;return tex;
  }
  // Lower lid: a thin strip along the lower rim, warm skin with a soft upper line.
  function makeLowerLidTexture(T){
    var W=288,H=110,c=document.createElement('canvas');c.width=W;c.height=H;var x=c.getContext('2d');
    x.clearRect(0,0,W,H);
    var cx=W/2,cy=-26,rx=106,ry=100;
    x.save();
    for(var i=20;i>=0;i--){
      var t=i/20,rr=1+t*0.12;
      var g=x.createRadialGradient(cx,cy+60,rx*0.1,cx,cy+70,rx*rr);
      g.addColorStop(0,'#d2ad84');g.addColorStop(0.5,'#bd9468');g.addColorStop(0.85,'#a27850');g.addColorStop(1,'rgba(126,88,58,0)');
      x.globalAlpha=t<0.26?0.06:1;x.fillStyle=g;
      x.beginPath();x.ellipse(cx,cy,rx*rr,ry*rr,0,0,Math.PI*2);x.fill();
    }
    x.globalAlpha=1;
    x.strokeStyle='rgba(94,58,34,0.6)';x.lineCap='round';x.lineWidth=5;
    x.beginPath();x.moveTo(cx-rx*0.9,12);x.quadraticCurveTo(cx,34,cx+rx*0.9,12);x.stroke();
    x.restore();
    var tex=new T.CanvasTexture(c);tex.colorSpace=T.SRGBColorSpace;return tex;
  }

  // Attach eyelid planes to the head bone. Coordinates are Head-local, measured
  // from the production GLB in the face-upgrade lab (see debug.html eyes[]).
  function buildEyelids(T,headBone){
    var upMat=new T.MeshBasicMaterial({map:makeUpperLidTexture(T),transparent:true,depthWrite:false,side:T.DoubleSide});
    var loMat=new T.MeshBasicMaterial({map:makeLowerLidTexture(T),transparent:true,depthWrite:false,side:T.DoubleSide});
    var eyes=[[-0.127,0.188,0.468,0.108,0.088],[0.128,0.224,0.458,0.104,0.084]];
    var lids=[];
    eyes.forEach(function(d){
      var ex=d[0],ey=d[1],ez=d[2],rw=d[3],rh=d[4];
      var upP=new T.Group();upP.position.set(ex,ey+rh,ez+0.004);
      var Hup=rh*1.8;
      var up=new T.Mesh(new T.PlaneGeometry(rw*2.1,Hup),upMat);
      up.position.set(0,-Hup/2,0);
      upP.add(up);upP.scale.y=0;headBone.add(upP);
      var loP=new T.Group();loP.position.set(ex,ey-rh,ez+0.004);
      var Hlo=rh*0.72;
      var lo=new T.Mesh(new T.PlaneGeometry(rw*2.0,Hlo),loMat);
      lo.position.set(0,Hlo/2,0);
      loP.add(lo);loP.scale.y=0;headBone.add(loP);
      lids.push({up:upP,lo:loP});
    });
    return lids;
  }

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
        var clips=gltf.animations,action=null,last=-1;
        var mouths=[];
        var bones={};model.traverse(function(o){if(o.isBone)bones[o.name]=o;});
        var jawBone=bones.Jaw,headBone=bones.Head;
        var jawBind=jawBone?jawBone.quaternion.clone():null;
        var headBind=headBone?headBone.quaternion.clone():null;
        var axis=(jawBone&&jawBone.userData.forestSpeechAxis)||[1,0,0];
        var jawAxis=new T.Vector3(axis[0],axis[1],axis[2]).normalize();
        var jawDelta=new T.Quaternion();
        model.traverse(function(o){
          if(o.morphTargetDictionary&&o.morphTargetInfluences){
            Object.keys(o.morphTargetDictionary).forEach(function(name){
              if(/^(jawOpen|mouthOpen|viseme_aa|aa|mouthRound)$/i.test(name))mouths.push({mesh:o,index:o.morphTargetDictionary[name]});
            });
          }
        });
        // Eyelid rig (v6).
        var lids=headBone?buildEyelids(T,headBone):[];
        // Blink state machine: quick close, brief hold, slower open; idle interval
        // shortens while speaking, with occasional double blinks for realism.
        var blink={amount:0,phase:0,t:0,next:0.9,left:0};
        // Lip-sync state.
        var jawLevel=0,roundLevel=0;

        /* ---- Gesture & body-motion rig (procedural, additive over bind) ----
           Rotation axes were verified against the rig in the face-upgrade lab:
           upper arm x- lifts the arm forward, RArm z+ / LArm z- abduct outward,
           forearm x- flexes the elbow. Poses are hand-tuned to read as calm
           teacher-like gestures rather than T-pose / mechanical swings. */
        var armKeys=['RArm','RFore','RHand','LArm','LFore','LHand'];
        var armNameMap={RArm:'RightArm',RFore:'RightForeArm',RHand:'RightHand',LArm:'LeftArm',LFore:'LeftForeArm',LHand:'LeftHand'};
        var armBones={},armBind={};
        var spineBone=bones.Spine,spineBind=spineBone?spineBone.quaternion.clone():null;
        armKeys.forEach(function(k){armBones[k]=bones[armNameMap[k]];armBind[k]=armBones[k]?armBones[k].quaternion.clone():null;});
        var GPOSES={
          rest:{},
          talkRight:{RArm:[-0.62,0,0.2],RFore:[-1.08,0,0.15],RHand:[-0.1,0,0.07]},
          talkLeft:{LArm:[-0.62,0,-0.2],LFore:[-1.08,0,-0.15],LHand:[-0.1,0,-0.07]},
          pointRight:{RArm:[-0.7,0,0.24],RFore:[-1.2,0,0.16],RHand:[-0.14,0,0.1]},
          pointLeft:{LArm:[-0.7,0,-0.24],LFore:[-1.2,0,-0.16],LHand:[-0.14,0,-0.1]},
          openBoth:{RArm:[-0.46,0,0.46],RFore:[-0.66,0,0.22],LArm:[-0.46,0,-0.46],LFore:[-0.66,0,-0.22]},
          presentR:{RArm:[-0.92,0,0.4],RFore:[-0.4,0,0.13],RHand:[0,0,0.06]},
          presentL:{LArm:[-0.92,0,-0.4],LFore:[-0.4,0,-0.13],LHand:[0,0,-0.06]},
          bothFront:{RArm:[-0.72,0,0.34],RFore:[-0.98,0,0.12],LArm:[-0.72,0,-0.34],LFore:[-0.98,0,-0.12]},
          think:{RArm:[-0.72,0,0.26],RFore:[-1.55,0,0.16],RHand:[-0.18,0,0.08]},
          listen:{RArm:[-0.26,0,0.1],RFore:[-0.42,0,0.06]}
        };
        // Single-hand explaining/presenting gestures dominate; two-hand and
        // raised "emphasis" gestures are rarer so the motion stays calm.
        var TALK_GEST=['talkRight','talkRight','talkLeft','talkLeft','presentR','presentL','openBoth','bothFront','pointRight','pointLeft'];
        function rand(a,b){return a+Math.random()*(b-a);}
        function pickGesture(){return TALK_GEST[Math.floor(Math.random()*TALK_GEST.length)];}
        var gState={pose:'rest',until:0.6,state:'idle'};
        var gCur={},gTgt={};
        armKeys.forEach(function(k){gCur[k]=[0,0,0];gTgt[k]=[0,0,0];});
        var gEuler=new T.Euler(),gQuat=new T.Quaternion();
        var gSpineCur={x:0,y:0,z:0},gSpineTgt={x:0,y:0,z:0};
        var gEulerSpine=new T.Euler(),gQuatSpine=new T.Quaternion();
        function updateGesture(state,t,dt,level,reduced){
          if(!armBones.RArm)return;
          if(gState.state!==state){gState.state=state;gState.pose='rest';gState.until=t+0.4;}
          // Reduced motion only calms the flourishes; speaking gestures remain
          // (smaller amplitude, slower cadence) so the doctor still "talks with
          // his hands" rather than freezing. Thinking/listening poses go to rest.
          var calm=reduced?0.45:1;
          var want;
          if(state==='speaking'){
            if(t>=gState.until){
              if(gState.pose==='rest'){gState.pose=pickGesture();gState.until=t+(reduced?rand(3.6,6.2):rand(2.2,4.2));}
              else{gState.pose='rest';gState.until=t+(reduced?rand(1.0,2.0):rand(0.4,1.0));}
            }
            want=gState.pose;
          }else if(state==='thinking'){want=reduced?'rest':'think';}
          else if(state==='listening'){want=reduced?'rest':((Math.sin(t*0.21)>0.35)?'listen':'rest');}
          else{want='rest';}
          var pose=GPOSES[want]||GPOSES.rest;
          // When speech quiets mid-gesture, hands ease a touch toward rest.
          var energy=(state==='speaking'?(0.82+0.18*Math.max(0,level)):1)*calm;
          for(var i=0;i<armKeys.length;i++){
            var k=armKeys[i],a=pose[k],tx=0,ty=0,tz=0;
            if(a){
              tx=a[0]*energy;ty=a[1]*energy;tz=a[2]*energy;
              tx+=Math.sin(t*0.9+i*1.7)*0.006*calm;   // tiny organic drift, never frozen
              tz+=Math.sin(t*0.7+i*2.3)*0.006*calm;
            }
            gTgt[k][0]=tx;gTgt[k][1]=ty;gTgt[k][2]=tz;
          }
          var gk=Math.min(1,dt*4.0);
          for(var j=0;j<armKeys.length;j++){
            var kk=armKeys[j];
            if(!armBones[kk]||!armBind[kk])continue;
            for(var c=0;c<3;c++)gCur[kk][c]+=(gTgt[kk][c]-gCur[kk][c])*gk;
            gEuler.set(gCur[kk][0],gCur[kk][1],gCur[kk][2],'XYZ');
            gQuat.setFromEuler(gEuler);
            armBones[kk].quaternion.copy(armBind[kk]).multiply(gQuat);
          }
          // Spine: breathing, attentive lean, gentle torso turn.
          var sTx=0,sTy=0,sTz=0;
          sTx=0.012+0.016*Math.sin(t*1.1);     // breathing always stays (natural)
          if(state==='speaking'){
            sTx+=(0.025+level*0.02)*calm;
            sTy=reduced?0.02*Math.sin(t*0.93):(0.045*Math.sin(t*0.4)+0.02*Math.sin(t*0.93));
          }
          else if(state==='listening'){sTx+=0.06*calm;sTy=reduced?0:0.03*Math.sin(t*0.35);}
          else if(state==='thinking'){sTx+=0.05*calm;sTy=reduced?0:0.05*Math.sin(t*0.2);}
          sTz=reduced?0:0.012*Math.sin(t*0.33);
          gSpineTgt.x=sTx;gSpineTgt.y=sTy;gSpineTgt.z=sTz;
          var sk=Math.min(1,dt*2.2);
          gSpineCur.x+=(gSpineTgt.x-gSpineCur.x)*sk;
          gSpineCur.y+=(gSpineTgt.y-gSpineCur.y)*sk;
          gSpineCur.z+=(gSpineTgt.z-gSpineCur.z)*sk;
          if(spineBone&&spineBind){
            gEulerSpine.set(gSpineCur.x,gSpineCur.y,gSpineCur.z,'YXZ');
            gQuatSpine.setFromEuler(gEulerSpine);
            spineBone.quaternion.copy(spineBind).multiply(gQuatSpine);
          }
        }

        // Head prosody state (euler radians) and smoothed current values.
        var hp={x:0,y:0,z:0},hc={x:0,y:0,z:0};
        var headDelta=new T.Quaternion(),headEuler=new T.Euler();
        var qtmp=new T.Quaternion();

        function select(state){
          if(!mixer)return;
          var pattern=state==='speaking'?/talk|speak|chat/i:state==='listening'?/listen/i:/idle|breath|stand/i;
          var clip=clips.find(function(c){return pattern.test(c.name);})||clips[0];
          var next=mixer.clipAction(clip);
          if(next!==action){if(action)action.fadeOut(.25);next.reset().fadeIn(.25).play();action=next;}
        }
        function setLids(s){
          for(var i=0;i<lids.length;i++){lids[i].up.scale.y=s*0.85;lids[i].lo.scale.y=s*0.48;}
        }
        function updateBlink(dt,state,speaking){
          var b=blink;b.t+=dt;
          if(b.phase===0){ // idle wait
            b.amount=0;
            if(b.t>=b.next){b.phase=1;b.t=0;}
          }else if(b.phase===1){ // close (~0.085s)
            b.amount=Math.min(1,b.t/0.085);
            if(b.t>=0.085){b.phase=2;b.t=0;}
          }else if(b.phase===2){ // hold (~0.03s)
            b.amount=1;
            if(b.t>=0.03){b.phase=3;b.t=0;}
          }else{ // open (~0.11s)
            b.amount=Math.max(0,1-b.t/0.11);
            if(b.t>=0.11){
              b.phase=0;b.t=0;
              if(b.left>0){b.left--;b.next=0.12;}
              else{
                var base=speaking?1.15:state==='listening'?1.9:2.6;
                b.next=base*0.5+Math.random()*base*0.9;
                if(Math.random()<(speaking?0.22:0.1))b.left=1; // occasional double
              }
            }
          }
          setLids(b.amount);
        }
        function updateHead(dt,state,t,level,reduced){
          // Target prosody by state. Sign convention verified against the rig:
          // +x pitch tips the face UP (so a nod/look-down is negative x),
          // y = turn, z = tilt.
          var tx=0,ty=0,tz=0;
          if(state==='speaking'){
            tx=-0.03-level*0.06+0.012*Math.sin(t*0.9);          // beat nod on loud syllables
            ty=0.06*Math.sin(t*0.53)+0.02*Math.sin(t*1.27);     // gentle sway
            tz=0.035*Math.sin(t*0.31);                          // soft tilt
          }else if(state==='listening'){
            tx=-0.02;
            tz=0.06+0.01*Math.sin(t*0.5);                        // attentive head tilt
            ty=0.05+0.02*Math.sin(t*0.4);
          }else if(state==='thinking'){
            tx=0.04;
            tz=0.045*Math.sin(t*0.25);
            ty=0.08*Math.sin(t*0.18);
          }else{
            tx=-0.005+0.015*Math.sin(t*0.5);
            ty=0.05*Math.sin(t*0.22);
            tz=0.028*Math.sin(t*0.17);
          }
          var hcalm=reduced?0.5:1;
          hp.x=tx*hcalm;hp.y=ty*hcalm;hp.z=tz*hcalm;
          // Critically damped smoothing so state changes never snap.
          var k=Math.min(1,dt*6);
          hc.x+=(hp.x-hc.x)*k;hc.y+=(hp.y-hc.y)*k;hc.z+=(hp.z-hc.z)*k;
          if(headBone&&headBind){
            headEuler.set(hc.x,hc.y,hc.z,'YXZ');
            headDelta.setFromEuler(headEuler);
            // Rebuild from bind every frame (prevents drift accumulation) and
            // layer our prosody; the clip's body motion is untouched.
            headBone.quaternion.copy(headBind).multiply(headDelta);
          }
        }
        resolve({root:wrapper,meshes:meshes,vertices:vertices,update:function(state,t,reduced){
          select(state);
          var dt=Math.max(0,last<0?0:Math.min(.1,t-last));
          if(mixer)mixer.update(dt);
          last=t;
          wrapper.position.y=0;wrapper.rotation.z=0;
          // Lip-sync while speaking is essential feedback (not decorative), so it
          // runs under reduced motion too; only extra flourish is toned down.
          var speaking=(state==='speaking');
          var level=speaking?(root.forestSpeechLevel?root.forestSpeechLevel():0):0;
          if(level<0)level=0;else if(level>1)level=1;
          // Fast attack, slower release so the jaw snaps open on syllables and
          // eases shut between phrases; clamp the opening so it never gapes.
          var rate=level>jawLevel?26:13;
          jawLevel+=(level-jawLevel)*Math.min(1,rate*dt);
          var roundRate=level>roundLevel?12:9;
          roundLevel+=(level-roundLevel)*Math.min(1,roundRate*dt);
          var jawOpen=jawLevel*0.30;
          if(jawBone&&jawBind){
            jawBone.quaternion.copy(jawBind).multiply(jawDelta.setFromAxisAngle(jawAxis,jawOpen));
          }
          // Lip rounding follows the envelope with a lag so lip shape varies
          // instead of tracking the jaw 1:1.
          var mr=roundLevel*0.6;
          mouths.forEach(function(m){m.mesh.morphTargetInfluences[m.index]=mr;});
          root.__jawDebug={level:level,jaw:jawLevel,round:roundLevel,open:jawOpen};
          // Blinking is an involuntary, natural micro-motion — keep it in every
          // mode (the old code froze the eyes open under reduced motion).
          updateBlink(dt,state,speaking);
          // Head prosody and arm gestures are passed the real state; their own
          // functions scale amplitude down when reduced motion is requested.
          updateHead(dt,state,t,jawLevel,reduced);
          // Arm gestures + spine breathing/lean (after mixer.update so it wins).
          updateGesture(state,t,dt,jawLevel,reduced);
        }});
      },undefined,reject);
    });
  };
})(window);
