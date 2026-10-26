const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
test('60-second PCM recording preserves its duration and final spoken samples',async()=>{
 const window={};vm.runInNewContext(fs.readFileSync('web/live-transcription.js','utf8'),{window,Blob,Float32Array,ArrayBuffer,DataView});
 const chunks=Array.from({length:60},()=>new Float32Array(48000));chunks[59].fill(.75,48000-4800);
 const blob=window.ForestLiveTranscription.wav(chunks,48000),view=new DataView(await blob.arrayBuffer());
 assert.equal(blob.type,'audio/wav');assert.equal(view.getUint32(24,true),16000);
 assert.equal(view.getUint32(40,true),60*16000*2);assert.equal(blob.size,44+60*16000*2);
 assert.ok(view.getInt16(blob.size-2,true)>24000,'last tenth of a second is preserved');
});
