const assert=require('node:assert/strict');
const create=require('../web/character-playback.js');
async function run(){
  let resolvePlay;
  const events={};
  const video={hidden:true,currentTime:0,src:'talking.mp4',plays:0,pauses:0,
    getAttribute(){return this.src;}, addEventListener(e,fn){events[e]=fn;},
    pause(){this.pauses++;}, play(){this.plays++;return new Promise(resolve=>resolvePlay=resolve);}};
  const poster={hidden:false}, player=create(video,poster);
  player.update(false,true,true);assert.equal(video.plays,0);
  player.update(true,true,true);assert.equal(video.plays,1);
  resolvePlay();await Promise.resolve();assert.equal(video.hidden,false);assert.equal(poster.hidden,true);
  player.update(true,false,true);assert.equal(video.hidden,true);assert.equal(poster.hidden,false);
  player.update(true,true,true);player.update(false,true,true);
  resolvePlay();await Promise.resolve();assert.equal(video.hidden,true,'late play must not restart an ended answer');
  player.update(true,true,false);assert.equal(video.plays,2,'background tabs must not play');
  video.src='';player.update(true,true,true);assert.equal(video.plays,2,'missing animation preserves poster');
  video.src='talking.mp4';player.update(true,true,true);events.error();
  resolvePlay();await Promise.resolve();assert.equal(poster.hidden,false,'media error preserves voice and poster');
  console.log('Passed: speaking loop, switch view, late play, hidden page, missing file and media error.');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
