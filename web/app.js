/* 森林小博士 · 学生端逻辑
   交互约束：不出现 API/开发术语；每次反馈简短适龄；区分文字/语音/照片三种输入，
   三者共享同一会话上下文；语音链路 = 录音 → ASR → 模型 → TTS → 播放。 */

(function () {
  'use strict';
  var VOICE_MAX_MS=60000;
  window.ForestVoiceLimits={maxSeconds:VOICE_MAX_MS/1000,holdDelayMs:280};

  /* 官方勘探家头像；与桌面悬浮球使用同一资产。 */
  var AVATAR_SVG = '<img src="/assets/avatar/forest-official.png?v=20261015official1" alt="森林小博士" loading="lazy">';

  /* ---------- 状态 ---------- */
  var S = {
    cfg: null,
    sid: '',
    stageId: 'qa',
    mode: 'student',
    voiceMode: false,      // 底部栏当前是语音还是文字
    recording: false, recordIntent:0,
    busy: false,
    mediaRecorder: null,
    chunks: [],
    audioEl: null,
    speechRec: null,
    photo: null,           // {dataUrl, base64, mime, name, size}
    abort: null,
    followupVersion: 0,
    stopped: false,
    followLatest: true, quickQuestions: [], quickOffset: 0,
    audioSeq: 0, playbackAudio: null, playbackUnlock: Promise.resolve(), audioURL:null,
    welcomeEnvelope: null, welcomeEnvelopeLoading: null, micStream: null, recordTimer: null, voiceVersion: 0,
    voiceSheetActive: false, voiceUiTimer: null, asrPending:false,recordClock:null,recordingSince:0,
    turnVersion:0,sessionVersion:0,sessionPromise:null
  };

  var $ = function (id) { return document.getElementById(id); };

  /* ---------- 头像状态（idle/listening/thinking/speaking） ---------- */
  var AVATAR_STATE = 'idle';
  function setAvatarState(state) {
    if (state === AVATAR_STATE) return;
    AVATAR_STATE = state;
    window.dispatchEvent(new CustomEvent('forest:state', {detail:{state:state}}));
    ['brandAvatarImg', 'heroAvatarImg'].forEach(function (id) {
      var img = $(id);
      if (!img) return;
      img.dataset.state = state;
      img.parentElement.dataset.state = state;
    });
  }

  function avatarFallback() {
    // 图片不可用时保留角色名称，避免无限重试。
    ['brandAvatar', 'heroAvatar'].forEach(function (id) {
      var box = $(id);
      if (box) { box.textContent = '森林'; box.setAttribute('aria-label', '森林小博士'); }
    });
  }

  /* ---------- 工具 ---------- */
  function setStatus(text) {
    var el = $('status');
    if (!text) { el.hidden = true; setAvatarState('idle'); return; }
    el.hidden = false;
    $('statusText').textContent = text;
  }

  function openVoiceSheet() {
    if (S.voiceUiTimer) { clearTimeout(S.voiceUiTimer); S.voiceUiTimer = null; }
    S.voiceSheetActive = true;
    document.body.classList.add('voice-input-active');
    document.body.classList.remove('voice-cancel-armed');
    $('recLayer').hidden = false;
    $('recLayer').setAttribute('aria-hidden', 'false');
    $('recLayer').dataset.state = 'recording';
  }

  function setVoiceSheetState(state, title, tip, transcript) {
    if (!S.voiceSheetActive) return;
    $('recLayer').dataset.state = state;
    if (title) $('recTitle').textContent = title;
    if (tip) { S.voiceTipBase=tip; $('recTip').textContent = tip; }
    if(state==='recording')$('recTip').textContent=(S.voiceTipBase||'松开结束，上移取消')+' · '+(S.recordingSince?Math.min(60,Math.floor((Date.now()-S.recordingSince)/1000)):0)+'秒 / 最长60秒';
    if (typeof transcript === 'string') $('recTranscript').textContent = transcript;
    window.dispatchEvent(new CustomEvent('forest:voice-ui',{detail:{active:true,state:state,title:$('recTitle').textContent,tip:$('recTip').textContent,text:$('recTranscript').textContent,maxSeconds:VOICE_MAX_MS/1000,elapsedSeconds:S.recordingSince?Math.min(VOICE_MAX_MS/1000,Math.floor((Date.now()-S.recordingSince)/1000)):0}}));
  }

  function closeVoiceSheet() {
    S.voiceSheetActive = false;
    if (S.voiceUiTimer) { clearTimeout(S.voiceUiTimer); S.voiceUiTimer = null; }
    document.body.classList.remove('voice-input-active', 'voice-cancel-armed');
    $('recLayer').hidden = true;
    $('recLayer').setAttribute('aria-hidden', 'true');
    $('recLayer').dataset.state = '';
    window.dispatchEvent(new CustomEvent('forest:voice-ui',{detail:{active:false}}));
  }

  function audioErrorMessage(err) {
    var name = err && err.name || '';
    var message = err && err.message || '';
    if (name === 'EncodingError' || /decode|audio data/i.test(message)) {
      return '这段录音没有读取成功，请靠近麦克风，按住说完一句话后再松开。';
    }
    if (name === 'NotReadableError') return '麦克风被其他应用占用了，请关闭录音或通话应用后重试。';
    if (name === 'NotAllowedError' || name === 'PermissionDeniedError' || name === 'SecurityError') {
      return '麦克风权限没有开启，请在浏览器设置中允许本站使用麦克风。';
    }
    if (name === 'NotFoundError' || name === 'DevicesNotFoundError') return '没有检测到可用的麦克风。';
    return '录音处理失败，请靠近麦克风再试一次。';
  }

  function showVoiceError(message) {
    if (!S.voiceSheetActive) return;
    setVoiceSheetState('error', '没有听清楚', message, '');
    S.voiceUiTimer = setTimeout(closeVoiceSheet, 1800);
  }

  function deliverVoiceTranscript(text) {
    if (!text) return;
    window.dispatchEvent(new CustomEvent('forest:transcript', {detail:{text:text}}));
    if (!S.voiceSheetActive) {
      if (S.cfg && S.cfg.voice && S.cfg.voice.auto_send) doChat({text:text,input_kind:'voice'});
      else showAsrEdit(text);
      return;
    }
    setVoiceSheetState('result', '我听到的是…', '文字已识别，即将发送', text);
    if (S.cfg && S.cfg.voice && S.cfg.voice.auto_send) {
      doChat({text:text,input_kind:'voice'});
      S.voiceUiTimer = setTimeout(function () {
        if (!S.voiceSheetActive || $('recLayer').dataset.state !== 'result') return;
        closeVoiceSheet();
      }, 850);
    } else {
      S.voiceUiTimer = setTimeout(function () {
        closeVoiceSheet();
        showAsrEdit(text);
      }, 650);
    }
  }

  function stopAudio() {
    S.audioSeq++;
    var wa = $('welcomeAudio');
    if (wa) { try { wa.pause(); } catch (e) {} }
    if (S.audioEl) { try { S.audioEl.pause(); } catch (e) {} S.audioEl = null; }
    if (S.audioURL) { URL.revokeObjectURL(S.audioURL); S.audioURL=null; }
    S.speechEnvelope = null;
    if (window.speechSynthesis) { try { window.speechSynthesis.cancel(); } catch (e) {} }
    setAvatarState('idle');
  }

  function isWeChat() { return /MicroMessenger/i.test(navigator.userAgent); }
  function isSecure() {
    return location.protocol === 'https:' || ['localhost', '127.0.0.1'].indexOf(location.hostname) >= 0;
  }

  /* ---------- 会话 ---------- */
  function createSession() {
    if(S.sessionPromise)return S.sessionPromise;
    var generation=S.sessionVersion;
    var pending=fetch('/api/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'student', stage_id: S.stageId })
    }).then(function (r) { return r.json(); }).then(function (j) {
      if(generation!==S.sessionVersion)throw new DOMException('Session replaced','AbortError');
      if (!j.ok) throw new Error('会话创建失败');
      S.sid = j.session_id;
      try { localStorage.setItem('xiaoyin_sid', S.sid); } catch (e) {}
      return j;
    });
    S.sessionPromise=pending;
    pending.then(function(){if(S.sessionPromise===pending)S.sessionPromise=null;},function(){if(S.sessionPromise===pending)S.sessionPromise=null;});
    return pending;
  }

  function restoreSession(sid) {
    var generation=S.sessionVersion;
    return fetch('/api/session/' + encodeURIComponent(sid) + '?mode=student')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (generation!==S.sessionVersion||!j || !j.ok) return null;
        S.sid = j.session.session_id || j.session.id;
        S.stageId = j.session.stage_id || S.stageId;
        renderStages((S.cfg && S.cfg.stages) || [], S.stageId);
        return j.session;
      });
  }

  function renderHistory(session) {
    var msgs = (session && session.messages) || [];
    if (!msgs.length) return;
    $('welcome').hidden = true;
    $('chat').hidden = false;
    S.followLatest = true;
    msgs.forEach(function (m) {
      if (m.role === 'user') {
        addMsg('u', m.content, m.kind === 'image' ? '照片' : '');
      } else {
        var bubble = addMsg('a', m.content);
        attachTools(bubble, m.content);
      }
    });
    if (msgs[msgs.length - 1].role === 'assistant') { loadFollowups(); window.dispatchEvent(new CustomEvent('forest:answer',{detail:{text:msgs[msgs.length-1].content}})); }
  }

  /* ---------- 渲染 ---------- */
  function appendInlineMarkup(parent, text) {
    String(text).split(/(\*\*[^*]+\*\*)/g).forEach(function (part) {
      if (!part) return;
      if (part.slice(0, 2) === '**' && part.slice(-2) === '**') {
        var strong = document.createElement('strong');
        strong.textContent = part.slice(2, -2);
        parent.appendChild(strong);
      } else {
        parent.appendChild(document.createTextNode(part));
      }
    });
  }

  function renderMessageText(container, text) {
    container.textContent = '';
    if (container.parentElement) container.parentElement.setAttribute('aria-busy', String(!text));
    var lines = String(text || '').split(/\r?\n/);
    var list = null, listType = '', paragraph = [];
    function flushParagraph() {
      if (!paragraph.length) return;
      var p = document.createElement('p');
      appendInlineMarkup(p, paragraph.join('\n'));
      container.appendChild(p);
      paragraph = [];
    }
    function flushList() {
      flushParagraph();
      list = null;
      listType = '';
    }
    lines.forEach(function (raw) {
      var line = raw.replace(/^\s*#{1,6}\s+/, '');
      var bullet = line.match(/^\s*[-*]\s+(.+)$/);
      var numbered = line.match(/^\s*\d+[.)]\s+(.+)$/);
      if (bullet || numbered) {
        flushParagraph();
        var type = bullet ? 'ul' : 'ol';
        if (!list || listType !== type) {
          list = document.createElement(type);
          listType = type;
          container.appendChild(list);
        }
        var li = document.createElement('li');
        appendInlineMarkup(li, (bullet || numbered)[1]);
        list.appendChild(li);
      } else if (!line.trim()) {
        flushList();
      } else {
        if (list) flushList();
        paragraph.push(line);
      }
    });
    flushList();
    if (!text) {
      var typing = document.createElement('span');
      typing.className = 'typing';
      typing.setAttribute('aria-label', '小博士正在思考');
      typing.innerHTML = '<i></i><i></i><i></i>';
      container.appendChild(typing);
    }
  }

  function addMsg(role, text, tag) {
    var wrap = document.createElement('div');
    wrap.className = 'msg ' + role;
    wrap.setAttribute('aria-label', role === 'u' ? '你说' : '森林小博士说');
    var who = document.createElement('div');
    who.className = 'who';
    who.innerHTML = role === 'u' ? '<img src="/assets/avatar/user-cartoon.png?v=20261015avatars1" alt="我" loading="lazy">' : AVATAR_SVG;
    var bubble = document.createElement('div');
    bubble.className = 'bubble';
    var textBox = document.createElement('div');
    textBox.className = 'bubble-text';
    if (tag) {
      var t = document.createElement('span');
      t.className = 'imgtag';
      t.textContent = '📷 ' + tag;
      bubble.appendChild(t);
    }
    renderMessageText(textBox, text);
    bubble.appendChild(textBox);
    bubble._forestText = textBox;
    wrap.appendChild(who);
    wrap.appendChild(bubble);
    $('chat').appendChild(wrap);
    scrollBottom();
    return bubble;
  }

  function scrollBottom(force, preferReply) {
    if (force) S.followLatest = true;
    if (!S.followLatest && !preferReply) {
      syncJumpButton();
      return;
    }
    var m = $('main');
    requestAnimationFrame(function () {
      var replies=document.querySelectorAll('#chat .msg.a'),reply=replies[replies.length-1];
      if(!force&&reply&&document.body.classList.contains('desktop-character-app')){
        var top=reply.getBoundingClientRect().top-m.getBoundingClientRect().top+m.scrollTop-parseFloat(getComputedStyle(m).paddingTop||0);
        m.scrollTop=Math.max(0,Math.min(top,m.scrollHeight-m.clientHeight));
        S.followLatest=true;
      }else m.scrollTop = m.scrollHeight;
      syncJumpButton();
    });
  }
  window.addEventListener('forest:media-ready',function(){scrollBottom(false,true);});

  function atLatest() {
    var m = $('main');
    return m.scrollHeight - m.scrollTop - m.clientHeight < 80;
  }

  function syncJumpButton() {
    var visible = !$('chat').hidden && !atLatest() && !S.followLatest;
    $('btnJumpLatest').hidden = !visible;
  }

  function addNotice(text) {
    if(document.body.classList.contains('desktop-character-app')&&/^欢迎回来/.test(text))return;
    window.dispatchEvent(new CustomEvent('forest:notice', {detail:{text:text}}));
    var d = document.createElement('div');
    d.className = 'notice';
    d.textContent = text;
    $('chat').appendChild(d);
    scrollBottom();
  }

  function addError(title, detail, retry) {
    window.dispatchEvent(new CustomEvent('forest:notice', {detail:{text:title+' '+(detail||'')}}));
    var d = document.createElement('div');
    d.className = 'err';
    var b = document.createElement('b');
    b.textContent = title;
    d.appendChild(b);
    d.appendChild(document.createTextNode(detail || ''));
    if (typeof retry === 'function') {
      var retryButton = document.createElement('button');
      retryButton.type = 'button';
      retryButton.className = 'err-retry';
      retryButton.textContent = '重新回答';
      retryButton.addEventListener('click', retry);
      d.appendChild(retryButton);
    }
    $('chat').appendChild(d);
    scrollBottom();
  }

  function renderStages(stages, currentId) {
    currentId = ({share:'qa',intro:'qa',aichat1:'qa',aichat2:'qa',extension:'qa',level1:'hint',level2:'hint',level3:'hint',level4:'hint',level5:'hint'})[currentId] || currentId;
    var st = null;
    stages.forEach(function (s) { if (s.id === currentId) st = s; });
    if (!st) st = stages[0];
    if (!st) return;
    S.stageId = st.id;
    $('taskTitle').textContent = st.name;
    $('taskGoal').textContent = st.goal;
    $('interactionGoal').textContent = st.goal;
    $('textInput').placeholder = st.placeholder || st.goal;
    document.querySelectorAll('#interactionTabs button').forEach(function (button) {
      button.setAttribute('aria-pressed', String(button.dataset.profile === st.id));
    });
    var extras=(S.cfg&&S.cfg.quick_questions)||[];
    var questions=(st.questions||[]).concat(extras).filter(function(q,i,all){return q&&all.indexOf(q)===i;});
    renderQuick(questions);
  }

  function renderQuick(qs) {
    S.quickQuestions=qs||[];
    S.quickOffset=0;
    renderQuickPage();
  }

  function renderQuickPage() {
    var box = $('quickList');
    box.innerHTML = '';
    var questions=S.quickQuestions||[];
    questions.slice(S.quickOffset,S.quickOffset+3).forEach(function (q) {
      var b = document.createElement('button');
      b.className = 'chip';
      b.type = 'button';
      b.textContent = q;
      b.addEventListener('click', function () { sendText(q); });
      box.appendChild(b);
    });
    var more=$('btnQuickMore');
    if(more)more.hidden=questions.length<=3;
  }

  function nextQuickQuestions() {
    if(!S.quickQuestions.length)return;
    S.quickOffset=(S.quickOffset+3)%S.quickQuestions.length;
    renderQuickPage();
  }

  function renderVoiceCapability() {
    var v = (S.cfg && S.cfg.voice) || {};
    var asrOk = v.asr && v.asr.state === 'configured';
    var hint = $('voiceHint');
    if (asrOk) {
      hint.textContent = '按住说话，松开结束；文字会逐步显示，结束后校正。';
      $('btnVoiceBig').hidden = false;
    } else {
      $('btnVoiceBig').hidden = false;
      var parts = ['语音识别还没有配置好，先用下面的文字框跟我说话吧。'];
      if (!isSecure()) parts.push('另外，手机录音需要 https 安全地址，当前不是，录音可能无法使用。');
      if (isWeChat()) parts.push('如果是在微信里打开，可以点右上角“在浏览器打开”再试。');
      hint.textContent = parts.join('');
    }
    if (S.cfg && S.cfg.demo && S.cfg.demo.enabled) {
      var d = document.createElement('div');
      d.className = 'notice';
      d.textContent = '当前是演示状态：回答来自课程知识库的固定内容，不是真实 AI。等老师配置好以后会自动变成真实回答。';
      $('welcome').appendChild(d);
    }
  }

  /* ---------- 发送文字 ---------- */
  function sendText(text) {
    text = (text || '').trim();
    if (!text || S.busy) return;
    unlockPlayback();
    $('textInput').value = '';
    autoSizeTextInput();
    doChat({ text: text, input_kind: 'text' });
  }

  function autoSizeTextInput() {
    var input=$('textInput');
    if(!input)return;
    input.style.height='auto';
    input.style.height=Math.min(112,Math.max(44,input.scrollHeight))+'px';
    input.style.overflowY=input.scrollHeight>112?'auto':'hidden';
  }

  /* ---------- 发送照片 ---------- */
  function sendPhoto() {
    if (!S.photo || S.busy) return;
    var q = ($('photoQuestion').value || '').trim();
    doVision(S.photo, q);
  }

  function clearFollowups() {
    S.followupVersion++;
    document.querySelectorAll('.followups').forEach(function (box) { box.remove(); });
  }

  function loadFollowups() {
    var version = ++S.followupVersion, selected = S.stageId, sid = S.sid;
    fetch('/api/session/' + encodeURIComponent(sid) + '/suggestions', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({stage_id:selected})
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (!j.ok || !j.questions || !j.questions.length || version !== S.followupVersion || S.busy || sid !== S.sid || selected !== S.stageId) return;
      var box = document.createElement('section'); box.className = 'followups';
      var label = document.createElement('div'); label.className = 'quick-label'; label.textContent = '接下来还可以问'; box.appendChild(label);
      j.questions.slice(0,2).forEach(function (question) {
        var button = document.createElement('button'); button.type='button'; button.className='chip'; button.textContent=question;
        button.addEventListener('click', function () { sendText(question); }); box.appendChild(button);
      });
      $('chat').appendChild(box); scrollBottom();
    }).catch(function () {});
  }

  /* ---------- 对话主流程 ---------- */
  function stopCurrentReply() {
    S.turnVersion++;S.stopped=true;clearFollowups();
    if(S.abort){try{S.abort.abort();}catch(ignore){}S.abort=null;}
    if(S.activeKind==='chat'&&S.sid)fetch('/api/chat/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:S.sid,request_id:S.requestId})}).catch(function(){});
    stopRecording(false);stopAudio();S.activeKind='';S.busy=false;$('btnStop').hidden=true;setStatus('');
    var pending=document.querySelectorAll('#chat .bubble[aria-busy="true"]');
    pending.forEach(function(bubble){renderMessageText(bubble._forestText,'已停止回答。');});
    window.dispatchEvent(new CustomEvent('forest:cancel'));
  }
  function doChat(payload) {
    if(S.busy)return;
    if (!S.sid) { var sessionVersion=S.sessionVersion;createSession().then(function () { if(sessionVersion===S.sessionVersion)doChat(payload); }).catch(function(error){if(error.name!=='AbortError')addError('对话没有建立成功','请稍后重试。');}); return; }
    var turn=++S.turnVersion;S.activeKind='chat';
    S.requestId=window.crypto&&window.crypto.randomUUID?window.crypto.randomUUID():Date.now()+'-'+Math.random().toString(36).slice(2);
    stopAudio();
    window.dispatchEvent(new CustomEvent('forest:question', {detail:{text:payload.text}}));
    clearFollowups();
    S.stopped = false;
    $('welcome').hidden = true;
    $('chat').hidden = false;
    S.followLatest = true;
    addMsg('u', payload.text, payload.kind === 'image' ? '照片' : '');
    var bubble = addMsg('a', '');
    var acc = '';
    var demoTagged = false;
    S.busy = true;
    $('btnSend').hidden = true;
    $('btnStop').hidden = false;
    setStatus('思考中…');
    setAvatarState('thinking');

    S.abort = new AbortController();
    var body = { session_id: S.sid, request_id:S.requestId, text: payload.text, mode: S.mode, stage_id: S.stageId,
                 input_kind: payload.input_kind || 'text' };

    fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: S.abort.signal
    }).then(function (resp) {
      if(turn!==S.turnVersion)return;
      if (!resp.ok || !resp.body) throw new Error('服务返回异常（' + resp.status + '）');
      var reader = resp.body.getReader();
      var dec = new TextDecoder('utf-8');
      var buf = '';
      function pump() {
        return reader.read().then(function (res) {
          if(turn!==S.turnVersion){reader.cancel().catch(function(){});return;}
          if (res.done) return;
          buf += dec.decode(res.value, { stream: true });
          var idx;
          while ((idx = buf.indexOf('\n\n')) >= 0) {
            var chunk = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            chunk.split('\n').forEach(function (line) {
              if (line.indexOf('data: ') !== 0) return;
              var ev;
              try { ev = JSON.parse(line.slice(6)); } catch (e) { return; }
              handleEvent(ev, bubble, function (t) {
                acc += t;
                window.dispatchEvent(new CustomEvent('forest:partial',{detail:{text:acc}}));
                return acc;
              }, function () { doChat(payload); });
            });
          }
          return pump();
        });
      }
      return pump();
    }).catch(function (err) {
      if(turn!==S.turnVersion)return;
      if (err && err.name === 'AbortError') return;
      addError('哎呀，好像连不上了。', '请检查网络后再试一次。（' + (err && err.message ? err.message : '') + '）', function () { doChat(payload); });
    }).then(function () {
      if(turn!==S.turnVersion)return;
      S.busy = false;
      S.activeKind='';
      S.abort = null;
      $('btnSend').hidden = false;
      $('btnStop').hidden = true;
      setStatus('');
      if (!acc.trim()) {
        bubble.parentNode && bubble.parentNode.parentNode && bubble.parentNode.parentNode.removeChild(bubble.parentNode);
      } else {
        attachTools(bubble, acc);
        window.dispatchEvent(new CustomEvent('forest:answer', {detail:{text:acc}}));
        if (!S.stopped) loadFollowups();
        if (!S.stopped && S.cfg && S.cfg.voice && S.cfg.voice.auto_play) speak(acc);
      }
      scrollBottom();
    });
  }

  function handleEvent(ev, bubble, onDelta, retry) {
    if (ev.type === 'meta') {
      if (ev.context && ev.context.warning) addNotice(ev.context.warning);
      setStatus('思考中…');
      setAvatarState('thinking');
    } else if (ev.type === 'model') {
      if (ev.is_real_ai === false) {
        var tag = document.createElement('span');
        tag.className = 'demo-tag';
        tag.textContent = '演示内容（非真实 AI）';
        bubble.appendChild(tag);
        bubble.appendChild(document.createElement('br'));
      }
    } else if (ev.type === 'delta') {
      var nextText = onDelta(ev.text);
      renderMessageText(bubble._forestText, nextText);
      scrollBottom();
    } else if (ev.type === 'notice') {
      addNotice(ev.message);
    } else if (ev.type === 'error') {
      var titles = {
        not_configured: '还没有配置好 AI 大脑',
        upstream_error: 'AI 服务暂时不可用',
        rate_limited: '问得太快啦',
        rate_limited_global: '现在人有点多',
        session_not_found: '会话已过期',
        empty_input: '还没有输入内容'
      };
      addError(titles[ev.code] || '出了点小问题', ev.message || '', ev.code === 'upstream_error' ? retry : null);
      setStatus('');
    }
  }

  function attachTools(bubble, text) {
    var tools = document.createElement('div');
    tools.className = 'msg-tools';
    var v = (S.cfg && S.cfg.voice) || {};
    var ttsOk = v.tts && v.tts.state === 'configured';
    var b1 = document.createElement('button');
    b1.className = 'mini-btn';
    b1.type = 'button';
    b1.textContent = '🔊 听一听';
    b1.addEventListener('click', function () { speak(text, b1, ttsOk); });
    tools.appendChild(b1);
    bubble.appendChild(tools);
  }

  /* ---------- 语音合成播放 ---------- */
  // Decode a copy for a time-indexed amplitude envelope. Never reroute audible audio,
  // which would risk silence under mobile autoplay / suspended AudioContext rules.
  function prepareSpeechEnvelope(blob,seq) {
    S.speechEnvelope=null;
    if (!window.ForestSpeechEnvelope) return;
    var Context=window.OfflineAudioContext||window.webkitOfflineAudioContext;
    if(!Context||!blob.arrayBuffer)return;
    var context;
    try{context=new Context(1,1,16000);}catch(e){return;}
    blob.arrayBuffer().then(function(bytes){return context.decodeAudioData(bytes);}).then(function(audio){
      if(seq!==S.audioSeq)return;
      S.speechEnvelope=window.ForestSpeechEnvelope.build(audio,seq);
    }).catch(function(){/* Speech remains playable if envelope decoding is unavailable. */});
  }
  window.forestSpeechLevel=function(){
    if(!window.ForestSpeechEnvelope)return 0;
    var welcome=$('welcomeAudio');
    if(welcome&&!welcome.paused&&!welcome.ended&&S.welcomeEnvelope){
      return window.ForestSpeechEnvelope.level(welcome,S.welcomeEnvelope,1);
    }
    return window.ForestSpeechEnvelope.level(S.audioEl,S.speechEnvelope,S.audioSeq);
  };
  function speak(text, btn, ttsOk) {
    stopAudio();
    var seq = S.audioSeq;
    if (typeof ttsOk === 'undefined') ttsOk = !!(S.cfg && S.cfg.voice && S.cfg.voice.tts && S.cfg.voice.tts.state === 'configured');
    if (ttsOk) {
      setStatus('准备朗读…');
      setAvatarState('thinking');
      fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text })
      }).then(function (r) {
        if (!r.ok) throw new Error('tts');
        return r.blob();
      }).then(function (blob) {
        if (seq !== S.audioSeq) return;
        prepareSpeechEnvelope(blob,seq);
        // Do not replace src while the same element is still playing the silent
        // user-gesture unlock clip. Wait for that play() promise to settle first.
        return Promise.resolve(S.playbackUnlock).then(function () {
          if (seq !== S.audioSeq) return;
          var url = URL.createObjectURL(blob);
          S.audioURL=url;
          var a = S.playbackAudio || new Audio();
          S.playbackAudio = a;
          a.src = url; a.muted = false;
          S.audioEl = a;
          a.onplaying = function () {
            if(seq===S.audioSeq&&S.audioEl===a){setStatus('播放中…');setAvatarState('speaking');}
          };
          a.onpause = function () {
            if(seq===S.audioSeq&&S.audioEl===a&&!a.ended){setStatus('');setAvatarState('idle');}
          };
          a.onended = function () {
            if(seq!==S.audioSeq||S.audioEl!==a)return;
            S.audioEl=null;S.speechEnvelope=null;
            URL.revokeObjectURL(url);if(S.audioURL===url)S.audioURL=null;
            setStatus('');setAvatarState('idle');
          };
          a.onerror = function () {
            if(seq!==S.audioSeq||S.audioEl!==a)return;
            S.audioEl=null;S.speechEnvelope=null;
            URL.revokeObjectURL(url);if(S.audioURL===url)S.audioURL=null;
            setStatus('');setAvatarState('idle');
          };
          return a.play();
        });
      }).catch(function () {
        if (seq !== S.audioSeq) return;
        S.audioEl=null;S.speechEnvelope=null;
        if(S.audioURL){URL.revokeObjectURL(S.audioURL);S.audioURL=null;}
        setStatus('');
        setAvatarState('idle');
        addNotice('森林小博士的统一声音暂时无法播放，请点击“听一听”重试，并检查设备音量。');
      });
      return;
    }
    addNotice('森林小博士的统一声音暂不可用，请稍后重试。');
  }

  /* ---------- 照片分析 ---------- */
  function doVision(photo, question) {
    if(S.busy)return;
    if (!S.sid) { var sessionVersion=S.sessionVersion;createSession().then(function () { if(sessionVersion===S.sessionVersion)doVision(photo, question); }).catch(function(error){if(error.name!=='AbortError')addError('对话没有建立成功','请稍后重试。');}); return; }
    var turn=++S.turnVersion;S.activeKind='vision';S.stopped=false;S.followLatest=true;
    stopAudio();
    clearFollowups();
    window.dispatchEvent(new CustomEvent('forest:question',{detail:{text:question||'',inputKind:'image'}}));
    $('welcome').hidden = true;
    $('chat').hidden = false;
    var uploadBubble=addMsg('u', '（我拍了一张照片）' + (question ? ' ' + question : ''), '照片');
    var upload=document.createElement('img');upload.className='uploaded-photo';upload.alt='本轮上传的照片';upload.src=photo.dataUrl||'data:'+photo.mime+';base64,'+photo.base64;uploadBubble.appendChild(upload);
    var bubble = addMsg('a', '');
    var voiceAnswer = '';
    S.busy = true;
    $('btnSend').hidden = true;
    $('btnStop').hidden = false;
    setStatus('正在看照片…');
    setAvatarState('thinking');

    S.abort=new AbortController();
    fetch('/api/vision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },signal:S.abort.signal,
      body: JSON.stringify({
        image_base64: photo.base64, mime: photo.mime,
        question: question || '', session_id: S.sid, stage_id: S.stageId
      })
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; }); })
      .then(function (res) {
        if(turn!==S.turnVersion)return;
        var j = res.body || {};
        if (j.ok && j.text) {
          voiceAnswer=j.text;
          renderMessageText(bubble._forestText, j.text);
          attachTools(bubble, j.text);
          window.dispatchEvent(new CustomEvent('forest:answer',{detail:{text:j.text,inputKind:'image'}}));
        } else if (j.error === 'not_configured') {
          addError('还看不懂照片', j.message || '');
          addNotice('现在可以先告诉我：照片里有什么？它躲在哪里？');
        } else if (j.error === 'too_large') {
          addError('照片太大啦', j.message || '');
        } else {
          addError('照片分析没有成功', (j.message || '') + ' 可以点“重试”再试一次。');
          addRetry(bubble.parentNode, photo, question);
        }
      }).catch(function (error) {
        if(turn!==S.turnVersion||error.name==='AbortError')return;
        addError('网络不太好', '照片没有发出去，请再试一次。');
        addRetry(bubble.parentNode, photo, question);
      }).then(function () {
        if(turn!==S.turnVersion)return;
        S.activeKind='';S.abort=null;
        S.busy = false;
        $('btnSend').hidden = false;
        $('btnStop').hidden = true;
        setStatus('');
        clearPhoto();
        if (bubble.textContent.trim()) loadFollowups();
        if (voiceAnswer && S.cfg && S.cfg.voice && S.cfg.voice.auto_play) speak(voiceAnswer);
        scrollBottom();
      });
  }

  function addRetry(msgNode, photo, question) {
    if (!msgNode) return;
    var d = document.createElement('div');
    d.className = 'msg-tools';
    var b = document.createElement('button');
    b.className = 'mini-btn';
    b.type = 'button';
    b.textContent = '重试';
    b.addEventListener('click', function () { doVision(photo, question); });
    d.appendChild(b);
    msgNode.appendChild(d);
  }

  /* ---------- 照片选择与压缩 ---------- */
  function pickPhoto() { $('fileInput').click(); }

  function onFile(ev) {
    var f = ev.target.files && ev.target.files[0];
    if (!f) return;
    if (!/^image\//.test(f.type)) { addNotice('请选择图片文件（jpg / png 等）。'); return; }
    var maxMB = (S.cfg && S.cfg.limits && S.cfg.limits.max_image_mb) || 5;
    if (f.size > maxMB * 1024 * 1024 * 4) {
      addNotice('这张照片太大了，换一张小一点的试试吧。');
      return;
    }
    var reader = new FileReader();
    reader.onload = function () {
      var img = new Image();
      img.onload = function () {
        compress(img, maxMB, function (dataUrl, mime, bytes) {
          S.photo = {
            dataUrl: dataUrl, mime: mime, name: f.name,
            base64: dataUrl.split(',')[1], size: bytes
          };
          $('photoImg').src = dataUrl;
          $('photoName').textContent = f.name;
          $('photoSize').textContent = Math.round(bytes / 1024) + ' KB（已压缩）';
          $('photoPreview').hidden = false;
        });
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(f);
    ev.target.value = '';
  }

  function compress(img, maxMB, cb) {
    var MAX = 1280;
    var w = img.width, h = img.height;
    if (Math.max(w, h) > MAX) {
      var k = MAX / Math.max(w, h);
      w = Math.round(w * k); h = Math.round(h * k);
    }
    var cv = document.createElement('canvas');
    cv.width = w; cv.height = h;
    cv.getContext('2d').drawImage(img, 0, 0, w, h);
    var q = 0.82;
    var out = cv.toDataURL('image/jpeg', q);
    var bytes = Math.round((out.length - out.indexOf(',') - 1) * 0.75);
    while (bytes > maxMB * 1024 * 1024 && q > 0.35) {
      q -= 0.12;
      out = cv.toDataURL('image/jpeg', q);
      bytes = Math.round((out.length - out.indexOf(',') - 1) * 0.75);
    }
    cb(out, 'image/jpeg', bytes);
  }

  function clearPhoto() {
    S.photo = null;
    $('photoPreview').hidden = true;
    $('photoQuestion').value = '';
  }

  /* ---------- 录音与识别 ---------- */
  function wavBlob(samples, rate) {
    var bytes = new ArrayBuffer(44 + samples.length * 2), d = new DataView(bytes);
    function str(offset, value) { for (var i=0;i<value.length;i++) d.setUint8(offset+i,value.charCodeAt(i)); }
    str(0,'RIFF'); d.setUint32(4,36+samples.length*2,true); str(8,'WAVE'); str(12,'fmt ');
    d.setUint32(16,16,true); d.setUint16(20,1,true); d.setUint16(22,1,true);
    d.setUint32(24,rate,true); d.setUint32(28,rate*2,true); d.setUint16(32,2,true); d.setUint16(34,16,true);
    str(36,'data'); d.setUint32(40,samples.length*2,true);
    for(var i=0;i<samples.length;i++) { var value=Math.max(-1,Math.min(1,samples[i])); d.setInt16(44+i*2,value<0?value*32768:value*32767,true); }
    return new Blob([bytes],{type:'audio/wav'});
  }

  function unlockPlayback() {
    if (S.playbackAudio) return S.playbackUnlock;
    var a = new Audio(), url = URL.createObjectURL(wavBlob(new Float32Array(1600),16000));
    S.playbackAudio=a; a.src=url; a.muted=true;
    S.playbackUnlock = new Promise(function (resolve) {
      var finished = false;
      function finish() {
        if (finished) return;
        finished = true;
        try { a.pause(); a.currentTime=0; } catch (e) {}
        a.muted=false;
        URL.revokeObjectURL(url);
        resolve();
      }
      a.play().then(finish, finish);
      // Some embedded browsers leave a muted unlock play() pending without an
      // output device. The element is still gesture-associated; release TTS
      // after a short bounded delay instead of leaving the avatar in thinking.
      setTimeout(finish, 200);
    });
    return S.playbackUnlock;
  }

  function normalizeAudio(blob) {
    var mime=(blob.type||'').split(';')[0].toLowerCase(), name=(blob.name||'').toLowerCase();
    var format = mime==='audio/mpeg'||/\.mp3$/.test(name)?'mp3':mime==='audio/mp4'||/\.m4a$/.test(name)?'m4a':mime==='audio/aac'?'aac':mime==='audio/wav'||/\.wav$/.test(name)?'wav':null;
    if (blob.size>8*1024*1024) return Promise.reject(new Error('录音太大，请录一段短一点的语音。'));
    if (format) return Promise.resolve({blob:blob,format:format});
    var Context=window.AudioContext||window.webkitAudioContext;
    if (!Context) return Promise.reject(new Error('无法读取这个录音格式，请选择MP3、M4A或WAV录音。'));
    var context=new Context();
    return blob.arrayBuffer().then(function (bytes) { return context.decodeAudioData(bytes); }).then(function (audio) {
      context.close();
      if(audio.duration>65) throw new Error('请把录音控制在一分钟以内。');
      var offline=new OfflineAudioContext(1,Math.ceil(audio.duration*16000),16000), source=offline.createBufferSource();
      source.buffer=audio; source.connect(offline.destination); source.start();
      return offline.startRendering();
    }).then(function (audio) { return {blob:wavBlob(audio.getChannelData(0),16000),format:'wav'}; });
  }

  function startRecording() {
    if (S.busy || S.recording || S.micPending) return false;
    stopAudio(); try{unlockPlayback();}catch(ignore){}
    if (!isSecure()) {
      // 局域网HTTP不能直接访问网页麦克风，改由系统录音/选择录音提供音频。
      $('audioFileInput').value=''; $('audioFileInput').click();
      $('voiceHint').textContent='录好后返回这里，选择录音就能发送。';
      return;
    }
    var requestMic;
    if(navigator.mediaDevices&&navigator.mediaDevices.getUserMedia){
      requestMic=function(){return navigator.mediaDevices.getUserMedia({audio:true});};
    }else{
      var legacy=navigator.getUserMedia||navigator.webkitGetUserMedia||navigator.mozGetUserMedia;
      if(legacy)requestMic=function(){return new Promise(function(resolve,reject){legacy.call(navigator,{audio:true},resolve,reject);});};
    }
    if(!requestMic){
      addNotice('当前内置浏览器没有开放麦克风录音。请从右上角菜单选择“在浏览器打开”；也可以选择系统录音文件发送。');
      $('audioFileInput').value='';$('audioFileInput').click();return false;
    }
    if (!isSecure()) {
      addNotice('录音需要 https 安全地址。当前不是 https，可能无法录音，请先用文字输入，或让老师用 https 地址打开。');
      return;
    }
    S.micPending = true;
    S.lastVoicePreview = ''; 
    setStatus('正在开启麦克风，请允许录音权限…');
    openVoiceSheet();
    setVoiceSheetState('requesting','正在开启麦克风…','请允许麦克风权限', '正在开启麦克风，请允许录音权限…');
    var intent=++S.recordIntent;
    requestMic().then(function (stream) {
      if(intent!==S.recordIntent){
        stream.getTracks().forEach(function(t){t.stop();});
        if(S.recordIntent!==intent+1)return;
        S.micPending=false;
        closeVoiceSheet();
        addNotice('麦克风已准备好，请重新按住“按住说话”，说完松开。');return;
      }
      S.micPending = false;
      S.micStream = stream;
      S.recordingSince=Date.now();
      var chunks = [];
      setVoiceSheetState('recording','正在听你说…','松手发送，上移取消','正在听，请开始说话…');
      S.liveRecorder=window.ForestLiveTranscription&&window.ForestLiveTranscription.create(stream,function(text){
        if(S.recording){S.lastVoicePreview=text;setVoiceSheetState('recording',null,null,text);window.dispatchEvent(new CustomEvent('forest:transcript',{detail:{text:text}}));}
      });
      var mr=null;
      if(window.MediaRecorder){try{mr=new MediaRecorder(stream);}catch(ignore){}}
      if(!mr&&!S.liveRecorder)throw new Error('recording_unsupported');
      S.pcmOnly=!mr;
      S.mediaRecorder = mr;
      if(mr){
      mr.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
      mr.onstop = function () {
        if(S.liveRecorder){S.liveRecorder.stop();S.liveRecorder=null;}
        stream.getTracks().forEach(function (t) { t.stop(); });
        if(S.recordTimer) clearTimeout(S.recordTimer);
        if(S.recordClock){clearInterval(S.recordClock);S.recordClock=null;}
        S.recording=false;
        S.micPending=false; S.micStream=null;
        // The full PCM recording bypasses WebView codecs that may reject its own WebM.
        var blob = mr._forestPcm&&mr._forestPcm.size>44?mr._forestPcm:new Blob(chunks, { type: mr.mimeType || 'audio/webm' });
        transcribe(blob);
      };
      mr.start(250);
      }
      S.recording = true;
      S.recordingSince=Date.now();
      S.recordClock=setInterval(function(){if(S.recording)setVoiceSheetState('recording',null,null);},1000);
      S.recordTimer=setTimeout(function () { if(S.recording) stopRecording(true); },VOICE_MAX_MS);
      setStatus('正在听…');
      setAvatarState('listening');
    }).catch(function (err) {
      if(intent!==S.recordIntent)return;
      if(S.liveRecorder){S.liveRecorder.stop();S.liveRecorder=null;}
      if(S.micStream){S.micStream.getTracks().forEach(function(t){t.stop();});S.micStream=null;}
      S.micPending = false;
      closeVoiceSheet();
      setStatus('');
      if(err.name==='NotReadableError')addNotice('麦克风正被其他应用占用，请结束其他录音后再按住说话。');
      else if(err.message==='recording_unsupported')addNotice('当前浏览器无法录音，请从右上角菜单选择“在浏览器打开”后使用语音。');
      else if(err.name==='NotAllowedError'||err.name==='PermissionDeniedError'||err.name==='SecurityError')addNotice('录音被系统或浏览器拦截。请在设备设置中允许微信或浏览器使用麦克风，并允许本站录音；若没有权限提示，请从右上角菜单选择“在浏览器打开”。允许后刷新，再按住说话。');
      else if(err.name==='NotFoundError'||err.name==='DevicesNotFoundError')addNotice('没有检测到可用的麦克风，请检查设备是否连接或启用了麦克风，再按住说话。');
      else if(err.name==='AbortError')addNotice('麦克风启动被中断，请关闭其他录音或通话应用后重试。');
      else addNotice('录音启动失败（'+String(err.name||'未知错误')+'）。请刷新重试；仍失败时，可从右上角菜单选择“在浏览器打开”后使用语音。');
    });
  }

  function stopRecording(send) {
    if(send!==false&&!S.recording&&!S.micPending&&!S.mediaRecorder&&!S.pcmOnly)return;
    S.recordIntent++;
    var liveBlob=null;
    if(S.liveRecorder){liveBlob=S.liveRecorder.stop();S.liveRecorder=null;}
    if(S.recordTimer) clearTimeout(S.recordTimer);
    if(S.recordClock){clearInterval(S.recordClock);S.recordClock=null;}
    S.recording = false;
    setStatus('');
    if (send === false) {
      // 取消：作废一切在途最终识别结果，迟到的 ASR 响应绝不能再被发送或编辑。
      S.voiceVersion++;
      if(S.asrPending){S.asrPending=false;S.busy=false;$('btnStop').hidden=true;}
      S.micPending=false;
      closeVoiceSheet();
    }
    else setVoiceSheetState('recognizing','正在识别…','正在校正，马上显示完整文字',S.lastVoicePreview||'正在识别语音…');
    if(S.pcmOnly){
      S.pcmOnly=false;S.micPending=false;
      if(S.micStream)S.micStream.getTracks().forEach(function(t){t.stop();});S.micStream=null;
      if(send!==false){
        if(liveBlob&&liveBlob.size>11244)transcribe(liveBlob);
        else showVoiceError('录音太短，请按住按钮说完一句话后再松开。');
      }
      return;
    }
    if (S.speechRec) {
      var speech = S.speechRec;
      if (send === false) { speech.onresult=null; speech.onend=null; speech.abort(); S.speechRec=null; S.micPending=false; closeVoiceSheet(); setAvatarState('idle'); }
      else { S.micPending=true; speech.stop(); }
      return;
    }
    if (S.mediaRecorder && S.mediaRecorder.state !== 'inactive') {
      S.micPending=true;
      if (send === false) {
        S.mediaRecorder.onstop = function () { if(S.micStream) S.micStream.getTracks().forEach(function (t) {t.stop();}); S.micStream=null; S.micPending=false; };
        try { S.mediaRecorder.stop(); } catch (e) {}
      } else {
        S.mediaRecorder._forestPcm=liveBlob;
        S.mediaRecorder.stop();
      }
    }
    S.mediaRecorder = null;
  }

  function transcribe(blob) {
    var version=++S.voiceVersion;
    var fromVoiceSheet=S.voiceSheetActive;
    S.asrPending=true;S.busy=true; $('btnStop').hidden=false;
    setStatus('识别中…');
    setAvatarState('listening');
    if(fromVoiceSheet)setVoiceSheetState('recognizing','正在识别…','正在校正，马上显示完整文字',S.lastVoicePreview||'正在识别语音…');
    normalizeAudio(blob).then(function (prepared) {
    if(version!==S.voiceVersion)return;
    var fr = new FileReader();
    fr.onload = function () {
      if(version!==S.voiceVersion)return;
      var b64 = String(fr.result).split(',')[1];
      fetch('/api/asr', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio_base64: b64, format: prepared.format })
      }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
        .then(function (res) {
          if(version!==S.voiceVersion) return;
          S.asrPending=false;S.busy=false; $('btnStop').hidden=true;
          setStatus('');
          var j = res.body || {};
          if (j.ok && j.text) {
            if(fromVoiceSheet)deliverVoiceTranscript(j.text);
            else if (S.cfg && S.cfg.voice && S.cfg.voice.auto_send) doChat({text:j.text,input_kind:'voice'});
            else showAsrEdit(j.text);
          } else if (j.error === 'not_configured') {
            addNotice('语音识别还没有配置好，所以我还听不懂录音。你可以直接打字告诉我。');
            if(fromVoiceSheet)showVoiceError('语音识别还没有配置好，可以先直接打字告诉我。');
            fallbackSpeechRecognition('要不要试试手机自带的语音输入？');
          } else {
            if(fromVoiceSheet)showVoiceError(j.message || '没有听清，请再说一次。');
            addError('没有听清楚', (j.message || '') + ' 再说一次试试？');
          }
        }).catch(function () {
          if(version!==S.voiceVersion) return;
          S.asrPending=false;S.busy=false; $('btnStop').hidden=true;
          setStatus('');
          if(fromVoiceSheet)showVoiceError('网络不太好，录音没有发出去，请再试一次。');
          addError('录音没有发出去', '网络不太好，请再试一次。');
        });
    };
    fr.readAsDataURL(prepared.blob);
    }).catch(function (err) {
      if(version!==S.voiceVersion) return;
      S.asrPending=false;S.busy=false; $('btnStop').hidden=true; setStatus('');
      var message=audioErrorMessage(err);
      if(fromVoiceSheet)showVoiceError(message);
      addNotice(message);
    });
  }

  function showAsrEdit(text) {
    $('asrEdit').hidden = false;
    $('asrText').value = text;
    $('asrText').focus();
  }

  function fallbackSpeechRecognition(reason) {
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      addNotice(reason + ' 这台设备暂时不支持语音输入，请用文字告诉我吧。');
      return;
    }
    if (isWeChat()) {
      addNotice(reason + ' 在微信里可能用不了，可以点右上角“在浏览器打开”再试。');
      return;
    }
    try {
      var rec = new SR();
      rec.lang = 'zh-CN';
      rec.interimResults = false;
      rec.continuous = true;
      rec.maxAlternatives = 1;
      rec.onresult = function (e) {
        // results包含到当前为止的全部分段，不能只读取第0段。
        var parts=[];
        for(var i=0;i<e.results.length;i++) if(e.results[i].isFinal) parts.push(e.results[i][0].transcript);
        rec.forestText=parts.join('');
        $('recTranscript').textContent=rec.forestText;
        window.dispatchEvent(new CustomEvent('forest:transcript',{detail:{text:rec.forestText}}));
      };
      rec.onerror = function () {
        setStatus('');
        showVoiceError('手机自带的语音输入没有成功，请再试一次。');
        addNotice('手机自带的语音输入没能用起来，请用文字告诉我吧。');
      };
      rec.onend = function () {
        if(S.recordTimer) clearTimeout(S.recordTimer);
        S.recording=false; S.micPending=false; S.speechRec=null;
        setStatus(''); setAvatarState('idle');
        if(rec.forestText) {
          if(S.voiceSheetActive) deliverVoiceTranscript(rec.forestText);
          else showAsrEdit(rec.forestText);
        } else {
          showVoiceError('没有听到清楚的话，请按住按钮再说一次。');
        }
      };
      S.speechRec = rec;
      setStatus('正在听…（手机自带识别）');
      rec.start();
      openVoiceSheet();
      setVoiceSheetState('recording','正在听你说…','松手发送，上移取消','正在听，请开始说话…');
      S.recording=true;
      setAvatarState('listening');
      S.recordTimer=setTimeout(function(){if(S.recording) stopRecording(true);},60000);
    } catch (e) {
      closeVoiceSheet();
      addNotice(reason + ' 请用文字告诉我吧。');
    }
  }

  // UI-only bridge: both views use this device's existing session and voice chain.
  window.forestConversation = {
    snapshot: function () { return {busy:S.busy, recording:S.recording, state:AVATAR_STATE, profile:S.stageId, sessionId:S.sid || ''}; },
    talk: function () { if(S.recording) stopRecording(true); else if(S.busy) $('btnStop').click(); else startRecording(); },
    cancel: function () { stopRecording(false); },
    holdStart:function(){return startRecording();},
    holdEnd:function(cancel){stopRecording(!cancel);},
    welcome: function () { playWelcomeVoice(); },
    replay: function (text) { unlockPlayback(); if(text) speak(text); },
    profile: function (id) { var b=document.querySelector('#interactionTabs [data-profile="'+id+'"]'); if(b) b.click(); }
  };
  if (new URLSearchParams(location.search).get('avatarAudit') === '1') {
    window.__forestSetAvatarState = setAvatarState;
    window.__forestAudioState = function () {
      var a=S.audioEl;
      return {
        hasAudio:!!a,
        paused:a?a.paused:null,
        ended:a?a.ended:null,
        currentTime:a?a.currentTime:null,
        readyState:a?a.readyState:null,
        networkState:a?a.networkState:null,
        error:a&&a.error?a.error.code:null,
        envelopeSeq:S.speechEnvelope?S.speechEnvelope.seq:null,
        audioSeq:S.audioSeq,
        avatarState:AVATAR_STATE
      };
    };
  }

  /* ---------- 初始化 ---------- */
  function bind() {
    var holdHintTimer=null;
    function flashHoldHint() {
      // 短按（不足长按阈值）不录音：给出明确但不打断的提示，避免误触后困惑。
      if (S.voiceSheetActive || S.recording || S.micPending) return;
      var hint=$('voiceHint');
      if(hint){hint.textContent='按住按钮说话，说完再松开；轻点不会录音。';}
      var btn=$('btnModeToggle');
      if(btn){
        var live=btn.querySelector('.hold-live');
        if(live){
          live.textContent='按住说话，说完再松开';
          document.body.classList.add('hold-hint-flash');
          if(holdHintTimer)clearTimeout(holdHintTimer);
          holdHintTimer=setTimeout(function(){document.body.classList.remove('hold-hint-flash');if(live)live.textContent='';},1400);
        }
      }
    }
    window.addEventListener('forest:hold-progress', function (event) {
      var detail = event.detail || {};
      document.body.classList.toggle('voice-cancel-armed', detail.phase === 'moving' && !!detail.cancelled);
      if (detail.phase === 'moving' && S.voiceSheetActive) {
        var title = detail.cancelled ? '松开取消' : '正在听你说…';
        var tip = detail.cancelled ? '已进入取消区域' : '松手发送，上移取消';
        setVoiceSheetState('recording', title, tip);
      }
      if (detail.phase === 'aborted') { closeVoiceSheet(); flashHoldHint(); }
    });
    window.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape' || !S.voiceSheetActive) return;
      event.preventDefault();
      if (S.recording || S.micPending) stopRecording(false);
      else closeVoiceSheet();
    });
    ['selectstart','contextmenu','dragstart'].forEach(function(name){
      document.addEventListener(name,function(e){
        var target=e.target;
        if(target&&target.closest&&target.closest('button,[role="button"]'))e.preventDefault();
      },true);
    });
    function syncComposer() {
      var canSend = !!$('textInput').value.trim() || !!S.photo;
      $('btnSend').hidden = S.busy || !canSend;
      $('btnMore').hidden = S.busy || canSend;
      document.querySelectorAll('#interactionTabs button').forEach(function (button) {
        button.disabled = S.busy;
      });
    }
    document.querySelectorAll('#interactionTabs button').forEach(function (button) {
      button.addEventListener('click', function () {
        if (S.busy) return;
        clearFollowups();
        renderStages((S.cfg && S.cfg.stages) || [], button.dataset.profile);
        if (S.sid) {
          fetch('/api/session/' + encodeURIComponent(S.sid) + '/stage', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({stage_id:S.stageId})
          }).catch(function () {});
        }
      });
    });
    $('textInput').addEventListener('input', function () {
      autoSizeTextInput();
      syncComposer();
    });
    $('main').addEventListener('scroll', function () {
      var replies=document.querySelectorAll('#chat .msg.a'),reply=replies[replies.length-1],m=$('main');
      var anchored=reply&&document.body.classList.contains('desktop-character-app')&&Math.abs(reply.getBoundingClientRect().top-m.getBoundingClientRect().top-parseFloat(getComputedStyle(m).paddingTop||0))<3;
      S.followLatest = atLatest()||!!anchored;
      syncJumpButton();
    }, {passive:true});
    $('btnJumpLatest').addEventListener('click', function () { scrollBottom(true); });
    $('btnQuickMore').addEventListener('click', nextQuickQuestions);
    new MutationObserver(syncComposer).observe($('btnStop'), {attributes:true, attributeFilter:['hidden']});
    new MutationObserver(syncComposer).observe($('photoPreview'), {attributes:true, attributeFilter:['hidden']});
    $('btnMore').addEventListener('click', function () {
      var open = $('attachmentMenu').hidden;
      $('attachmentMenu').hidden = !open;
      $('btnMore').setAttribute('aria-expanded', String(open));
    });
    function closeMore() {
      $('attachmentMenu').hidden = true;
      $('btnMore').setAttribute('aria-expanded', 'false');
    }
    $('btnMenuPhoto').addEventListener('click', function () { closeMore(); pickPhoto(); });
    $('btnMenuVoice').addEventListener('click', function () { closeMore(); startRecording(); });
    $('btnMenuNew').addEventListener('click', function () { closeMore(); $('btnNew').click(); });
    if (window.visualViewport) {
      function fitKeyboard() { document.documentElement.style.setProperty('--chat-height', window.visualViewport.height + 'px'); }
      window.visualViewport.addEventListener('resize', fitKeyboard);
      fitKeyboard();
    }
    var bi = $('brandAvatarImg'), hi = $('heroAvatarImg');
    if (bi) { bi.onerror = avatarFallback; }
    if (hi) { hi.onerror = avatarFallback; }

    $('btnSend').addEventListener('click', function () {
      if (S.photo) { sendPhoto(); } else { sendText($('textInput').value); }
    });
    if($('btnStartupRetry'))$('btnStartupRetry').addEventListener('click',init);
    $('textInput').addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
        e.preventDefault();
        if (S.photo) sendPhoto(); else sendText($('textInput').value);
      }
    });
    $('btnStop').addEventListener('click', stopCurrentReply);
    $('btnPhoto').addEventListener('click', pickPhoto);
    $('fileInput').addEventListener('change', onFile);
    $('audioFileInput').addEventListener('change', function () { var audio=this.files&&this.files[0]; if(audio) transcribe(audio); });
    $('btnPhotoDelete').addEventListener('click', clearPhoto);
    $('btnPhotoReplace').addEventListener('click', pickPhoto);
    $('btnPhotoReplace').setAttribute('type', 'button');
    $('btnPhotoDelete').setAttribute('type', 'button');

    window.bindForestHold($('btnModeToggle'),startRecording,function(cancel){stopRecording(!cancel);});

    window.bindForestHold($('btnVoiceBig'),startRecording,function(cancel){stopRecording(!cancel);});
    $('btnRecStop').addEventListener('click', function () { stopRecording(true); });
    $('btnRecCancel').addEventListener('click', function () { stopRecording(false); });

    $('btnAsrSend').addEventListener('click', function () {
      var t = ($('asrText').value || '').trim();
      $('asrEdit').hidden = true;
      if (t) { doChat({ text: t, input_kind: 'voice' }); }
    });
    $('btnAsrCancel').addEventListener('click', function () {
      $('asrEdit').hidden = true;
      $('asrText').value = '';
    });

    $('btnNew').addEventListener('click', function () {
      stopCurrentReply();S.sessionVersion++;S.sessionPromise=null;S.sid='';
      try{localStorage.removeItem('xiaoyin_sid');}catch(ignore){}
      $('chat').innerHTML = '';
      $('chat').hidden = true;
      $('welcome').hidden = false;
      $('textInput').value='';$('asrEdit').hidden=true;clearPhoto();autoSizeTextInput();
      window.dispatchEvent(new CustomEvent('forest:reset'));
      createSession().catch(function(error){if(error.name!=='AbortError')addError('对话没有建立成功','请稍后重试。');});
    });
  }

  /* ---------- 扫码开场语音（自我介绍，去掉文字版） ---------- */
  function setupWelcomeVoice() {
    var audio = $('welcomeAudio');
    var btn = $('btnWelcomePlay');
    if (!audio) return;
    audio.addEventListener('playing', function () { setAvatarState('speaking'); });
    audio.addEventListener('pause', function () { if (!audio.ended) setAvatarState('idle'); });
    audio.addEventListener('ended', function () { setAvatarState('idle'); });
    prepareWelcomeEnvelope(audio);
    if (btn) {
      btn.addEventListener('click', function () { playWelcomeVoice(); });
    }
    tryAutoplayWelcomeVoice();
  }

  function prepareWelcomeEnvelope(audio) {
    if (S.welcomeEnvelope || S.welcomeEnvelopeLoading || !window.ForestSpeechEnvelope) return;
    var Context=window.OfflineAudioContext||window.webkitOfflineAudioContext;
    if(!Context)return;
    var context;
    try{context=new Context(1,1,16000);}catch(e){return;}
    S.welcomeEnvelopeLoading=fetch(audio.currentSrc||audio.src)
      .then(function(r){if(!r.ok)throw new Error('welcome audio');return r.arrayBuffer();})
      .then(function(bytes){return context.decodeAudioData(bytes);})
      .then(function(buffer){S.welcomeEnvelope=window.ForestSpeechEnvelope.build(buffer,1);})
      .catch(function(){S.welcomeEnvelope=null;});
  }

  function playWelcomeVoice() {
    var audio = $('welcomeAudio');
    if (!audio) return;
    stopAudio();
    if (audio.ended) audio.currentTime = 0;
    audio.muted = false;
    var p = audio.play();
    if (p && p.catch) p.catch(function () {});
  }

  function tryAutoplayWelcomeVoice() {
    var audio = $('welcomeAudio');
    if (!audio) return;
    // 先以静音方式请求播放：多数手机浏览器允许静音自动播放，
    // 成功后再取消静音，争取实现“扫码即播”的有声开场。
    audio.muted = true;
    var p = audio.play();
    if (!p || !p.then) { audio.muted = false; return; }
    p.then(function () {
      try { audio.muted = false; audio.currentTime = 0; } catch (e) {}
      var p2 = audio.play();
      if (p2 && p2.catch) p2.catch(function () {});
    }).catch(function () {
      // 自动播放被浏览器拦截：保留“听小博士自我介绍”按钮，点一下即可播放。
      audio.muted = false;
    });
  }

  function init() {
    if(S.initializing)return;
    S.initializing=true;
    if(!S.bound){bind();S.bound=true;}
    if($('startupError'))$('startupError').hidden=true;
    if($('btnStartupRetry'))$('btnStartupRetry').disabled=true;
    fetch('/api/client-config').then(function (r) { if(!r.ok)throw Error('config unavailable');return r.json(); }).then(function (cfg) {
      S.cfg = cfg;
      $('charName').textContent = cfg.character.name;
      $('brandSub').textContent = '自然探究 AI 伙伴 · ' + cfg.course.stage_grade + cfg.course.subject;
      $('textInput').maxLength = Number(cfg.limits && cfg.limits.max_input_chars) || 300;
      setupWelcomeVoice();
      renderStages(cfg.stages || [], S.stageId);
      renderVoiceCapability();
      var saved = null;
      try { saved = localStorage.getItem('xiaoyin_sid'); } catch (e) {}
      if (saved) {
        return restoreSession(saved).then(function (sess) {
          if (sess) {
            renderHistory(sess);
            addNotice('欢迎回来，我们接着刚才的继续聊。');
          } else {
            return createSession();
          }
        });
      } else {
        return createSession();
      }
    }).catch(function () {
      if($('startupError'))$('startupError').hidden=false;
      else addError('页面没有加载完整', '请刷新页面再试一次。');
    }).then(function(){S.initializing=false;if($('btnStartupRetry'))$('btnStartupRetry').disabled=false;});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else { init(); }
})();
