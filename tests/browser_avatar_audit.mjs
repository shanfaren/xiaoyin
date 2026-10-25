import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const SCREENSHOTS = path.join(ROOT, 'docs', '2D_Avatar_Audit', 'screenshots', '20261025');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const PORT = 9337;
const BASE_URL = process.env.AVATAR_AUDIT_BASE_URL || 'http://127.0.0.1:8000/?avatarAudit=1';

fs.mkdirSync(SCREENSHOTS, { recursive: true });
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'forest-avatar-audit-'));

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForJson(url, attempts = 100) {
  for (let i = 0; i < attempts; i += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return response.json();
    } catch {
      // Chrome is still starting.
    }
    await sleep(100);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

class Cdp {
  constructor(url) {
    this.nextId = 1;
    this.pending = new Map();
    this.events = [];
    this.socket = new WebSocket(url);
  }

  async connect() {
    await new Promise((resolve, reject) => {
      this.socket.addEventListener('open', resolve, { once: true });
      this.socket.addEventListener('error', reject, { once: true });
    });
    this.socket.addEventListener('message', (event) => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(message.error.message));
        else pending.resolve(message.result);
        return;
      }
      this.events.push(message);
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    this.socket.close();
  }
}

const audioPreload = String.raw`
(() => {
  const nativeFetch = window.fetch.bind(window);
  window.__avatarAuditVibrationCount = 0;
  try {
    Object.defineProperty(navigator, 'vibrate', {
      configurable: true,
      value: () => {
        window.__avatarAuditVibrationCount += 1;
        return true;
      }
    });
  } catch {}

  function makeWav(longPlayback) {
    const sampleRate = 16000;
    const segments = longPlayback ? [
      { seconds: 1.0, amplitude: 0.42 },
      { seconds: 0.3, amplitude: 0 },
      { seconds: 1.8, amplitude: 0.22 },
      { seconds: 0.6, amplitude: 0 }
    ] : [
      { seconds: 0.65, amplitude: 0.42 },
      { seconds: 0.45, amplitude: 0 },
      { seconds: 0.45, amplitude: 0.22 },
      { seconds: 0.45, amplitude: 0 }
    ];
    const count = Math.round(segments.reduce((total, item) => total + item.seconds, 0) * sampleRate);
    const bytes = new ArrayBuffer(44 + count * 2);
    const view = new DataView(bytes);
    function text(offset, value) {
      for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
    }
    text(0, 'RIFF');
    view.setUint32(4, 36 + count * 2, true);
    text(8, 'WAVE');
    text(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    text(36, 'data');
    view.setUint32(40, count * 2, true);

    let cursor = 0;
    for (const segment of segments) {
      const length = Math.round(segment.seconds * sampleRate);
      for (let i = 0; i < length && cursor < count; i += 1, cursor += 1) {
        const sample = Math.sin((cursor / sampleRate) * Math.PI * 2 * 180) * segment.amplitude;
        view.setInt16(44 + cursor * 2, Math.round(sample * 32767), true);
      }
    }
    return new Blob([bytes], { type: 'audio/wav' });
  }

  window.fetch = async function (input, init) {
    const url = typeof input === 'string' ? input : input.url;
    if (url.includes('/api/asr')) {
      window.__avatarAuditAsrCount = (window.__avatarAuditAsrCount || 0) + 1;
      return new Response(JSON.stringify({ ok: true, text: '竹节虫为什么像树枝？' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    }
    if (url.includes('/api/tts')) {
      window.__avatarAuditTtsCount = (window.__avatarAuditTtsCount || 0) + 1;
      return new Response(makeWav(window.__avatarAuditTtsCount >= 3), {
        status: 200,
        headers: { 'Content-Type': 'audio/wav', 'Cache-Control': 'no-store' }
      });
    }
    const response = await nativeFetch(input, init);
    if (url.includes('/api/client-config')) {
      const json = await response.json();
      json.voice = json.voice || {};
      json.voice.tts = json.voice.tts || {};
      json.voice.tts.state = 'configured';
      json.voice.auto_play = true;
      json.voice.auto_send = false;
      return new Response(JSON.stringify(json), {
        status: response.status,
        headers: { 'Content-Type': 'application/json' }
      });
    }
    return response;
  };
})();
`;

