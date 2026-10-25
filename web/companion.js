(function () {
  'use strict';
  var $=function(id){return document.getElementById(id);};
  var ready=false,loading=false,active=false,sceneData=null,state='idle',lastAnswer='',notice='',frame=0,previous=0;
  var reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function bridge(){return window.forestConversation;}
  function snapshot(){return bridge()?bridge().snapshot():{state:'idle'};}
  function sync(){
    var s=snapshot(); state=s.state;
    $('companionPurpose').value=s.profile||'qa';$('companionPurpose').disabled=!!s.busy||!!s.recording;
    $('companionTalk').textContent=s.recording?'松开结束':s.busy?'正在回答…':'按住说话';
    $('companionCancel').hidden=!s.recording;
    $('companionReplay').hidden=!lastAnswer||s.recording||s.busy;
    $('companionState').textContent=s.recording?'我在听，松开结束录音':s.busy?'让我想一想…':state==='speaking'?'正在和你说话':state==='thinking'?'正在准备声音…':'按住下方按钮，说说你的发现';
    $('characterStage').setAttribute('aria-label',s.recording?'点击森林小博士取消当前录音':'轻点听自我介绍，长按下方按钮开始语音输入');
    $('characterStage').dataset.state=state;
  }
  function showCaption(text){$('companionCaption').textContent=text;$('companionCaption').scrollTop=0;}
  function setView(view){
    cancelAnimationFrame(frame);frame=0;previous=0;
    active=view==='3d';document.body.classList.toggle('avatar-view',active);$('companion').hidden=!active;
    $('view3d').setAttribute('aria-pressed',String(active));$('viewChat').setAttribute('aria-pressed',String(!active));
    try{localStorage.setItem('forest_view_mesh',view);}catch(e){}
    if(active){loadScene();if(ready){resize();animate();}sync();}
    else {cancelAnimationFrame(frame);frame=0;previous=0;}
  }
  function loadScene(){
    if(ready||loading)return;
    loading=true;
    $('modelLoading').hidden=false;$('modelLoading').textContent='正在加载 2D 角色…';
    var slowHint=setTimeout(function(){if(!ready&&loading)$('modelLoading').textContent='网络较慢，角色仍在加载…';},4500);
    function script(url){return new Promise(function(resolve,reject){var s=document.createElement('script');s.src=url;s.onload=resolve;s.onerror=reject;document.head.appendChild(s);});}
    (window.THREE?Promise.resolve():script('/static/vendor/three.min.js'))
      .then(function(){return window.loadForestCharacter2D(window.THREE);})
      .then(function(character){
        clearTimeout(slowHint);
        if(new URLSearchParams(location.search).get('avatarAudit')==='1')window.__forestCharacter2D=character;
        createScene(character);ready=true;loading=false;$('modelLoading').hidden=true;resize();if(active)animate();
      })
      .catch(function(e){clearTimeout(slowHint);loading=false;console.error('Character load failed',e);$('modelLoading').textContent='角色加载失败，请刷新页面或切换“文字聊天”。';});
  }
  function createScene(character){
    var T=window.THREE,scene=new T.Scene(),camera=new T.PerspectiveCamera(32,1,.1,80);
    camera.position.set(0,2.15,8);camera.lookAt(0,2.0,0);
    var renderer=new T.WebGLRenderer({antialias:true,alpha:true,powerPreference:'low-power'});
    renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.7));renderer.setClearColor(0,0);
    renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.25;
    renderer.shadowMap.enabled=true;renderer.shadowMap.type=T.PCFSoftShadowMap;
    $('characterStage').appendChild(renderer.domElement);
    scene.add(new T.HemisphereLight(0xfff8e8,0x9ba788,2.8));
    var key=new T.DirectionalLight(0xffedce,3.4);key.position.set(-3,7,5);key.castShadow=true;
    key.shadow.mapSize.set(512,512);key.shadow.camera.left=-3;key.shadow.camera.right=3;key.shadow.camera.top=5;key.shadow.camera.bottom=-2;key.shadow.normalBias=.04;scene.add(key);
    var fill=new T.DirectionalLight(0xe7f6e9,1.8);fill.position.set(4,4,-3);scene.add(fill);
    scene.add(character.root);
    // The illustrated forest is a CSS background; WebGL only draws the character.
    sceneData={renderer:renderer,camera:camera,scene:scene,character:character};
    renderer.domElement.addEventListener('webglcontextlost',function(e){e.preventDefault();ready=false;cancelAnimationFrame(frame);frame=0;previous=0;$('modelLoading').hidden=false;$('modelLoading').textContent='角色画面暂时中断，请刷新页面或切换文字聊天。';});
    if(window.ResizeObserver)new ResizeObserver(resize).observe($('characterStage'));
    window.addEventListener('resize',resize);
  }
  function resize(){
    if(!sceneData||!active)return;var box=$('characterStage').getBoundingClientRect();if(!box.width||!box.height)return;
    var d=sceneData;d.camera.aspect=box.width/box.height;d.camera.position.z=d.camera.aspect<.50?6.5:7;
    d.camera.updateProjectionMatrix();d.renderer.setSize(box.width,box.height,false);
  }
  function animate(t){
    if(!active||!ready||document.hidden){frame=0;return;}frame=requestAnimationFrame(animate);
    if(!t||(previous&&t-previous<33))return;
    var dt=previous?Math.min((t-previous)/1000,.05):0;
    previous=t;
    var d=sceneData;
    d.character.update(state,t/1000,reduced,dt);
    d.renderer.render(d.scene,d.camera);
  }
  $('view3d').addEventListener('click',function(){setView('3d');});
  $('viewChat').addEventListener('click',function(){setView('chat');});
  function talk(){
    notice='';
    var s=snapshot();
    if(s.recording){if(bridge())bridge().cancel();sync();return;}
    if(s.busy){$('btnStop').click();sync();return;}
    showCaption('我是森林小博士。想提问时，请长按下方“按住说话”，说完后再松开。');
    if(bridge()&&bridge().welcome)bridge().welcome();
  }
  window.bindForestHold($('companionTalk'),function(){return bridge().holdStart();},function(cancel){bridge().holdEnd(cancel);});
  $('characterStage').addEventListener('click',talk);
  $('companionCancel').addEventListener('click',function(){bridge().cancel();sync();});
  $('companionReplay').addEventListener('click',function(){bridge().replay(lastAnswer);sync();});
  $('companionPurpose').addEventListener('change',function(){bridge().profile(this.value);sync();});
  window.addEventListener('forest:state',function(e){state=e.detail.state;sync();});
  window.addEventListener('forest:question',function(e){showCaption('让我想一想…');});
  window.addEventListener('forest:transcript',function(e){showCaption('我听到：'+e.detail.text);});
  window.addEventListener('forest:partial',function(e){showCaption(e.detail.text);});
  window.addEventListener('forest:answer',function(e){lastAnswer=e.detail.text;showCaption(lastAnswer);sync();});
  window.addEventListener('forest:notice',function(e){notice=e.detail.text;if(lastAnswer && notice.indexOf('欢迎回来')===0)return;showCaption(notice);});
  new MutationObserver(sync).observe($('btnStop'),{attributes:true,attributeFilter:['hidden']});
  new MutationObserver(sync).observe($('recLayer'),{attributes:true,attributeFilter:['hidden']});
  new MutationObserver(sync).observe($('interactionTabs'),{attributes:true,subtree:true,attributeFilter:['aria-pressed']});
  document.addEventListener('visibilitychange',function(){if(document.hidden){cancelAnimationFrame(frame);frame=0;previous=0;}else if(active&&ready)animate();});
  $('btnNew').addEventListener('click',function(){if(snapshot().busy)return;lastAnswer='';showCaption('你好呀，我们一起寻找大自然的隐身高手吧！');sync();});
  var preferred='3d';try{preferred=localStorage.getItem('forest_view_mesh')||'3d';}catch(e){}
  setView(preferred==='chat'?'chat':'3d');
})();
