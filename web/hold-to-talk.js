(function(root){
  'use strict';
  root.bindForestHold=function(button,start,finish){
    var active=false,pointer=null,started=0;
    function down(e){
      if(active||button.disabled||(e.button!==undefined&&e.button!==0))return;
      e.preventDefault();active=true;pointer=e.pointerId;started=Date.now();
      if(pointer!==undefined&&button.setPointerCapture)button.setPointerCapture(pointer);
      button.classList.add('holding');
      if(start()===false){active=false;button.classList.remove('holding');}
    }
    function up(e,cancel){
      if(!active||(e.pointerId!==undefined&&pointer!==null&&e.pointerId!==pointer))return;
      e.preventDefault();active=false;button.classList.remove('holding');
      finish(cancel||Date.now()-started<350);pointer=null;
    }
    button.addEventListener('pointerdown',down);
    button.addEventListener('pointerup',function(e){up(e,false);});
    button.addEventListener('pointercancel',function(e){up(e,true);});
    button.addEventListener('lostpointercapture',function(e){up(e,true);});
    button.addEventListener('contextmenu',function(e){e.preventDefault();});
    button.addEventListener('click',function(e){e.preventDefault();});
    button.addEventListener('keydown',function(e){if((e.code==='Space'||e.code==='Enter')&&!e.repeat)down(e);});
    button.addEventListener('keyup',function(e){if(e.code==='Space'||e.code==='Enter')up(e,false);});
    root.addEventListener('blur',function(){up({preventDefault:function(){}},true);});
  };
})(window);
