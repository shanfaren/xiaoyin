/* 流式语音识别实时预览；松手后的最终结果仍由 app.js 用完整 WAV 走 /api/asr。 */
(function(root){
  'use strict';
  function wav(chunks,rate){
    var length=chunks.reduce(function(n,c){return n+c.length;},0),input=new Float32Array(length),at=0;
    chunks.forEach(function(c){input.set(c,at);at+=c.length;});
    var count=Math.floor(length*16000/rate),bytes=new ArrayBuffer(44+count*2),d=new DataView(bytes);
    function str(o,s){for(var i=0;i<s.length;i++)d.setUint8(o+i,s.charCodeAt(i));}
    str(0,'RIFF');d.setUint32(4,36+count*2,true);str(8,'WAVE');str(12,'fmt ');
    d.setUint32(16,16,true);d.setUint16(20,1,true);d.setUint16(22,1,true);d.setUint32(24,16000,true);
    d.setUint32(28,32000,true);d.setUint16(32,2,true);d.setUint16(34,16,true);str(36,'data');d.setUint32(40,count*2,true);
    for(var n=0;n<count;n++){
      var a=Math.floor(n*rate/16000),b=Math.max(a+1,Math.floor((n+1)*rate/16000)),sum=0;
      for(var j=a;j<b&&j<length;j++)sum+=input[j];
      var v=Math.max(-1,Math.min(1,sum/(b-a)));d.setInt16(44+n*2,v<0?v*32768:v*32767,true);
    }
    return new Blob([bytes],{type:'audio/wav'});
  }
  function create(stream,onText){
    var Context=root.AudioContext||root.webkitAudioContext;
    if(!Context)return null;
    var context,source,processor,gain,closed=false,chunks=[],queue=[],streamId=null,sending=false,timer=null,fallbackTimer=null,controller=null;
    try{
      context=new Context();source=context.createMediaStreamSource(stream);
      processor=context.createScriptProcessor(4096,1,1);gain=context.createGain();gain.gain.value=0;
      processor.onaudioprocess=function(e){
        if(closed)return;
        var input=e.inputBuffer.getChannelData(0);
        chunks.push(new Float32Array(input));
        appendPcm(input,context.sampleRate);
      };
      source.connect(processor);processor.connect(gain);gain.connect(context.destination);
      context.resume().catch(function(){});
    }catch(e){if(context)context.close();return null;}
    function appendPcm(input,rate){
      var ratio=rate/16000,count=Math.floor(input.length/ratio);
      for(var n=0;n<count;n++){
        var a=Math.floor(n*ratio),b=Math.max(a+1,Math.floor((n+1)*ratio)),sum=0;
        for(var j=a;j<b&&j<input.length;j++)sum+=input[j];
        var v=Math.max(-1,Math.min(1,sum/(b-a)));
        var s=v<0?v*32768:v*32767;
        queue.push(s & 0xFF,(s>>8)&0xFF);
      }
    }
    function startStream(){
      fetch('/api/asr/stream/start',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})
        .then(function(r){return r.json();})
        .then(function(j){
          if(closed)return;
          if(j&&j.ok&&j.stream_id){streamId=j.stream_id;timer=setInterval(flush,200);}
          else startFallback();
        })
        .catch(function(){if(!closed)startFallback();});
    }
    function flush(){
      if(closed||sending||!streamId||!queue.length)return;
      sending=true;
      var bytes=queue;queue=[];
      var binary='';
      for(var i=0;i<bytes.length;i++)binary+=String.fromCharCode(bytes[i]);
      controller=new AbortController();
      fetch('/api/asr/stream/chunk',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,
        body:JSON.stringify({stream_id:streamId,audio_base64:btoa(binary)})})
        .then(function(r){return r.json();})
        .then(function(j){if(!closed&&j&&j.ok&&j.text)onText(j.text);})
        .catch(function(){})
        .finally(function(){sending=false;});
    }
    function startFallback(){
      if(fallbackTimer||closed)return;
      queue=[];
      fallbackTimer=setInterval(function(){
        if(closed||!chunks.length)return;
        var blob=wav(chunks,context.sampleRate);
        blob.arrayBuffer().then(function(buffer){
          if(closed)return;
          var bytes=new Uint8Array(buffer),binary='';
          for(var i=0;i<bytes.length;i++)binary+=String.fromCharCode(bytes[i]);
          return fetch('/api/asr',{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({audio_base64:btoa(binary),format:'wav'})});
        }).then(function(r){return r&&r.json();}).then(function(j){if(!closed&&j&&j.ok&&j.text)onText(j.text);})
          .catch(function(){});
      },3000);
    }
    startStream();
    return {stop:function(){
      if(closed)return null;
      var result=chunks.length?wav(chunks,context.sampleRate):null;
      closed=true;
      if(timer)clearInterval(timer);
      if(fallbackTimer)clearInterval(fallbackTimer);
      if(controller)controller.abort();
      if(streamId){
        try{fetch('/api/asr/stream/finish',{method:'POST',headers:{'Content-Type':'application/json',keepalive:true},
          body:JSON.stringify({stream_id:streamId})});}catch(e){}
      }
      processor.onaudioprocess=null;source.disconnect();processor.disconnect();gain.disconnect();context.close();
      chunks=[];queue=[];
      return result;
    }};
  }
  root.ForestLiveTranscription={create:create,wav:wav};
})(typeof window!=='undefined'?window:globalThis);
