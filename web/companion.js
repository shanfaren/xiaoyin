(function () {
  'use strict';
  var $=function(id){return document.getElementById(id);};
  var ready=false,loading=false,active=false,sceneData=null,state='idle',lastAnswer='',notice='',frame=0,previous=0;
  var reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var drag=null,turned=-.10,lastDrag=0;
  var movie=window.createCharacterPlayback($('companionVideo'),$('companionPoster'));
  function bridge(){return window.forestConversation;}
  function snapshot(){return bridge()?bridge().snapshot():{state:'idle'};}
  function sync(){
    var s=snapshot(); state=s.state;
    $('companionPurpose').value=s.profile||'qa';$('companionPurpose').disabled=!!s.busy||!!s.recording;
    $('companionTalk').textContent=s.recording?'说完了，发送':s.busy?'停止回答':state==='speaking'?'打断，再说一句':'点击说话';
    $('companionCancel').hidden=!s.recording;
    $('companionReplay').hidden=!lastAnswer||s.recording||s.busy;
    $('companionState').textContent=s.recording?'我在听，说完再点一下我':s.busy?'让我想一想…':state==='speaking'?'正在和你说话':state==='thinking'?'正在准备声音…':'点击我，说说你的发现';
    $('characterStage').setAttribute('aria-label',s.recording?'点击森林小博士停止录音并发送':'点击森林小博士开始说话');
    $('characterStage').dataset.state=state;
    movie.update(state==='speaking',active,!document.hidden);
  }
  function showCaption(text){$('companionCaption').textContent=text;$('companionCaption').scrollTop=0;}
  function setView(view){
    cancelAnimationFrame(frame);frame=0;
    active=view==='3d';document.body.classList.toggle('avatar-view',active);$('companion').hidden=!active;
    movie.update(state==='speaking',active,!document.hidden);
    $('view3d').setAttribute('aria-pressed',String(active));$('viewChat').setAttribute('aria-pressed',String(!active));
    try{localStorage.setItem('forest_view',view);}catch(e){}
    if(active){loadScene();if(ready){resize();animate();}sync();}
    else {cancelAnimationFrame(frame);frame=0;}
  }
  function loadScene(){
    if(ready||loading)return;
    // Display the approved character honestly until a usable mesh is available.
    if($('characterStage').dataset.preview==='true')return;
    loading=true;
    function init(){try{createScene();ready=true;loading=false;$('modelLoading').hidden=true;resize();animate();}catch(e){failed();}}
    function failed(){loading=false;$('modelLoading').textContent='这台设备暂时无法显示立体角色，请切换“文字聊天”，语音功能仍可使用。';}
    if(window.THREE){init();return;}
    var script=document.createElement('script');script.src='/static/vendor/three.min.js';script.onload=init;script.onerror=failed;document.head.appendChild(script);
  }
  function createScene(){
    var T=window.THREE,scene=new T.Scene(),camera=new T.PerspectiveCamera(32,1,.1,80);
    camera.position.set(0,2.25,9);camera.lookAt(0,2.05,0);
    var renderer=new T.WebGLRenderer({antialias:true,alpha:true,powerPreference:'low-power'});
    renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.7));renderer.setClearColor(0,0);
    renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.25;
    renderer.shadowMap.enabled=true;renderer.shadowMap.type=T.PCFSoftShadowMap;
    $('characterStage').appendChild(renderer.domElement);
    scene.add(new T.HemisphereLight(0xfff8e8,0x9ba788,2.8));
    var key=new T.DirectionalLight(0xffedce,3.4);key.position.set(-3,7,5);key.castShadow=true;
    key.shadow.mapSize.set(512,512);key.shadow.camera.left=-3;key.shadow.camera.right=3;key.shadow.camera.top=5;key.shadow.camera.bottom=-2;key.shadow.normalBias=.04;scene.add(key);
    var fill=new T.DirectionalLight(0xe7f6e9,1.8);fill.position.set(4,4,-3);scene.add(fill);
    var character=window.createForestCharacter(T);scene.add(character.root);
    var ground=new T.Mesh(new T.CircleGeometry(2,64),new T.ShadowMaterial({color:0x526249,opacity:.16}));ground.rotation.x=-Math.PI/2;ground.position.y=-.015;ground.receiveShadow=true;scene.add(ground);
    sceneData={renderer:renderer,camera:camera,scene:scene,character:character};
    renderer.domElement.addEventListener('webglcontextlost',function(e){e.preventDefault();ready=false;cancelAnimationFrame(frame);frame=0;$('modelLoading').hidden=false;$('modelLoading').textContent='立体画面暂时中断，请刷新页面或切换文字聊天。';});
    if(window.ResizeObserver)new ResizeObserver(resize).observe($('characterStage'));
    window.addEventListener('resize',resize);
  }
  function resize(){
    if(!sceneData||!active)return;var box=$('characterStage').getBoundingClientRect();if(!box.width||!box.height)return;
    var d=sceneData;d.camera.aspect=box.width/box.height;d.camera.position.z=d.camera.aspect<.68?10.3:9;
    d.camera.updateProjectionMatrix();d.renderer.setSize(box.width,box.height,false);
  }
  function animate(t){
    if(!active||!ready||document.hidden){frame=0;return;}frame=requestAnimationFrame(animate);
    if(!t||t-previous<33)return;previous=t;
    var d=sceneData;d.character.root.rotation.y=turned;d.character.update(state,t/1000,reduced);d.renderer.render(d.scene,d.camera);
  }
  $('view3d').addEventListener('click',function(){setView('3d');});
  $('viewChat').addEventListener('click',function(){setView('chat');});
  function talk(){notice='';if(bridge()){bridge().talk();sync();}}
  $('companionTalk').addEventListener('click',talk);
  $('characterStage').addEventListener('click',function(){if(Date.now()-lastDrag>300)talk();});
  $('companionCancel').addEventListener('click',function(){bridge().cancel();sync();});
  $('companionReplay').addEventListener('click',function(){bridge().replay(lastAnswer);sync();});
  $('companionPurpose').addEventListener('change',function(){bridge().profile(this.value);sync();});
  $('characterStage').addEventListener('pointerdown',function(e){if($('characterStage').dataset.preview==='true')return;drag={x:e.clientX,angle:turned,moved:false};});
  $('characterStage').addEventListener('pointermove',function(e){if(!drag)return;var dx=e.clientX-drag.x;if(Math.abs(dx)>8){drag.moved=true;turned=Math.max(-1.1,Math.min(1.1,drag.angle+dx*.008));}});
  function endDrag(){if(drag&&drag.moved)lastDrag=Date.now();drag=null;}
  window.addEventListener('pointerup',endDrag);window.addEventListener('pointercancel',endDrag);
  window.addEventListener('forest:state',function(e){state=e.detail.state;sync();});
  window.addEventListener('forest:question',function(e){showCaption('让我想一想…');});
  window.addEventListener('forest:partial',function(e){showCaption(e.detail.text);});
  window.addEventListener('forest:answer',function(e){lastAnswer=e.detail.text;showCaption(lastAnswer);sync();});
  window.addEventListener('forest:notice',function(e){notice=e.detail.text;if(lastAnswer && notice.indexOf('欢迎回来')===0)return;showCaption(notice);});
  new MutationObserver(sync).observe($('btnStop'),{attributes:true,attributeFilter:['hidden']});
  new MutationObserver(sync).observe($('recLayer'),{attributes:true,attributeFilter:['hidden']});
  new MutationObserver(sync).observe($('interactionTabs'),{attributes:true,subtree:true,attributeFilter:['aria-pressed']});
  document.addEventListener('visibilitychange',function(){movie.update(state==='speaking',active,!document.hidden);if(document.hidden){cancelAnimationFrame(frame);frame=0;}else if(active&&ready)animate();});
  $('btnNew').addEventListener('click',function(){if(snapshot().busy)return;lastAnswer='';showCaption('你好呀，我们一起寻找大自然的隐身高手吧！');sync();});
  var preferred='3d';try{preferred=localStorage.getItem('forest_view')||'3d';}catch(e){}
  setView(preferred==='chat'?'chat':'3d');
})();
