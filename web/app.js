/* 森林小博士 · 学生端逻辑
   交互约束：不出现 API/开发术语；每次反馈简短适龄；区分文字/语音/照片三种输入，
   三者共享同一会话上下文；语音链路 = 录音 → ASR → 模型 → TTS → 播放。 */

(function () {
  'use strict';

  /* 官方勘探家头像；与桌面悬浮球使用同一资产。 */
  var AVATAR_SVG = '<img src="/assets/avatar/forest-official.png?v=20261015official1" alt="森林小博士" loading="lazy">';

  /* ---------- 状态 ---------- */
  var S = {
    cfg: null,
    sid: '',
    stageId: 'qa',
    mode: 'student',
    voiceMode: false,      // 底部栏当前是语音还是文字
    recording: false,
    busy: false,
    mediaRecorder: null,
    chunks: [],
    audioEl: null,
    speechRec: null,
    photo: null,           // {dataUrl, base64, mime, name, size}
    abort: null,
    followupVersion: 0,
    stopped: false,
    audioSeq: 0, playbackAudio: null, audioURL:null, micStream: null, recordTimer: null, voiceVersion: 0
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

  function stopAudio() {
    S.audioSeq++;
    if (S.audioEl) { try { S.audioEl.pause(); } catch (e) {} S.audioEl = null; }
    if (S.audioURL) { URL.revokeObjectURL(S.audioURL); S.audioURL=null; }
    if (window.speechSynthesis) { try { window.speechSynthesis.cancel(); } catch (e) {} }
  }

  function isWeChat() { return /MicroMessenger/i.test(navigator.userAgent); }
  function isSecure() {
    return location.protocol === 'https:' || ['localhost', '127.0.0.1'].indexOf(location.hostname) >= 0;
  }

  /* ---------- 会话 ---------- */
  function createSession() {
    return fetch('/api/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'student', stage_id: S.stageId })
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (!j.ok) throw new Error('会话创建失败');
      S.sid = j.session_id;
      try { localStorage.setItem('xiaoyin_sid', S.sid); } catch (e) {}
      return j;
    });
  }

  function restoreSession(sid) {
    return fetch('/api/session/' + encodeURIComponent(sid) + '?mode=student')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!j || !j.ok) return null;
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
  function addMsg(role, text, tag) {
    var wrap = document.createElement('div');
    wrap.className = 'msg ' + role;
    var who = document.createElement('div');
    who.className = 'who';
    who.innerHTML = AVATAR_SVG;
    var bubble = document.createElement('div');
    bubble.className = 'bubble';
    if (tag) {
      var t = document.createElement('span');
      t.className = 'imgtag';
      t.textContent = '📷 ' + tag;
      bubble.appendChild(t);
    }
    bubble.appendChild(document.createTextNode(text));
    wrap.appendChild(who);
    wrap.appendChild(bubble);
    $('chat').appendChild(wrap);
    scrollBottom();
    return bubble;
  }

  function scrollBottom() {
    var m = $('main');
    m.scrollTop = m.scrollHeight;
  }

  function addNotice(text) {
    window.dispatchEvent(new CustomEvent('forest:notice', {detail:{text:text}}));
    var d = document.createElement('div');
    d.className = 'notice';
    d.textContent = text;
    $('chat').appendChild(d);
    scrollBottom();
  }

  function addError(title, detail) {
    window.dispatchEvent(new CustomEvent('forest:notice', {detail:{text:title+' '+(detail||'')}}));
    var d = document.createElement('div');
    d.className = 'err';
    var b = document.createElement('b');
    b.textContent = title;
    d.appendChild(b);
    d.appendChild(document.createTextNode(detail || ''));
    $('chat').appendChild(d);
    scrollBottom();
  }

  function renderStages(stages, currentId) {
    currentId = ({intro:'qa',aichat1:'qa',aichat2:'share',extension:'share',level1:'hint',level2:'hint',level3:'hint',level4:'hint',level5:'hint'})[currentId] || currentId;
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
    renderQuick(st.questions || []);
  }

  function renderQuick(qs) {
    var box = $('quickList');
    box.innerHTML = '';
    qs.forEach(function (q) {
      var b = document.createElement('button');
      b.className = 'chip';
      b.type = 'button';
      b.textContent = q;
      b.addEventListener('click', function () { sendText(q); });
      box.appendChild(b);
    });
  }

  function renderVoiceCapability() {
    var v = (S.cfg && S.cfg.voice) || {};
    var asrOk = v.asr && v.asr.state === 'configured';
    var hint = $('voiceHint');
    if (asrOk) {
      hint.textContent = '点一下，说完再点停止，我就能听懂啦。';
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
    doChat({ text: text, input_kind: 'text' });
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
      j.questions.forEach(function (question) {
        var button = document.createElement('button'); button.type='button'; button.className='chip'; button.textContent=question;
        button.addEventListener('click', function () { sendText(question); }); box.appendChild(button);
      });
      $('chat').appendChild(box); scrollBottom();
    }).catch(function () {});
  }

  /* ---------- 对话主流程 ---------- */
  function doChat(payload) {
    if (!S.sid) { createSession().then(function () { doChat(payload); }); return; }
    stopAudio();
    window.dispatchEvent(new CustomEvent('forest:question', {detail:{text:payload.text}}));
    clearFollowups();
    S.stopped = false;
    $('welcome').hidden = true;
    $('chat').hidden = false;
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
    var body = { session_id: S.sid, text: payload.text, mode: S.mode, stage_id: S.stageId,
                 input_kind: payload.input_kind || 'text' };

    fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: S.abort.signal
    }).then(function (resp) {
      if (!resp.ok || !resp.body) throw new Error('服务返回异常（' + resp.status + '）');
      var reader = resp.body.getReader();
      var dec = new TextDecoder('utf-8');
      var buf = '';
      function pump() {
        return reader.read().then(function (res) {
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
              handleEvent(ev, bubble, function (t) { acc += t; window.dispatchEvent(new CustomEvent('forest:partial',{detail:{text:acc}})); });
            });
          }
          return pump();
        });
      }
      return pump();
    }).catch(function (err) {
      if (err && err.name === 'AbortError') return;
      addError('哎呀，好像连不上了。', '请检查网络后再试一次。（' + (err && err.message ? err.message : '') + '）');
    }).then(function () {
      S.busy = false;
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

  function handleEvent(ev, bubble, onDelta) {
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
      onDelta(ev.text);
      bubble.appendChild(document.createTextNode(ev.text));
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
      addError(titles[ev.code] || '出了点小问题', ev.message || '');
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
        var url = URL.createObjectURL(blob);
        S.audioURL=url;
        var a = S.playbackAudio || new Audio();
        S.playbackAudio = a;
        a.src = url; a.muted = false;
        S.audioEl = a;
        a.onplaying = function () { if(seq===S.audioSeq){setStatus('播放中…'); setAvatarState('speaking');} };
        a.onended = function () { URL.revokeObjectURL(url); setStatus(''); setAvatarState('idle'); };
        return a.play();
      }).catch(function () {
        if (seq !== S.audioSeq) return;
        setStatus('');
        browserSpeak(text, btn);
      });
      return;
    }
    browserSpeak(text, btn);
  }

  function browserSpeak(text, btn) {
    if (!window.speechSynthesis) {
      addNotice('这台设备暂时不能朗读。可以请老师配置语音合成后使用。');
      return;
    }
    try {
      var u = new SpeechSynthesisUtterance(text);
      u.lang = 'zh-CN';
      u.rate = 0.95;
      u.onstart = function () { setStatus('播放中…（浏览器朗读）'); setAvatarState('speaking'); };
      u.onend = function () { setStatus(''); setAvatarState('idle'); };
      window.speechSynthesis.speak(u);
      if (btn) {
        btn.textContent = '⏹ 停止朗读';
        btn.onclick = function () { stopAudio(); setStatus(''); btn.textContent = '🔊 听一听'; };
      }
    } catch (e) {
      addNotice('浏览器朗读不可用，可以请老师配置语音合成。');
    }
  }

  /* ---------- 照片分析 ---------- */
  function doVision(photo, question) {
    if (!S.sid) { createSession().then(function () { doVision(photo, question); }); return; }
    stopAudio();
    clearFollowups();
    $('welcome').hidden = true;
    $('chat').hidden = false;
    addMsg('u', '（我拍了一张照片）' + (question ? ' ' + question : ''), '照片');
    var bubble = addMsg('a', '');
    var voiceAnswer = '';
    S.busy = true;
    $('btnSend').hidden = true;
    $('btnStop').hidden = false;
    setStatus('正在看照片…');
    setAvatarState('thinking');

    fetch('/api/vision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_base64: photo.base64, mime: photo.mime,
        question: question || '', session_id: S.sid, stage_id: S.stageId
      })
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; }); })
      .then(function (res) {
        var j = res.body || {};
        if (j.ok && j.text) {
          voiceAnswer=j.text;
          bubble.textContent = j.text;
          attachTools(bubble, j.text);
        } else if (j.error === 'not_configured') {
          addError('还看不懂照片', j.message || '');
          addNotice('现在可以先告诉我：照片里有什么？它躲在哪里？');
        } else if (j.error === 'too_large') {
          addError('照片太大啦', j.message || '');
        } else {
          addError('照片分析没有成功', (j.message || '') + ' 可以点“重试”再试一次。');
          addRetry(bubble.parentNode, photo, question);
        }
      }).catch(function () {
        addError('网络不太好', '照片没有发出去，请再试一次。');
        addRetry(bubble.parentNode, photo, question);
      }).then(function () {
        S.busy = false;
        $('btnSend').hidden = false;
        $('btnStop').hidden = true;
        setStatus('');
        clearPhoto();
        if (bubble.textContent.trim()) loadFollowups();
        if (voiceAnswer && S.cfg && S.cfg.voice && S.cfg.voice.auto_play) speak(voiceAnswer);
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
    if (S.playbackAudio) return;
    var a = new Audio(), url = URL.createObjectURL(wavBlob(new Float32Array(1600),16000));
    S.playbackAudio=a; a.src=url; a.muted=true;
    a.play().then(function () { if (a.src===url) { a.pause(); a.currentTime=0; a.muted=false; } URL.revokeObjectURL(url); }).catch(function () { a.muted=false; URL.revokeObjectURL(url); });
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
    if (S.busy || S.recording || S.micPending) return;
    stopAudio(); unlockPlayback();
    if (!isSecure()) {
      // 局域网HTTP不能直接访问网页麦克风，改由系统录音/选择录音提供音频。
      $('audioFileInput').value=''; $('audioFileInput').click();
      $('voiceHint').textContent='录好后返回这里，选择录音就能发送。';
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      fallbackSpeechRecognition('这台设备的浏览器不支持录音。');
      return;
    }
    if (!isSecure()) {
      addNotice('录音需要 https 安全地址。当前不是 https，可能无法录音，请先用文字输入，或让老师用 https 地址打开。');
      return;
    }
    S.micPending = true;
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      S.micPending = false;
      S.micStream = stream;
      S.chunks = [];
      var mr = new MediaRecorder(stream);
      S.mediaRecorder = mr;
      mr.ondataavailable = function (e) { if (e.data && e.data.size) S.chunks.push(e.data); };
      mr.onstop = function () {
        stream.getTracks().forEach(function (t) { t.stop(); });
        var blob = new Blob(S.chunks, { type: mr.mimeType || 'audio/webm' });
        transcribe(blob);
      };
      mr.start();
      S.recording = true;
      S.recordTimer=setTimeout(function () { if(S.recording) stopRecording(true); },60000);
      $('recLayer').hidden = false;
      setStatus('正在听…');
      setAvatarState('listening');
    }).catch(function (err) {
      S.micPending = false;
      $('recLayer').hidden = true;
      addNotice('没有拿到麦克风权限。请在浏览器里允许使用麦克风，或者直接用文字输入。');
    });
  }

  function stopRecording(send) {
    if(S.recordTimer) clearTimeout(S.recordTimer);
    S.recording = false;
    $('recLayer').hidden = true;
    setStatus('');
    if (S.mediaRecorder && S.mediaRecorder.state !== 'inactive') {
      if (send === false) {
        S.mediaRecorder.onstop = function () { if(S.micStream) S.micStream.getTracks().forEach(function (t) {t.stop();}); S.micStream=null; };
        try { S.mediaRecorder.stop(); } catch (e) {}
      } else {
        S.mediaRecorder.stop();
      }
    }
    S.mediaRecorder = null;
  }

  function transcribe(blob) {
    var version=++S.voiceVersion;
    S.busy=true; $('btnStop').hidden=false;
    setStatus('识别中…');
    setAvatarState('listening');
    normalizeAudio(blob).then(function (prepared) {
    var fr = new FileReader();
    fr.onload = function () {
      var b64 = String(fr.result).split(',')[1];
      fetch('/api/asr', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio_base64: b64, format: prepared.format })
      }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
        .then(function (res) {
          if(version!==S.voiceVersion) return;
          S.busy=false; $('btnStop').hidden=true;
          setStatus('');
          var j = res.body || {};
          if (j.ok && j.text) {
            if (S.cfg && S.cfg.voice && S.cfg.voice.auto_send) doChat({text:j.text,input_kind:'voice'});
            else showAsrEdit(j.text);
          } else if (j.error === 'not_configured') {
            addNotice('语音识别还没有配置好，所以我还听不懂录音。你可以直接打字告诉我。');
            fallbackSpeechRecognition('要不要试试手机自带的语音输入？');
          } else {
            addError('没有听清楚', (j.message || '') + ' 再说一次试试？');
          }
        }).catch(function () {
          if(version!==S.voiceVersion) return;
          S.busy=false; $('btnStop').hidden=true;
          setStatus('');
          addError('录音没有发出去', '网络不太好，请再试一次。');
        });
    };
    fr.readAsDataURL(prepared.blob);
    }).catch(function (err) { if(version!==S.voiceVersion) return; S.busy=false; $('btnStop').hidden=true; setStatus(''); addNotice(err.message || '无法读取录音，请再录一次。'); });
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
      rec.maxAlternatives = 1;
      rec.onresult = function (e) {
        var t = e.results[0][0].transcript;
        setStatus('');
        showAsrEdit(t);
      };
      rec.onerror = function () {
        setStatus('');
        addNotice('手机自带的语音输入没能用起来，请用文字告诉我吧。');
      };
      rec.onend = function () { setStatus(''); };
      S.speechRec = rec;
      setStatus('正在听…（手机自带识别）');
      rec.start();
    } catch (e) {
      addNotice(reason + ' 请用文字告诉我吧。');
    }
  }

  // UI-only bridge: both views use this device's existing session and voice chain.
  window.forestConversation = {
    snapshot: function () { return {busy:S.busy, recording:S.recording, state:AVATAR_STATE, profile:S.stageId}; },
    talk: function () { if(S.recording) stopRecording(true); else if(S.busy) $('btnStop').click(); else startRecording(); },
    cancel: function () { stopRecording(false); },
    replay: function (text) { unlockPlayback(); if(text) speak(text); },
    profile: function (id) { var b=document.querySelector('#interactionTabs [data-profile="'+id+'"]'); if(b) b.click(); }
  };

  /* ---------- 初始化 ---------- */
  function bind() {
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
    $('textInput').addEventListener('input', syncComposer);
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
    $('textInput').addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.isComposing && e.keyCode !== 229) {
        e.preventDefault();
        if (S.photo) sendPhoto(); else sendText($('textInput').value);
      }
    });
    $('btnStop').addEventListener('click', function () {
      S.voiceVersion++;
      S.stopped = true;
      clearFollowups();
      if (S.abort) { try { S.abort.abort(); } catch (e) {} }
      if (S.sid) {
        fetch('/api/chat/stop', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: S.sid })
        }).catch(function () {});
      }
      stopAudio();
      S.busy=false; $('btnStop').hidden=true;
      setStatus('');
    });
    $('btnPhoto').addEventListener('click', pickPhoto);
    $('fileInput').addEventListener('change', onFile);
    $('audioFileInput').addEventListener('change', function () { var audio=this.files&&this.files[0]; if(audio) transcribe(audio); });
    $('btnPhotoDelete').addEventListener('click', clearPhoto);
    $('btnPhotoReplace').addEventListener('click', pickPhoto);
    $('btnPhotoReplace').setAttribute('type', 'button');
    $('btnPhotoDelete').setAttribute('type', 'button');

    $('btnModeToggle').addEventListener('click', function () {
      S.voiceMode = true;
      startRecording();
    });

    $('btnVoiceBig').addEventListener('click', function () {
      S.voiceMode = true;
      $('modeIcon').textContent = '🎤';
      $('modeLabel').textContent = '语音';
      startRecording();
    });
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
      if (S.busy) return;
      clearFollowups();
      if (S.sid) {
        fetch('/api/session/' + encodeURIComponent(S.sid) + '/clear', { method: 'POST' })
          .catch(function () {});
      }
      $('chat').innerHTML = '';
      $('chat').hidden = true;
      $('welcome').hidden = false;
      stopAudio();
      addNotice('我们重新开始啦，你可以再问我一次。');
    });
  }

  function init() {
    bind();
    fetch('/api/client-config').then(function (r) { return r.json(); }).then(function (cfg) {
      S.cfg = cfg;
      $('charName').textContent = cfg.character.name;
      $('brandSub').textContent = '自然探究 AI 伙伴 · ' + cfg.course.stage_grade + cfg.course.subject;
      $('welcomeText').textContent = cfg.character.welcome;
      renderStages(cfg.stages || [], S.stageId);
      renderVoiceCapability();
      var saved = null;
      try { saved = localStorage.getItem('xiaoyin_sid'); } catch (e) {}
      if (saved) {
        restoreSession(saved).then(function (sess) {
          if (sess) {
            renderHistory(sess);
            addNotice('欢迎回来，我们接着刚才的继续聊。');
          } else {
            createSession();
          }
        });
      } else {
        createSession();
      }
    }).catch(function () {
      addError('页面没有加载完整', '请刷新页面再试一次。');
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else { init(); }
})();
