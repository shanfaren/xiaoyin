// Cloud/mobile UI checks; AI, ASR and vision use controlled test responses.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process');
const root=path.resolve(__dirname,'..'),out=path.join(root,'build-cache/cloud-ui-qa');fs.mkdirSync(out,{recursive:true});
const base=process.env.FOREST_CLOUD_QA_URL||'http://127.0.0.1:18218',remote=!!process.env.FOREST_CLOUD_QA_URL,results=[];
let server,browser;const log=fs.openSync(path.join(out,'server.log'),'w');
if(!remote){const boot="import sys;from backend import session;session.DATA_DIR=sys.argv[1];sys.argv=[sys.argv[0]]+sys.argv[2:];from backend import server;server.main()";server=spawn('D:/python/python.exe',['-u','-c',boot,path.join(out,'sessions'),'--host','127.0.0.1','--port','18218'],{cwd:root,env:{...process.env,FOREST_LOCAL_DESKTOP:'0'},stdio:['ignore',log,log],windowsHide:true});}
async function test(name,fn){try{await fn();console.log('PASS',name);results.push({name,pass:true});}catch(error){console.log('FAIL',name,error.message);results.push({name,pass:false,error:error.message});}}
async function context(width=390,height=844,options={}){
 const c=await browser.newContext({viewport:{width,height},isMobile:width<760,hasTouch:width<760,deviceScaleFactor:1}),p=await c.newPage();p.setDefaultTimeout(12000);
 await p.addInitScript(()=>{HTMLMediaElement.prototype.play=function(){return Promise.resolve();};});
 if(options.noWebGL)await p.addInitScript(()=>{const native=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(kind,...rest){if(/webgl/.test(kind))return null;return native.call(this,kind,...rest);};});
 await p.route('**/api/client-config',async route=>{if(options.failConfig){await route.fulfill({status:503,json:{ok:false}});return;}const r=await route.fetch({timeout:30000}),d=await r.json();d.voice.auto_play=false;d.voice.auto_send=true;await route.fulfill({json:d});});
 await p.route('**/api/chat',route=>route.fulfill({status:200,contentType:'text/event-stream',body:'data: '+JSON.stringify({type:'delta',text:'这是手机端验收用的回答。'})+'\n\n'}));
 await p.route('**/api/session/*/suggestions',route=>route.fulfill({json:{ok:true,questions:[]}}));
 await p.route('**/api/media/search',async route=>{if(remote){await route.fulfill({json:{ok:true,items:[]}});return;}await route.continue();});
 await p.goto(base+'/?cloudQA=1',{waitUntil:'domcontentloaded',timeout:60000});return {c,p};
}
(async()=>{
 if(!remote)for(let i=0;i<40;i++){try{if((await fetch(base+'/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,250));}
 browser=await chromium.launch({channel:'msedge',headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
 for(const [w,h] of [[320,568],[360,640],[390,844],[768,1024],[1440,900]])await test('mobile/tablet layout '+w+'x'+h,async()=>{
  const {c,p}=await context(w,h);try{
   await p.waitForFunction(()=>window.forestConversation&&window.forestConversation.snapshot().sessionId);await p.waitForSelector('#companion');
   const dimensions=await p.evaluate(()=>({width:innerWidth,scroll:document.body.scrollWidth,button:document.querySelector(innerWidth<760?'#companionTalk':'#btnModeToggle').getBoundingClientRect().bottom,height:innerHeight}));
   assert.ok(dimensions.scroll<=dimensions.width,JSON.stringify(dimensions));assert.ok(dimensions.button<=dimensions.height+1,JSON.stringify(dimensions));
   await p.locator('#viewChat').click();await p.locator('#textInput').fill('你好');await p.locator('#btnSend').click();await p.waitForFunction(()=>document.querySelector('#chat').textContent.includes('手机端验收'));
   assert.equal(await p.locator('#chat').isVisible(),true);assert.equal(await p.locator('#inputbar').isVisible(),true);
   await p.screenshot({path:path.join(out,'chat-'+w+'.png')});
  }finally{await c.close();}
 });
 await test('WebGL failure keeps the character visible and chat usable',async()=>{
  const {c,p}=await context(390,844,{noWebGL:true});try{await p.waitForFunction(()=>window.forestConversation&&window.forestConversation.snapshot().sessionId);
   await p.waitForFunction(()=>{const img=document.querySelector('#characterPoster');return img&&img.complete&&img.naturalWidth>0;},{},{timeout:2500});
   assert.equal(await p.locator('#characterPoster').isVisible(),true);await p.locator('#viewChat').click();await p.locator('#textInput').fill('你好');await p.locator('#btnSend').click();await p.waitForFunction(()=>document.querySelector('#chat').textContent.includes('手机端验收'));
   await p.locator('#view3d').click();await p.screenshot({path:path.join(out,'webgl-fallback.png')});
  }finally{await c.close();}
 });
 await test('startup failure is visible and reconnect works',async()=>{
  const {c,p}=await context(390,844,{failConfig:true});try{await p.waitForSelector('#startupError:not([hidden])',{timeout:2500});
   await p.unroute('**/api/client-config');await p.locator('#btnStartupRetry').click();await p.waitForFunction(()=>window.forestConversation.snapshot().sessionId);
   assert.equal(await p.locator('#startupError').isVisible(),false);
  }finally{await c.close();}
 });
 fs.writeFileSync(path.join(out,remote?'online-results.json':'results.json'),JSON.stringify(results,null,2));if(results.some(r=>!r.pass))process.exitCode=1;
 console.log('RESULT',results.filter(r=>r.pass).length+'/'+results.length);
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)server.kill();fs.closeSync(log);});
