(function(root){
  'use strict';
  root.bindForestHold=function(button,start,finish){
    var active=false,pointer=null,started=0,source='',touchAt=0;
    function prevent(e){if(e.preventDefault&&e.cancelable!==false)e.preventDefault();}
    function down(e,kind){
      if(active||button.disabled||(kind==='mouse'&&Date.now()-touchAt<800))return;
      if(kind!=='touch'&&e.button!==undefined&&e.button!==0)return;
      prevent(e);active=true;source=kind;pointer=e.pointerId;started=Date.now();
      if(kind==='touch')touchAt=started;
      button.classList.add('holding');
      // 部分内置浏览器会抛出捕获异常；捕获失败不能阻断开始录音。
      if(kind==='pointer'&&pointer!==undefined&&button.setPointerCapture){try{button.setPointerCapture(pointer);}catch(ignore){}}
      if(start()===false){active=false;button.classList.remove('holding');}
    }
    function up(e,cancel,kind){
      if(!active||(kind&&source!==kind)||(e.pointerId!==undefined&&pointer!==undefined&&pointer!==null&&e.pointerId!==pointer))return;
      prevent(e);active=false;button.classList.remove('holding');
      finish(cancel||Date.now()-started<350);pointer=null;source='';
    }
    // 触屏直接处理touch事件，避免依赖微信/旧安卓内核的Pointer Events实现。
    button.addEventListener('touchstart',function(e){down(e,'touch');},{passive:false});
    root.addEventListener('touchend',function(e){up(e,false,'touch');},{passive:false,capture:true});
    root.addEventListener('touchcancel',function(e){up(e,true,'touch');},{passive:false,capture:true});
    button.addEventListener('pointerdown',function(e){if(e.pointerType!=='touch')down(e,'pointer');});
    var pointerUp=function(e){up(e,false,'pointer');},pointerCancel=function(e){up(e,true,'pointer');};
    button.addEventListener('pointerup',pointerUp);root.addEventListener('pointerup',pointerUp,true);
    button.addEventListener('pointercancel',pointerCancel);root.addEventListener('pointercancel',pointerCancel,true);
    // 不因lostpointercapture提前取消；全局松开事件负责收尾。
    if(!root.PointerEvent){
      button.addEventListener('mousedown',function(e){down(e,'mouse');});
      root.addEventListener('mouseup',function(e){up(e,false,'mouse');},true);
    }
    button.addEventListener('contextmenu',function(e){e.preventDefault();});
    button.addEventListener('click',function(e){e.preventDefault();});
    button.addEventListener('selectstart',prevent);
    button.addEventListener('dragstart',prevent);
    button.addEventListener('keydown',function(e){if((e.code==='Space'||e.code==='Enter')&&!e.repeat)down(e,'key');});
    button.addEventListener('keyup',function(e){if(e.code==='Space'||e.code==='Enter')up(e,false,'key');});
    root.addEventListener('blur',function(){up({preventDefault:function(){}},true);});
  };
})(window);