const chrome = spawn(CHROME, [
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`,
  '--no-first-run',
  '--window-position=-32000,-32000',
  '--disable-breakpad',
  '--disable-crash-reporter',
  '--disable-background-networking',
  '--disable-background-timer-throttling',
  '--disable-backgrounding-occluded-windows',
  '--disable-renderer-backgrounding',
  '--autoplay-policy=no-user-gesture-required',
  '--use-fake-ui-for-media-stream',
  '--use-fake-device-for-media-stream',
  '--mute-audio',
  '--disable-audio-output',
  '--disable-features=AudioServiceSandbox,AudioServiceOutOfProcess',
  '--ignore-gpu-blocklist',
  '--enable-webgl',
  '--enable-unsafe-swiftshader',
  '--use-angle=swiftshader',
  '--window-size=1440,1000',
  'about:blank'
], {
  stdio: 'ignore',
  windowsHide: true
});

let cdp;
const errors = [];
const screenshots = [];

try {
  const targets = await waitForJson(`http://127.0.0.1:${PORT}/json/list`);
  const target = targets.find((item) => item.type === 'page');
  assert.ok(target, 'Chrome page target was not created');

  cdp = new Cdp(target.webSocketDebuggerUrl);
  await cdp.connect();
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Log.enable');
  await cdp.send('Network.enable');
  await cdp.send('Page.bringToFront');
  await cdp.send('Emulation.setFocusEmulationEnabled', { enabled: true });
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: audioPreload });

  async function evaluate(expression, awaitPromise = false, userGesture = false) {
    const result = await cdp.send('Runtime.evaluate', {
      expression,
      awaitPromise,
      userGesture,
      returnByValue: true
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    }
    return result.result.value;
  }

  async function waitFor(expression, timeoutMs = 10000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      if (await evaluate(expression)) return;
      await sleep(16);
    }
    const diagnostics = await evaluate(`({
      animation: window.__forestCharacter2D ? window.__forestCharacter2D.animationState() : null,
      audio: window.__forestAudioState ? window.__forestAudioState() : null
    })`).catch(() => null);
    throw new Error(`Timed out waiting for: ${expression}; diagnostics=${JSON.stringify(diagnostics)}`);
  }

  async function capture(name) {
    const result = await cdp.send('Page.captureScreenshot', {
      format: 'png',
      fromSurface: true,
      captureBeyondViewport: false
    });
    const output = path.join(SCREENSHOTS, name);
    fs.writeFileSync(output, Buffer.from(result.data, 'base64'));
    screenshots.push(output);
  }

  async function setState(state) {
    await evaluate(`window.__forestSetAvatarState(${JSON.stringify(state)})`);
    await waitFor(`document.getElementById('characterStage').dataset.state === ${JSON.stringify(state)}`);
    await sleep(350);
  }

  async function waitForPage() {
    await waitFor(`document.readyState === 'complete'`);
    await waitFor(`document.querySelector('#characterStage canvas') && document.getElementById('modelLoading').hidden`);
    await waitFor(`window.__forestCharacter2D && window.__forestSetAvatarState`);
  }

  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false
  });
  const navigationStarted = Date.now();
  await cdp.send('Page.navigate', { url: BASE_URL });
  await waitForPage();
  const modelReadyMs = Date.now() - navigationStarted;
  assert.equal(await evaluate(`document.visibilityState`), 'visible', 'headless page is not visible');
  await waitFor(`performance.getEntriesByType('resource').some((entry) => entry.name.includes('background_candidates'))`);
  const backgroundAudit = await evaluate(`({
    backgroundImage: getComputedStyle(document.getElementById('companion')).backgroundImage,
    backgroundSize: getComputedStyle(document.getElementById('companion')).backgroundSize,
    oldForestLoaded: performance.getEntriesByType('resource').some((entry) => entry.name.includes('forest-scene.js'))
  })`);
  assert.match(backgroundAudit.backgroundImage, /background_candidates/);
  assert.equal(backgroundAudit.backgroundSize, 'cover');
  assert.equal(backgroundAudit.oldForestLoaded, false);
  const characterResourceAudit = await evaluate(`performance.getEntriesByType('resource')
    .filter((entry) => entry.name.includes('/assets/character_optimized/'))
    .map((entry) => ({ name: entry.name, bytes: entry.transferSize, duration: Math.round(entry.duration) }))`);
  assert.ok(characterResourceAudit.length >= 1, 'optimized idle character was not requested');
  assert.ok(characterResourceAudit.every((entry) => entry.bytes < 250000), 'an unoptimized character image was loaded');

  const talkButton = await evaluate(`(() => {
    const box = document.getElementById('companionTalk').getBoundingClientRect();
    return { x: box.left + box.width / 2, y: box.top + box.height / 2 };
  })()`);
  async function pressTalk() {
    await evaluate(`document.getElementById('companionTalk').dispatchEvent(new PointerEvent('pointerdown', {
      bubbles: true, pointerId: 101, pointerType: 'mouse', button: 0,
      clientX: ${talkButton.x}, clientY: ${talkButton.y}
    }))`);
    await waitFor(`document.body.classList.contains('voice-input-active') && !document.getElementById('recLayer').hidden`, 4000);
    await waitFor(`window.forestConversation.snapshot().recording === true`, 5000);
    assert.equal(await evaluate(`window.__avatarAuditVibrationCount`), 1);
  }
  async function releaseTalk(y = talkButton.y) {
    await evaluate(`window.dispatchEvent(new PointerEvent('pointerup', {
      bubbles: true, pointerId: 101, pointerType: 'mouse', button: 0,
      clientX: ${talkButton.x}, clientY: ${y}
    }))`);
  }

  await pressTalk();
  await capture('desktop_voice_recording.png');
  await evaluate(`document.getElementById('companionTalk').dispatchEvent(new PointerEvent('pointermove', {
    bubbles: true, pointerId: 101, pointerType: 'mouse', button: 0,
    clientX: ${talkButton.x}, clientY: ${talkButton.y - 90}
  }))`);
  await waitFor(`document.body.classList.contains('voice-cancel-armed')`);
  await capture('desktop_voice_cancel.png');
  const asrBeforeCancel = await evaluate(`window.__avatarAuditAsrCount || 0`);
  await releaseTalk(talkButton.y - 90);
  await waitFor(`document.getElementById('recLayer').hidden`);
  assert.equal(await evaluate(`document.getElementById('asrEdit').hidden`), true);

  await evaluate(`document.getElementById('companionTalk').dispatchEvent(new PointerEvent('pointerdown', {
    bubbles: true, pointerId: 101, pointerType: 'mouse', button: 0,
    clientX: ${talkButton.x}, clientY: ${talkButton.y}
  }))`);
  await waitFor(`window.forestConversation.snapshot().recording === true`, 5000);
  assert.equal(await evaluate(`window.__avatarAuditVibrationCount`), 2);
  await sleep(700);
  await releaseTalk();
  await waitFor(`document.getElementById('recLayer').dataset.state === 'result'`, 10000);
  assert.equal(await evaluate(`document.getElementById('recTranscript').textContent`), '竹节虫为什么像树枝？');
  await capture('desktop_voice_transcript.png');
  await waitFor(`!document.getElementById('asrEdit').hidden`, 10000);
  const voiceTranscript = await evaluate(`document.getElementById('asrText').value`);
  assert.equal(voiceTranscript, '竹节虫为什么像树枝？');
  const voiceGestureAudit = {
    vibrationCount: await evaluate(`window.__avatarAuditVibrationCount`),
    asrRequests: await evaluate(`window.__avatarAuditAsrCount || 0`),
    asrBeforeCancel,
    transcript: voiceTranscript
  };
  await evaluate(`document.getElementById('btnAsrCancel').click()`);
  await waitFor(`document.getElementById('asrEdit').hidden`);

  await setState('idle');
  await capture('desktop_idle.png');
  await setState('listening');
  await capture('desktop_listening.png');
  await setState('thinking');
  await capture('desktop_thinking.png');

  await evaluate(`window.__forestSpeechLevelOriginal = window.forestSpeechLevel; window.forestSpeechLevel = () => 0.82;`);
  await setState('speaking');
  await waitFor(`window.__forestCharacter2D.animationState().jawLevel > 0.5`, 3000);
  const visualJaw = await evaluate(`window.__forestCharacter2D.animationState().jawLevel`);
  assert.ok(visualJaw > 0.5, `visual speaking jaw level was too low: ${visualJaw}`);
  await capture('desktop_speaking.png');

  const nearClosed = await evaluate(`new Promise((resolve, reject) => {
    const started = performance.now();
    function observeBlink() {
      const state = window.__forestCharacter2D.animationState();
      if (state.blinkPhase === 'open') window.__forestCharacter2D.triggerBlink();
      if (state.blinkProgress >= 0.85) {
        resolve(state);
      } else if (performance.now() - started > 3000) {
        reject(new Error('blink frame was not observable'));
      } else {
        requestAnimationFrame(observeBlink);
      }
    }
    requestAnimationFrame(observeBlink);
  })`, true);
  assert.ok(nearClosed.blinkProgress >= 0.85);
  await capture('desktop_blink_closed.png');

  await evaluate(`window.forestSpeechLevel = window.__forestSpeechLevelOriginal; window.__forestSetAvatarState('idle');`);
  await sleep(300);
  await capture('desktop_recovered.png');

  await evaluate(`window.forestConversation.replay('口型同步测试')`, false, true);
  await waitFor(`window.forestConversation.snapshot().state === 'speaking'`);
  await waitFor(`window.forestSpeechLevel() > 0.15 && window.__forestCharacter2D.animationState().jawLevel > 0.1`, 2000);
  const audible = await evaluate(`({
    level: window.forestSpeechLevel(),
    state: window.forestConversation.snapshot().state,
    jaw: window.__forestCharacter2D.animationState().jawLevel
  })`);
  assert.equal(audible.state, 'speaking');
  assert.ok(audible.level > 0.15);
  assert.ok(audible.jaw > 0.1);
  await capture('desktop_audio_audible.png');

  await waitFor(`window.forestSpeechLevel() === 0`, 3000);
  const silent = await evaluate(`({
    level: window.forestSpeechLevel(),
    jaw: window.__forestCharacter2D.animationState().jawLevel
  })`);
  assert.equal(silent.level, 0);
  await waitFor(`window.__forestCharacter2D.animationState().jawLevel < 0.12`, 1000);
  const silentJaw = await evaluate(`window.__forestCharacter2D.animationState().jawLevel`);
  assert.ok(silentJaw < 0.12, `jaw did not close during silence: ${silentJaw}`);

  await waitFor(`window.forestConversation.snapshot().state === 'idle'`, 7000);
  const ended = await evaluate(`({
    state: window.forestConversation.snapshot().state,
    level: window.forestSpeechLevel(),
    jaw: window.__forestCharacter2D.animationState().jawLevel
  })`);
  assert.equal(ended.level, 0);
  assert.ok(ended.jaw < 0.05, `jaw did not close after playback ended: ${ended.jaw}`);

  await evaluate(`window.forestConversation.replay('第一轮')`);
  await waitFor(`window.forestConversation.snapshot().state === 'speaking'`);
  await waitFor(`window.forestSpeechLevel() > 0.1`, 2000);
  const firstRoundSeq = await evaluate(`window.__forestAudioState().audioSeq`);
  await evaluate(`window.forestConversation.replay('第二轮')`);
  await waitFor(`window.forestConversation.snapshot().state === 'speaking' && window.forestSpeechLevel() > 0.1`, 6000);
  const replaced = await evaluate(`({
    state: window.forestConversation.snapshot().state,
    level: window.forestSpeechLevel(),
    seq: window.__forestAudioState().audioSeq
  })`);
  assert.equal(replaced.state, 'speaking');
  assert.ok(replaced.seq > firstRoundSeq, 'replacement playback did not advance the audio sequence');
  await sleep(700);
  assert.equal(await evaluate(`window.forestConversation.snapshot().state`), 'speaking');

  await evaluate(`document.getElementById('btnStop').click()`);
  await waitFor(`window.forestConversation.snapshot().state === 'idle'`);
  await waitFor(`window.__forestCharacter2D.animationState().jawLevel < 0.05`, 3000);
  const stopped = await evaluate(`({
    state: window.forestConversation.snapshot().state,
    level: window.forestSpeechLevel(),
    jaw: window.__forestCharacter2D.animationState().jawLevel
  })`);
  assert.equal(stopped.level, 0);
  assert.ok(stopped.jaw < 0.05);
  await capture('desktop_audio_stopped.png');

  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: 390,
    height: 844,
    deviceScaleFactor: 2,
    mobile: true,
    screenWidth: 390,
    screenHeight: 844
  });
  await cdp.send('Page.navigate', { url: BASE_URL });
  await waitForPage();
  await setState('idle');
  const mobileLayout = await evaluate(`({
    width: innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    stage: (() => {
      const r = document.getElementById('characterStage').getBoundingClientRect();
      return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height };
    })()
  })`);
  assert.ok(mobileLayout.scrollWidth <= mobileLayout.width + 1, 'mobile page has horizontal overflow');
  assert.ok(mobileLayout.stage.width > 300 && mobileLayout.stage.height > 300, 'mobile character stage is too small');
  await capture('mobile_idle.png');

  const mobileTalk = await evaluate(`(() => {
    const box = document.getElementById('companionTalk').getBoundingClientRect();
    return { x: box.left + box.width / 2, y: box.top + box.height / 2 };
  })()`);
  await evaluate(`document.getElementById('companionTalk').dispatchEvent(new PointerEvent('pointerdown', {
    bubbles: true, pointerId: 202, pointerType: 'mouse', button: 0,
    clientX: ${mobileTalk.x}, clientY: ${mobileTalk.y}
  }))`);
  await waitFor(`document.body.classList.contains('voice-input-active') && !document.getElementById('recLayer').hidden`, 4000);
  await waitFor(`window.forestConversation.snapshot().recording === true`, 5000);
  assert.equal(await evaluate(`window.__avatarAuditVibrationCount`), 1);
  await capture('mobile_voice_recording.png');
  await evaluate(`document.getElementById('companionTalk').dispatchEvent(new PointerEvent('pointermove', {
    bubbles: true, pointerId: 202, pointerType: 'mouse', button: 0,
    clientX: ${mobileTalk.x}, clientY: ${mobileTalk.y - 90}
  }))`);
  await waitFor(`document.body.classList.contains('voice-cancel-armed')`);
  await evaluate(`window.dispatchEvent(new PointerEvent('pointerup', {
    bubbles: true, pointerId: 202, pointerType: 'mouse', button: 0,
    clientX: ${mobileTalk.x}, clientY: ${mobileTalk.y - 90}
  }))`);
  await waitFor(`document.getElementById('recLayer').hidden`);

  await evaluate(`window.__forestSpeechLevelOriginal = window.forestSpeechLevel; window.forestSpeechLevel = () => 0.82;`);
  await setState('speaking');
  await capture('mobile_speaking.png');

  const auditEvents = cdp.events
    .filter((event) => event.method === 'Runtime.exceptionThrown' ||
      event.method === 'Log.entryAdded' ||
      (event.method === 'Network.responseReceived' && event.params.response?.status >= 400))
    .map((event) => ({ method: event.method, params: event.params }));
  for (const event of auditEvents) {
    if (event.method === 'Runtime.exceptionThrown') {
      errors.push(event.params.exceptionDetails?.exception?.description || event.params.exceptionDetails?.text);
    } else if (event.method === 'Network.responseReceived') {
      errors.push(`${event.params.response.status} ${event.params.response.url}`);
    } else if (event.params.entry.level === 'error' && !event.params.entry.text.startsWith('Failed to load resource:')) {
      errors.push(event.params.entry.text);
    }
  }

  console.log(JSON.stringify({
    ok: true,
    screenshots,
    audible,
    silent,
    silentJaw,
    ended,
    replaced,
    stopped,
    mobileLayout,
    backgroundAudit,
    modelReadyMs,
    characterResourceAudit,
    voiceGestureAudit,
    errors
  }, null, 2));

  assert.deepEqual(errors, []);
} catch (error) {
  console.error('AUDIT_ERROR', error.stack || error);
  if (cdp) {
    const messages = [];
    for (const event of cdp.events) {
      if (event.method === 'Runtime.exceptionThrown') {
        messages.push(event.params.exceptionDetails?.exception?.description || event.params.exceptionDetails?.text);
      } else if (event.method === 'Runtime.consoleAPICalled') {
        messages.push(event.params.args.map((arg) => arg.value || arg.description || '').join(' '));
      } else if (event.method === 'Log.entryAdded') {
        messages.push(`${event.params.entry.level}: ${event.params.entry.text}`);
      }
    }
    console.error('AUDIT_BROWSER_EVENTS', JSON.stringify([...new Set(messages)].slice(0, 30), null, 2));
  }
  process.exitCode = 1;
} finally {
  if (cdp) {
    try {
      await Promise.race([cdp.send('Browser.close'), sleep(1000)]);
    } catch {
      // Browser may already be closing after a page error.
    }
    cdp.close();
  }
  chrome.kill();
  await sleep(1000);
  if (profile.startsWith(os.tmpdir())) {
    try {
      fs.rmSync(profile, { recursive: true, force: true, maxRetries: 3, retryDelay: 150 });
    } catch {
      // A Chrome crash handler may briefly retain the temporary profile.
    }
  }
}
