/* 小隐 · 学生端逻辑
   交互约束：不出现 API/开发术语；每次反馈简短适龄；区分文字/语音/照片三种输入，
   三者共享同一会话上下文；语音链路 = 录音 → ASR → 模型 → TTS → 播放。 */

(function () {
  'use strict';

  /* ---------- 角色头像（内联 SVG，离线可用；资产文件见 /assets/avatar/） ---------- */
  var AVATAR_SVG = ''
    + '<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="小隐">'
    + '<defs>'
    + '<radialGradient id="xg1" cx="50%" cy="32%" r="72%">'
    + '<stop offset="0%" stop-color="#ffffff"/><stop offset="100%" stop-color="#EFE6D2"/></radialGradient>'
    + '<filter id="xg2" x="-60%" y="-60%" width="220%" height="220%">'
    + '<feGaussianBlur stdDeviation="2.4" result="b"/>'
    + '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
    + '</defs>'
    + '<path d="M50 17 C61 1, 83 6, 83 9 C80 19, 60 19, 50 17 Z" fill="#4A8F56"/>'
    + '<path d="M54 15 L56 9.5 L57.6 14.4" stroke="#2F6B3F" stroke-width="1.4" fill="none" stroke-linejoin="round"/>'
    + '<path d="M56.5 13 L76 8.8" stroke="#2F6B3F" stroke-width="1" opacity="0.5" fill="none"/>'
    + '<rect x="14" y="20" width="72" height="66" rx="24" fill="#2F6B3F"/>'
    + '<rect x="19" y="25" width="62" height="56" rx="20" fill="url(#xg1)" stroke="#8FBF8A" stroke-width="1.2"/>'
    + '<ellipse cx="50" cy="32.5" rx="24" ry="7" fill="#FFFFFF" opacity="0.5"/>'
    + '<rect x="27" y="37" width="46" height="28" rx="13" fill="#1D3B28" opacity="0.92"/>'
    + '<circle cx="40" cy="51" r="11" fill="#F2C14E" opacity="0.105"/>'
    + '<circle cx="60" cy="51" r="11" fill="#F2C14E" opacity="0.105"/>'
    + '<circle cx="40" cy="51" r="9.4" fill="#F2C14E" opacity="0.21"/>'
    + '<circle cx="60" cy="51" r="9.4" fill="#F2C14E" opacity="0.21"/>'
    + '<circle cx="40" cy="51" r="7.8" fill="#F2C14E" opacity="0.45"/>'
    + '<circle cx="60" cy="51" r="7.8" fill="#F2C14E" opacity="0.45"/>'
    + '<circle cx="40" cy="51" r="6.4" fill="#F2C14E" filter="url(#xg2)"/>'
    + '<circle cx="60" cy="51" r="6.4" fill="#F2C14E" filter="url(#xg2)"/>'
    + '<circle cx="41.6" cy="49.2" r="1.9" fill="#FFFDF3"/><circle cx="61.6" cy="49.2" r="1.9" fill="#FFFDF3"/>'
    + '<path d="M46.9 59.2 A3.4 3.4 0 0 0 53.1 59.2" stroke="#FBF7EC" stroke-width="1.7" fill="none" stroke-linecap="round"/>'
    + '<circle cx="79" cy="71" r="5" fill="#D7E9CF" opacity="0.85"/>'
    + '<circle cx="79" cy="71" r="9" fill="none" stroke="#C8552F" stroke-width="3.2"/>'
    + '<path d="M85.2 76.2 L92.4 84.2 L89.4 86.8 L82.2 78.8 Z" fill="#C8552F"/>'
    + '</svg>';

  /* ---------- 状态 ---------- */
  var S = {
    cfg: null,
    sid: '',
    stageId: 'intro',
    mode: 'student',
    voiceMode: false,      // 底部栏当前是语音还是文字
    recording: false,
    busy: false,
    mediaRecorder: null,
    chunks: [],
    audioEl: null,
    speechRec: null,
    photo: null,           // {dataUrl, base64, mime, name, size}
    abort: null
  };

  var $ = function (id) { return document.getElementById(id); };

  /* ---------- 头像状态（idle/listening/thinking/speaking） ---------- */
  var AVATAR_STATE = 'idle';
  function setAvatarState(state) {
    if (state === AVATAR_STATE) return;
    AVATAR_STATE = state;
    ['brandAvatarImg', 'heroAvatarImg'].forEach(function (id) {
      var img = $(id);
      if (!img) return;
      img.src = '/assets/avatar/xiaoyin_' + state + '.svg';
    });
  }

  function avatarFallback() {
    // 资产缺失时退回内联 SVG（离线可用）
    ['brandAvatar', 'heroAvatar'].forEach(function (id) {
      var box = $(id);
      if (box && !box.querySelector('svg')) box.innerHTML = AVATAR_SVG;
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
    if (S.audioEl) { try { S.audioEl.pause(); } catch (e) {} S.audioEl = null; }
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
        addMsg('a', m.content);
      }
    });
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
    var d = document.createElement('div');
    d.className = 'notice';
    d.textContent = text;
    $('chat').appendChild(d);
    scrollBottom();
  }

  function addError(title, detail) {
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
    var st = null;
    stages.forEach(function (s) { if (s.id === currentId) st = s; });
    if (!st) st = stages[0];
    if (!st) return;
    S.stageId = st.id;
    $('taskTitle').textContent = st.name;
    $('taskGoal').textContent = st.goal;
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
    $('textInput').value = '';
    doChat({ text: text, input_kind: 'text' });
  }

  /* ---------- 发送照片 ---------- */
  function sendPhoto() {
    if (!S.photo || S.busy) return;
    var q = ($('photoQuestion').value || '').trim();
    doVision(S.photo, q);
  }

  /* ---------- 对话主流程 ---------- */
  function doChat(payload) {
    if (!S.sid) { createSession().then(function () { doChat(payload); }); return; }
    stopAudio();
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
              handleEvent(ev, bubble, function (t) { acc += t; });
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
    if (ttsOk) {
      setStatus('播放中…');
      setAvatarState('speaking');
      fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text })
      }).then(function (r) {
        if (!r.ok) throw new Error('tts');
        return r.blob();
      }).then(function (blob) {
        var url = URL.createObjectURL(blob);
        var a = new Audio(url);
        S.audioEl = a;
        a.onended = function () { setStatus(''); setAvatarState('idle'); };
        return a.play();
      }).catch(function () {
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
    $('welcome').hidden = true;
    $('chat').hidden = false;
    addMsg('u', '（我拍了一张照片）' + (question ? ' ' + question : ''), '照片');
    var bubble = addMsg('a', '');
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
        question: question || '', session_id: S.sid
      })
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; }); })
      .then(function (res) {
        var j = res.body || {};
        if (j.ok && j.text) {
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
  function startRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      fallbackSpeechRecognition('这台设备的浏览器不支持录音。');
      return;
    }
    if (!isSecure()) {
      addNotice('录音需要 https 安全地址。当前不是 https，可能无法录音，请先用文字输入，或让老师用 https 地址打开。');
      return;
    }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
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
      $('recLayer').hidden = false;
      setStatus('正在听…');
      setAvatarState('listening');
    }).catch(function (err) {
      $('recLayer').hidden = true;
      addNotice('没有拿到麦克风权限。请在浏览器里允许使用麦克风，或者直接用文字输入。');
    });
  }

  function stopRecording(send) {
    S.recording = false;
    $('recLayer').hidden = true;
    setStatus('');
    if (S.mediaRecorder && S.mediaRecorder.state !== 'inactive') {
      if (send === false) {
        S.mediaRecorder.onstop = null;
        try { S.mediaRecorder.stop(); } catch (e) {}
      } else {
        S.mediaRecorder.stop();
      }
    }
    S.mediaRecorder = null;
  }

  function transcribe(blob) {
    setStatus('识别中…');
    setAvatarState('listening');
    var fr = new FileReader();
    fr.onload = function () {
      var b64 = String(fr.result).split(',')[1];
      fetch('/api/asr', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio_base64: b64, format: 'webm' })
      }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
        .then(function (res) {
          setStatus('');
          var j = res.body || {};
          if (j.ok && j.text) {
            showAsrEdit(j.text);
          } else if (j.error === 'not_configured') {
            addNotice('语音识别还没有配置好，所以我还听不懂录音。你可以直接打字告诉我。');
            fallbackSpeechRecognition('要不要试试手机自带的语音输入？');
          } else {
            addError('没有听清楚', (j.message || '') + ' 再说一次试试？');
          }
        }).catch(function () {
          setStatus('');
          addError('录音没有发出去', '网络不太好，请再试一次。');
        });
    };
    fr.readAsDataURL(blob);
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

  /* ---------- 初始化 ---------- */
  function bind() {
    var bi = $('brandAvatarImg'), hi = $('heroAvatarImg');
    if (bi) { bi.onerror = avatarFallback; }
    if (hi) { hi.onerror = avatarFallback; }

    $('btnSend').addEventListener('click', function () {
      if (S.photo) { sendPhoto(); } else { sendText($('textInput').value); }
    });
    $('textInput').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); sendText($('textInput').value); }
    });
    $('btnStop').addEventListener('click', function () {
      if (S.abort) { try { S.abort.abort(); } catch (e) {} }
      if (S.sid) {
        fetch('/api/chat/stop', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: S.sid })
        }).catch(function () {});
      }
      stopAudio();
      setStatus('');
    });
    $('btnPhoto').addEventListener('click', pickPhoto);
    $('fileInput').addEventListener('change', onFile);
    $('btnPhotoDelete').addEventListener('click', clearPhoto);
    $('btnPhotoReplace').addEventListener('click', pickPhoto);
    $('btnPhotoReplace').setAttribute('type', 'button');
    $('btnPhotoDelete').setAttribute('type', 'button');

    $('btnModeToggle').addEventListener('click', function () {
      S.voiceMode = !S.voiceMode;
      $('modeIcon').textContent = S.voiceMode ? '🎤' : '⌨';
      $('modeLabel').textContent = S.voiceMode ? '语音' : '文字';
      $('textInput').placeholder = S.voiceMode ? '点右边的按钮开始说话…' : '说说你发现了什么…';
      if (S.voiceMode) startRecording();
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
      renderQuick(cfg.quick_questions || []);
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
