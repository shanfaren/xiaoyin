const assert=require('assert'),fs=require('fs'),vm=require('vm');
let now=1000,started=0,finishes=[],listeners={},captured;
const button={disabled:false,classList:{add(){},remove(){}},setPointerCapture(n){captured=n;},
  addEventListener(n,fn){listeners[n]=fn;}};
const root={addEventListener(){}};
vm.runInNewContext(fs.readFileSync('web/hold-to-talk.js','utf8'),{window:root,Date:{now:()=>now}});
root.bindForestHold(button,()=>{started++;},cancel=>finishes.push(cancel));
const event={pointerId:1,button:0,preventDefault(){}};
listeners.pointerdown(event);assert.equal(started,1);assert.equal(captured,1);
now+=1000;listeners.pointerup(event);assert.deepEqual(finishes,[false]);
listeners.lostpointercapture(event);assert.equal(finishes.length,1);
listeners.pointerdown(event);now+=100;listeners.pointerup(event);assert.equal(finishes[1],true);
listeners.pointerdown(event);now+=1000;listeners.pointercancel(event);assert.equal(finishes[2],true);
console.log('PASS hold to start, release to finish, short-touch and cancelled-pointer handling');
let processAudio,tick,fetches=0,texts=[],releaseResolve;
const contextNode={connect(){},disconnect(){}};
class AudioContext {
  constructor(){this.sampleRate=48000;}
  createMediaStreamSource(){return contextNode;}
  createScriptProcessor(){const node={...contextNode};processAudio=node;return node;}
  createGain(){return {...contextNode,gain:{value:1}};}
  resume(){return Promise.resolve();}close(){}
}
const audioRoot={AudioContext};
vm.runInNewContext(fs.readFileSync('web/live-transcription.js','utf8'),{
  window:audioRoot,Blob,Float32Array,ArrayBuffer,DataView,AbortController,Uint8Array,
  setInterval(fn){tick=fn;return 1;},clearInterval(){},btoa:s=>Buffer.from(s,'binary').toString('base64'),
  fetch(url,options){fetches++;assert.equal(url,'/api/asr');
    const body=JSON.parse(options.body),bytes=Buffer.from(body.audio_base64,'base64');
    assert(bytes.length>64044);return Promise.resolve({json:()=>new Promise(resolve=>releaseResolve=resolve)});
  }});
(async()=>{
  const session=audioRoot.ForestLiveTranscription.create({},t=>texts.push(t));
  for(let i=0;i<36;i++)processAudio.onaudioprocess({inputBuffer:{getChannelData:()=>new Float32Array(4096)}});
  tick();await new Promise(resolve=>setImmediate(resolve));
  tick();assert.equal(fetches,1,'only one preview request at a time');
  const wav=session.stop();assert.equal(wav.type,'audio/wav');
  const bytes=Buffer.from(await wav.arrayBuffer());assert.equal(bytes.readUInt32LE(24),16000);
  assert.equal(bytes.readUInt32LE(40),36*4096/3*2);
  releaseResolve({ok:true,text:'late preview'});await new Promise(resolve=>setImmediate(resolve));
  assert.equal(texts.length,0,'late preview must not overwrite final recognition');
  console.log('PASS full-duration preview WAV, single in-flight recognition and stop isolation');
})().catch(error=>{console.error(error);process.exitCode=1;});
