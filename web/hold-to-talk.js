(function(root){
  'use strict';
  root.FOREST_HOLD_CONFIG={delayMs:280,cancelDistance:70};
  root.bindForestHold=function(button,start,finish){
    var active=false,engaged=false,pointer=null,started=0,startY=0,source='',touchAt=0;
    var engageTimer=null,cancelled=false;
    function prevent(e){if(e.preventDefault&&e.cancelable!==false)e.preventDefault();}
    function emit(phase,cancel){
      try{root.dispatchEvent(new root.CustomEvent('forest:hold-progress',{detail:{phase:phase,cancelled:!!cancel,engaged:engaged}}));}catch(ignore){}
    }
    function clearEngageTimer(){if(engageTimer){clearTimeout(engageTimer);engageTimer=null;}}
    function reset(){
      clearEngageTimer();active=false;engaged=false;pointer=null;source='';cancelled=false;
      button.classList.remove('pressing','holding','engaged','cancel-armed');
    }
    function engage(){
      if(!active||engaged)return;
      engaged=true;
      button.classList.add('holding','engaged');
      try{if(navigator.vibrate)navigator.vibrate(18);}catch(ignore){}
      emit('engaged',false);
      if(start({longPress:true})===false){reset();emit('aborted',true);}
    }
    function pointY(e){
      var touch=e.touches&&e.touches[0]||e.changedTouches&&e.changedTouches[0]||e;
      return typeof touch.clientY==='number'?touch.clientY:startY;
    }
    function move(e,kind){
      if(!active||(kind&&source&&source!==kind))return;
      var next=engaged&&pointY(e)<startY-root.FOREST_HOLD_CONFIG.cancelDistance;
      if(next!==cancelled){
        cancelled=next;
        button.classList.toggle('cancel-armed',cancelled);
        emit('moving',cancelled);
      }
      if(engaged)prevent(e);
    }
    function down(e,kind){
      if(active||button.disabled||(kind==='mouse'&&Date.now()-touchAt<800))return;
      if(kind!=='touch'&&e.button!==undefined&&e.button!==0)return;
      prevent(e);active=true;engaged=false;cancelled=false;source=kind;pointer=e.pointerId;started=Date.now();
      startY=pointY(e);
      if(kind==='touch')touchAt=started;
      button.classList.add('pressing');
      // 部分内置浏览器会抛出捕获异常；捕获失败不能阻断开始录音。
      if(kind==='pointer'&&pointer!==undefined&&button.setPointerCapture){try{button.setPointerCapture(pointer);}catch(ignore){}}
      engageTimer=setTimeout(engage,root.FOREST_HOLD_CONFIG.delayMs);
    }
    function up(e,cancel,kind){
      if(!active||(kind&&source!==kind)||(e.pointerId!==undefined&&pointer!==undefined&&pointer!==null&&e.pointerId!==pointer))return;
      prevent(e);clearEngageTimer();
      var wasEngaged=engaged,shouldCancel=!!cancel||cancelled||!wasEngaged;
      button.classList.remove('pressing','holding','engaged','cancel-armed');
      active=false;engaged=false;pointer=null;source='';cancelled=false;
      if(wasEngaged)finish(shouldCancel,{duration:Date.now()-started});
      else emit('aborted',true);
    }
    // 触屏直接处理touch事件，避免依赖微信/旧安卓内核的Pointer Events实现。
    button.addEventListener('touchstart',function(e){down(e,'touch');},{passive:false});
    root.addEventListener('touchmove',function(e){move(e,'touch');},{passive:false,capture:true});
    root.addEventListener('touchend',function(e){up(e,false,'touch');},{passive:false,capture:true});
    root.addEventListener('touchcancel',function(e){up(e,true,'touch');},{passive:false,capture:true});
    button.addEventListener('pointerdown',function(e){if(e.pointerType!=='touch')down(e,'pointer');});
    var pointerMove=function(e){move(e,'pointer');};
    var pointerUp=function(e){up(e,false,'pointer');},pointerCancel=function(e){up(e,true,'pointer');};
    root.addEventListener('pointermove',pointerMove,true);
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
    root.addEventListener('blur',function(){up({preventDefault:function(){},pointerId:pointer},true,source);});
  };
})(window);
