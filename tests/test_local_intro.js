const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
test('intro starts automatically after character ready and replays on every explicit reopen',()=>{
  const window=new EventTarget();let roleOpens=0,plays=0;
  const document=new EventTarget();document.getElementById=id=>id==='view3d'?{click(){roleOpens++;}}:null;
  vm.runInNewContext(fs.readFileSync('web/local-desktop.js','utf8'),{window,document,Promise});
  window.forestDesktop.requestIntro(()=>{plays++;});
  assert.equal(plays,0);
  window.dispatchEvent(new Event('forest:character-ready'));assert.equal(plays,1);
  window.dispatchEvent(new Event('forest:character-ready'));assert.equal(plays,1);
  window.forestDesktop.replayIntroduction();window.forestDesktop.replayIntroduction();
  assert.equal(plays,3);assert.equal(roleOpens,2);
});
test('desktop framing fills its allocated area without cutting head, feet or open arms',()=>{
  const window=new EventTarget(),document=new EventTarget();
  vm.runInNewContext(fs.readFileSync('web/local-desktop.js','utf8'),{window,document,Promise});
  for(const [width,height] of [[620,560],[460,370],[336,260],[300,650],[900,300]]){
    const frame=window.ForestDesktopLayout.frame(width,height);
    assert.ok(frame.fillHeight<=0.94001);assert.ok(frame.fillWidth<=0.94001);
    assert.ok(Math.max(frame.fillHeight,frame.fillWidth)>.93999);
  }
});
test('collapsing cancels microphone capture and pauses playback without replacing the session',()=>{
  const window=new EventTarget(),document=new EventTarget();let canceled=0,paused=0;
  window.forestConversation={cancel(){canceled++;},desktopPause(){paused++;},sessionId:'keep-this-session'};
  vm.runInNewContext(fs.readFileSync('web/local-desktop.js','utf8'),{window,document,Promise});
  window.forestDesktop.pauseForCollapse();
  assert.equal(canceled,1);assert.equal(paused,1);assert.equal(window.forestConversation.sessionId,'keep-this-session');
});
