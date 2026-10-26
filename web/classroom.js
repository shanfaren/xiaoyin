(function(){
  'use strict';
  var $=function(id){return document.getElementById(id);};
  var epoch=0,controller=null,selected=null,lastQuestion='',galleryLoaded=false;
  var answerEpoch=0,answerController=null,answerMedia=null,lastSubjects=[];
  function sessionId(){
    try{return (window.forestConversation.snapshot()||{}).sessionId||'';}catch(e){return '';}
  }
  function showVoice(event){
    var d=event.detail||{},button=$('btnModeToggle');
    $('voiceInline').hidden=!d.active;
    button.querySelector('.hold-live').textContent=d.text||d.title||'正在听…';
    $('voiceInlineHint').textContent=(d.title?d.title+' · ':'')+(d.tip||'松开结束，上移取消');
    if(d.active){$('companionTalk').textContent=d.text||d.title||'正在听…';}
    else if(window.forestConversation){var s=window.forestConversation.snapshot();$('companionTalk').textContent=s.busy?'正在回答…':'按住说话';}
  }
  window.addEventListener('forest:voice-ui',showVoice);
  $('btnInlineCancel').onclick=function(){
    if(window.forestConversation)window.forestConversation.cancel();
    $('voiceInline').hidden=true;
  };
  function openGallery(){
    $('galleryContent').hidden=false;$('btnGalleryToggle').textContent='收起图库';$('btnGalleryToggle').setAttribute('aria-expanded','true');
  }
  $('btnGalleryToggle').onclick=function(){
    if($('galleryContent').hidden){openGallery();if(!galleryLoaded)search('');}
    else{$('galleryContent').hidden=true;this.textContent='打开图库';this.setAttribute('aria-expanded','false');}
  };
  function safeUrl(value,local){
    try{var u=new URL(value,location.origin);return ((local&&u.origin===location.origin&&u.pathname.indexOf('/assets/animals/')===0)||(!local&&u.protocol==='https:'))?u.href:'';}catch(e){return '';}
  }
  function view(item){
    selected=item;var local=item.origin==='local';
    $('animalViewerImage').src=safeUrl(item.url,local);$('animalViewerImage').alt=item.alt||item.title;
    $('animalViewerTitle').textContent=item.title;
    $('animalViewerPrompt').textContent=item.prompt||'仔细看看：它的颜色和形状有什么特点？';
    $('animalViewerAnswer').hidden=true;$('animalViewerAnswer').textContent=item.explanation||'请和老师一起确认动物种类，再比较它与周围环境的颜色和形状。';
    $('btnViewerReveal').hidden=false;$('btnViewerReveal').textContent='看看它怎样隐藏';
    var credit=$('animalViewerCredit');credit.textContent='';
    var kind=document.createElement('strong');kind.textContent=(item.kind||'图片')+'　';credit.appendChild(kind);
    credit.appendChild(document.createTextNode((item.credit||'来源见链接')+' '));
    var source=safeUrl(item.source_url,false);if(source){var a=document.createElement('a');a.href=source;a.target='_blank';a.rel='noopener noreferrer';a.textContent='查看来源';credit.appendChild(a);}
    if(!$('animalViewer').open)$('animalViewer').showModal();
  }
  $('btnViewerClose').onclick=function(){$('animalViewer').close();};
  $('btnViewerReveal').onclick=function(){$('animalViewerAnswer').hidden=false;this.hidden=true;};
  function makeCard(item){
    var local=item.origin==='local',url=safeUrl(item.url,local);if(!url)return null;
    var b=document.createElement('button');b.type='button';b.className='animal-card';
    if(item.origin==='generated')b.classList.add('is-generated');
    var badge=document.createElement('i');badge.className='animal-origin'+(item.origin==='web'?' web':(item.origin==='generated'?' generated':''));
    badge.textContent=item.origin==='local'?'本地图库':(item.origin==='generated'?'AI生成':'联网');
    var img=document.createElement('img');img.src=url;img.alt=item.alt||item.title;img.loading='lazy';img.referrerPolicy='no-referrer';
    img.onerror=function(){b.disabled=true;b.querySelector('span').textContent=item.title+'（图片暂不可用）';};
    var title=document.createElement('span');title.textContent=item.title;
    b.append(badge,img,title);b.onclick=function(){view(item);};
    return b;
  }
  function groupHeader(label,count){
    var d=document.createElement('div');d.className='gallery-group';d.textContent=label+'（'+count+' 张）';return d;
  }
  function render(items){
    var root=$('galleryResults');root.replaceChildren();
    var local=items.filter(function(i){return i.origin==='local';});
    var web=items.filter(function(i){return i.origin==='web';});
    var generated=items.filter(function(i){return i.origin==='generated';});
    if(local.length){root.appendChild(groupHeader('本地图库 · 已核对物种与许可',local.length));}
    local.forEach(function(item){var c=makeCard(item);if(c)root.appendChild(c);});
    if(web.length){root.appendChild(groupHeader('联网搜索 · 来自第三方网页',web.length));}
    web.forEach(function(item){var c=makeCard(item);if(c)root.appendChild(c);});
    if(generated.length){root.appendChild(groupHeader('AI 生成示意图 · 非真实照片',generated.length));}
    generated.forEach(function(item){var c=makeCard(item);if(c)root.appendChild(c);});
  }
  function statusMessage(data){
    return (data.items||[]).length?'':'暂时没有对应图片，换个动物名称试试。';
  }
  function search(query){
    var version=++epoch;if(controller)controller.abort();controller=new AbortController();
    $('galleryStatus').textContent='正在找图片…';
    fetch('/api/media/search',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({query:query||'',session_id:sessionId(),prefer:document.body.classList.contains('desktop-character-app')?'local':'cloud'}),signal:controller.signal})
      .then(function(r){if(!r.ok)throw new Error('search');return r.json();})
      .then(function(data){
        if(version!==epoch)return;
        if(!data.ok)throw new Error(data.message||'search');
        galleryLoaded=true;render(data.items||[]);
        $('galleryStatus').textContent=statusMessage(data);
      })
      .catch(function(e){
        if(version!==epoch||e.name==='AbortError')return;
        $('galleryResults').replaceChildren();
        $('galleryStatus').textContent='图片暂时没有找到（接口未响应），请稍后重试。';
      });
  }
  $('gallerySearch').onsubmit=function(e){e.preventDefault();search($('galleryQuery').value.trim());};
  function attachAnswerImages(context){
    if(!context||context.version!==answerEpoch||!context.items||!context.bubble||!context.bubble.isConnected)return;
    if(context.bubble.querySelector('.answer-images'))return;
    var cards=[],groups={};
    context.items.forEach(function(item){var group=(item.species_zh||item.title||'').split('（')[0];if(cards.length<2&&!groups[group]){cards.push(item);groups[group]=true;}});
    context.items.forEach(function(item){if(cards.length<2&&cards.indexOf(item)<0)cards.push(item);});
    if(!cards.length)return;
    var strip=document.createElement('div');strip.className='answer-images';strip.setAttribute('aria-label','回答中的动物图片，点击放大');
    cards.forEach(function(item){var card=makeCard(item);if(card)strip.appendChild(card);});
    context.bubble.appendChild(strip);
    context.bubble.classList.add('has-answer-images');
    window.dispatchEvent(new CustomEvent('forest:media-ready'));
  }
  function prepareAnswerMedia(text,inputKind){
    lastQuestion=text||'';
    var version=++answerEpoch;if(answerController)answerController.abort();
    answerMedia={version:version,items:null,bubble:null};var context=answerMedia;
    if(inputKind==='image'){lastSubjects=[];context.items=[];return;}
    var query=lastQuestion;
    if(/^(它|它们|这种|这个|那种|那只|这只)/.test(query)&&lastSubjects.length)query=lastSubjects.join('和')+' '+query;
    var desktop=document.body.classList.contains('desktop-character-app');
    if(!desktop&&!/动物|保护色|拟态|隐藏|隐身|伪装|虫|蝶|蛙|鹰|兔|龙|螳螂|章鱼|乌贼|墨鱼|比目鱼|壁虎|北极|虎|斑马|豹|蝗虫|鸟|鹦鹉|孔雀|猴|图片|照片/.test(query))return;
    answerController=new AbortController();
    // Keep the gallery closed. Relevant photos belong to this answer's bubble.
    fetch('/api/media/search',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({query:query.slice(0,100),session_id:sessionId(),prefer:desktop?'local':'cloud'}),signal:answerController.signal})
      .then(function(r){if(!r.ok)throw Error('search');return r.json();})
      .then(function(data){if(version!==answerEpoch)return;context.items=data.ok?(data.items||[]):[];lastSubjects=[];context.items.forEach(function(item){var name=(item.species_zh||'').split('（')[0];if(name&&lastSubjects.indexOf(name)<0&&lastSubjects.length<2)lastSubjects.push(name);});attachAnswerImages(context);})
      .catch(function(){/* The text answer remains usable when no matching photo is available. */});
  }
  window.addEventListener('forest:question',function(e){prepareAnswerMedia(e.detail.text,e.detail.inputKind);});
  window.addEventListener('forest:answer',function(){
    if(!answerMedia){var questions=document.querySelectorAll('#chat .msg.u .bubble-text');if(questions.length){var question=questions[questions.length-1],text=question.textContent;prepareAnswerMedia(text,question.parentElement.querySelector('.imgtag')?'image':'text');}}
    if(!answerMedia)return;
    var bubbles=document.querySelectorAll('#chat .msg.a .bubble');answerMedia.bubble=bubbles[bubbles.length-1];attachAnswerImages(answerMedia);
  });
  window.addEventListener('forest:cancel',function(){++answerEpoch;if(answerController)answerController.abort();answerMedia=null;});
  $('btnNew').addEventListener('click',function(){++epoch;++answerEpoch;if(controller)controller.abort();if(answerController)answerController.abort();answerMedia=null;lastSubjects=[];if($('animalViewer').open)$('animalViewer').close();$('galleryQuery').value='';$('galleryResults').replaceChildren();galleryLoaded=false;$('galleryStatus').textContent='';$('galleryContent').hidden=true;$('btnGalleryToggle').textContent='动物图库';$('btnGalleryToggle').setAttribute('aria-expanded','false');});
})();
