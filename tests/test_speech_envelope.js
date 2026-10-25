'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const ROOT = path.resolve(__dirname, '..');
const ENVELOPE_PATH = path.join(ROOT, 'web', 'speech-envelope.js');
const APP_PATH = path.join(ROOT, 'web', 'app.js');

function loadEnvelope() {
  const window = {};
  const context = vm.createContext({ window });
  vm.runInContext(fs.readFileSync(ENVELOPE_PATH, 'utf8'), context, { filename: ENVELOPE_PATH });
  return window.ForestSpeechEnvelope;
}

function audioBuffer() {
  const sampleRate = 1000;
  const samples = new Float32Array(sampleRate);
  for (let i = 0; i < samples.length; i += 1) {
    if (i < 200) samples[i] = 0.5;
    else if (i >= 400 && i < 700) samples[i] = 0.2;
  }
  return {
    sampleRate,
    length: samples.length,
    getChannelData() {
      return samples;
    }
  };
}

test('envelope follows audible and silent portions of the actual audio buffer', () => {
  const speech = loadEnvelope();
  const envelope = speech.build(audioBuffer(), 7);

  assert.equal(envelope.seq, 7);
  assert.ok(envelope.step > 0);
  assert.ok(speech.level({ paused: false, ended: false, currentTime: 0.1 }, envelope, 7) > 0.6);
  assert.equal(speech.level({ paused: false, ended: false, currentTime: 0.3 }, envelope, 7), 0);
  assert.ok(speech.level({ paused: false, ended: false, currentTime: 0.5 }, envelope, 7) > 0);
  assert.equal(speech.level({ paused: false, ended: false, currentTime: 0.9 }, envelope, 7), 0);
});

test('mouth level closes on pause, end, stale audio sequence, and out-of-range time', () => {
  const speech = loadEnvelope();
  const envelope = speech.build(audioBuffer(), 9);

  assert.equal(speech.level({ paused: true, ended: false, currentTime: 0.1 }, envelope, 9), 0);
  assert.equal(speech.level({ paused: false, ended: true, currentTime: 0.1 }, envelope, 9), 0);
  assert.equal(speech.level({ paused: false, ended: false, currentTime: 0.1 }, envelope, 10), 0);
  assert.equal(speech.level({ paused: false, ended: false, currentTime: 2 }, envelope, 9), 0);
  assert.equal(speech.level({ paused: false, ended: false, muted:true, currentTime: 0.1 }, envelope, 9), 0);
});

test('production fallback never invents a fixed-frequency talking mouth', () => {
  const appSource = fs.readFileSync(APP_PATH, 'utf8');
  assert.doesNotMatch(appSource, /Math\.sin\(a\.currentTime\*11\)/);
  assert.match(appSource, /S\.speechEnvelope\s*=\s*null/);
  assert.match(appSource, /if\(seq!==S\.audioSeq\|\|S\.audioEl!==a\)return;/);
});
