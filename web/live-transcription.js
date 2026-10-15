/* 现有文件识别接口的渐进预览；完整录音在松开后另行最终识别。 */
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
    // 每个目标采样点取源区间均值，保留整段时长。
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
    var context,source,processor,gain,timer,closed=false,inflight=false,chunks=[],controller;
    try{
      context=new Context();source=context.createMediaStreamSource(stream);
      processor=context.createScriptProcessor(4096,1,1);gain=context.createGain();gain.gain.value=0;
      processor.onaudioprocess=function(e){if(!closed)chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));};
      source.connect(processor);processor.connect(gain);gain.connect(context.destination);
      context.resume().catch(function(){});
    }catch(e){if(context)context.close();return null;}
    function snapshot(){return wav(chunks,context.sampleRate);}
    timer=setInterval(function(){
      if(closed||inflight||chunks.length*4096<context.sampleRate*2)return;
      inflight=true;controller=new AbortController();
      snapshot().arrayBuffer().then(function(buffer){
        if(closed)return;
        var bytes=new Uint8Array(buffer),binary='';for(var i=0;i<bytes.length;i++)binary+=String.fromCharCode(bytes[i]);
        return fetch('/api/asr',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,
          body:JSON.stringify({audio_base64:btoa(binary),format:'wav'})});
      }).then(function(r){return r&&r.json();}).then(function(j){if(!closed&&j&&j.ok&&j.text)onText(j.text);})
        .catch(function(){}).finally(function(){inflight=false;});
    },3000);
    return {stop:function(){
      if(closed)return null;
      var result=chunks.length?snapshot():null;closed=true;clearInterval(timer);if(controller)controller.abort();
      processor.onaudioprocess=null;source.disconnect();processor.disconnect();gain.disconnect();context.close();chunks=[];
      return result;
    }};
  }
  root.ForestLiveTranscription={create:create,wav:wav};
})(typeof window!=='undefined'?window:globalThis);
