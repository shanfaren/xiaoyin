'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const SOURCE = path.join(__dirname, '..', 'web', 'hold-to-talk.js');

class FakeClassList {
  constructor() {
    this.values = new Set();
  }

  add(...names) {
    names.forEach((name) => this.values.add(name));
  }

  remove(...names) {
    names.forEach((name) => this.values.delete(name));
  }

  toggle(name, force) {
    if (force) this.values.add(name);
    else this.values.delete(name);
  }

  contains(name) {
    return this.values.has(name);
  }
}

class FakeElement extends EventTarget {
  constructor() {
    super();
    this.classList = new FakeClassList();
    this.disabled = false;
  }
}

function touchEvent(y) {
  return {
    touches: [{ clientY: y }],
    changedTouches: [{ clientY: y }]
  };
}

function loadHold(vibrate) {
  const window = new EventTarget();
  window.navigator = { vibrate };
  window.CustomEvent = CustomEvent;
  const context = vm.createContext({ window, navigator: window.navigator, setTimeout, clearTimeout, Date, CustomEvent });
  vm.runInContext(fs.readFileSync(SOURCE, 'utf8'), context, { filename: SOURCE });
  window.FOREST_HOLD_CONFIG = { delayMs: 8, cancelDistance: 70 };
  return window;
}

test('short taps do not start recording', async () => {
  const window = loadHold(() => true);
  const button = new FakeElement();
  let starts = 0;
  let finishes = 0;
  window.bindForestHold(button, () => { starts += 1; }, () => { finishes += 1; });

  button.dispatchEvent(Object.assign(new Event('touchstart'), touchEvent(700)));
  window.dispatchEvent(Object.assign(new Event('touchend'), touchEvent(700)));
  await new Promise((resolve) => setTimeout(resolve, 15));

  assert.equal(starts, 0);
  assert.equal(finishes, 0);
});

test('long press vibrates once, records, and releases normally', async () => {
  let vibrations = 0;
  const window = loadHold(() => { vibrations += 1; return true; });
  const button = new FakeElement();
  let starts = 0;
  let finishValue = null;
  window.bindForestHold(button, () => { starts += 1; }, (cancel) => { finishValue = cancel; });

  button.dispatchEvent(Object.assign(new Event('touchstart'), touchEvent(700)));
  await new Promise((resolve) => setTimeout(resolve, 18));
  window.dispatchEvent(Object.assign(new Event('touchend'), touchEvent(700)));

  assert.equal(starts, 1);
  assert.equal(vibrations, 1);
  assert.equal(finishValue, false);
});

test('dragging upward arms cancellation and releasing cancels instead of sending', async () => {
  const window = loadHold(() => true);
  const button = new FakeElement();
  let finishValue = null;
  let sawCancel = false;
  window.addEventListener('forest:hold-progress', (event) => {
    if (event.detail.phase === 'moving' && event.detail.cancelled) sawCancel = true;
  });
  window.bindForestHold(button, () => {}, (cancel) => { finishValue = cancel; });

  button.dispatchEvent(Object.assign(new Event('touchstart'), touchEvent(700)));
  await new Promise((resolve) => setTimeout(resolve, 18));
  window.dispatchEvent(Object.assign(new Event('touchmove'), touchEvent(600)));
  window.dispatchEvent(Object.assign(new Event('touchend'), touchEvent(600)));

  assert.equal(sawCancel, true);
  assert.equal(button.classList.contains('cancel-armed'), false);
  assert.equal(finishValue, true);
});

test('pen long press starts once and release outside sends once', async () => {
  const window=loadHold(()=>true),button=new FakeElement();
  let starts=0,finishes=[];
  window.bindForestHold(button,()=>{starts++;},cancel=>finishes.push(cancel));
  const pen={pointerType:'pen',pointerId:7,button:0,clientY:600};
  button.dispatchEvent(Object.assign(new Event('pointerdown'),pen));
  await new Promise(resolve=>setTimeout(resolve,18));
  window.dispatchEvent(Object.assign(new Event('pointerup'),pen));
  button.dispatchEvent(Object.assign(new Event('pointerup'),pen));
  assert.equal(starts,1);assert.deepEqual(finishes,[false]);
});
