/* A reusable silent loop, driven by actual answer audio playback. */
(function (root) {
  'use strict';
  function createCharacterPlayback(video, poster) {
    var wanted=false, version=0;
    function reset() {
      video.pause();
      try { video.currentTime=0; } catch(e) {}
      video.hidden=true;poster.hidden=false;
    }
    function update(speaking, active, visible) {
      var next=!!(speaking&&active&&visible&&video.getAttribute('src'));
      if(next===wanted)return;
      wanted=next;var request=++version;
      if(!wanted){reset();return;}
      try {
        var playing=video.play();
        Promise.resolve(playing).then(function(){
          if(request!==version||!wanted){if(!wanted)reset();return;}
          video.hidden=false;poster.hidden=true;
        },function(){
          if(request!==version)return;
          wanted=false;reset();
        });
      } catch(e){wanted=false;reset();}
    }
    video.addEventListener('error',function(){wanted=false;++version;reset();});
    return {update:update,reset:function(){wanted=false;++version;reset();}};
  }
  if(typeof module!=='undefined'&&module.exports)module.exports=createCharacterPlayback;
  else root.createCharacterPlayback=createCharacterPlayback;
})(typeof window!=='undefined'?window:this);
