// Browser recording regression tests with fake devices; no microphone or UI access.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const nodes=new Map(),uploads=[];
const node=id=>{if(!nodes.has(id))nodes.set(id,{hidden:true,dataset:{},parentElement:{dataset:{}},focus(){}});return nodes.get(id);};
class Recorder {
  constructor(){this.state='inactive';this.mimeType='audio/webm';Recorder.last=this;Recorder.count++;}
  start(interval){this.interval=interval;this.state='recording';}
  stop(){this.state='inactive';Promise.resolve().then(()=>{
    this.ondataavailable({data:new Blob(['last-words'])});this.onstop();
  });}
}
Recorder.count=0;
class Speech {start(){}stop(){this.onend();}abort(){}}
const context={console,Blob,Promise,setTimeout,clearTimeout,CustomEvent:function(){},
  document:{readyState:'loading',getElementById:node,addEventListener(){}},
  navigator:{userAgent:'test',mediaDevices:{getUserMedia:()=>Promise.resolve({getTracks:()=>[{stop(){}}]})}},
  location:{protocol:'https:',hostname:'test'},MediaRecorder:Recorder,
  window:{dispatchEvent(){},SpeechRecognition:Speech,MediaRecorder:Recorder}};
let source=fs.readFileSync('web/app.js','utf8');
source=source.replace("  if (document.readyState === 'loading')",`
  unlockPlayback=function(){};
  transcribe=function(blob){window.uploads.push(blob);};
  window.testVoice={S:S,start:startRecording,stop:stopRecording,fallback:fallbackSpeechRecognition};
  if (document.readyState === 'loading')`);
context.window.uploads=uploads;vm.runInNewContext(source,context);
const voice=context.window.testVoice;
(async()=>{
  voice.start();await Promise.resolve();
  const recorder=Recorder.last;
  assert.equal(recorder.interval,250);
  recorder.ondataavailable({data:new Blob(['first-words|'])});
  voice.stop(true);voice.start(); // immediate retry must wait for final data event
  assert.equal(Recorder.count,1);
  await Promise.resolve();
  assert.equal(await uploads[0].text(),'first-words|last-words');
  assert.equal(voice.S.micPending,false);
  voice.start();await Promise.resolve();voice.stop(false);await Promise.resolve();
  assert.equal(uploads.length,1,'cancelled recording must not upload');
  let permit,stopped=0;
  context.navigator.mediaDevices.getUserMedia=()=>new Promise(resolve=>permit=resolve);
  voice.start();voice.stop(true);
  permit({getTracks:()=>[{stop(){stopped++;}}]});await Promise.resolve();
  assert.equal(Recorder.count,2,'release before permission must not start a later recording');
  assert.equal(stopped,1);
  voice.fallback('');
  const rec=voice.S.speechRec;
  assert.equal(rec.continuous,true);
  const segment=t=>Object.assign([{transcript:t}],{isFinal:true});
  rec.onresult({results:[segment('竹节虫为什么')]});
  rec.onresult({results:[segment('竹节虫为什么'),segment('能躲过小鸟的眼睛？')]});
  voice.stop(true);
  assert.equal(node('asrText').value,'竹节虫为什么能躲过小鸟的眼睛？');
  console.log('PASS final recording chunk, pending-stop isolation, cancellation and all speech segments');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>clearTimeout(voice.S.recordTimer));
