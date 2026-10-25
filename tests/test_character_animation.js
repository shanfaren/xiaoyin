'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const ROOT = path.resolve(__dirname, '..');
const CHARACTER_PATH = path.join(ROOT, 'web', '2d-character.js');
const COMPANION_PATH = path.join(ROOT, 'web', 'companion.js');

function vector3() {
  return {
    x: 0,
    y: 0,
    z: 0,
    set(x, y, z) {
      this.x = x;
      this.y = y;
      this.z = z;
    }
  };
}

function createThreeStub(TextureLoaderOverride) {
  class Group {
    constructor() {
      this.children = [];
      this.position = vector3();
      this.rotation = vector3();
      this.scale = vector3();
      this.scale.set(1, 1, 1);
    }

    add(child) {
      this.children.push(child);
    }
  }

  class Mesh {
    constructor(geometry, material) {
      this.geometry = geometry;
      this.material = material;
      this.position = vector3();
      this.rotation = vector3();
      this.scale = vector3();
      this.scale.set(1, 1, 1);
    }
  }

  class ShaderMaterial {
    constructor(options) {
      Object.assign(this, options);
      this.uniforms = options.uniforms;
    }
  }

  class BasicMaterial {
    constructor(options) {
      Object.assign(this, options);
    }

    clone() {
      return new BasicMaterial(this);
    }
  }

  class TextureLoader {
    load(_url, onLoad) {
      onLoad({ colorSpace: null, anisotropy: 0 });
    }
  }

  return {
    SRGBColorSpace: 'srgb',
    Group,
    Mesh,
    PlaneGeometry: class PlaneGeometry {},
    ShaderMaterial,
    MeshBasicMaterial: BasicMaterial,
    TextureLoader: TextureLoaderOverride || TextureLoader,
    Vector2: class Vector2 {
      constructor(x, y) {
        this.x = x;
        this.y = y;
      }
    }
  };
}

async function createCharacter(TextureLoaderOverride) {
  const source = fs.readFileSync(CHARACTER_PATH, 'utf8');
  const deterministicMath = Object.create(Math);
  deterministicMath.random = () => 0.45;
  const window = {
    forestSpeechLevel: () => 0
  };
  const context = vm.createContext({
    window,
    console: { warn() {} },
    Math: deterministicMath
  });
  vm.runInContext(source, context, { filename: CHARACTER_PATH });
  return window.loadForestCharacter2D(createThreeStub(TextureLoaderOverride));
}

function blinkUniforms(character) {
  return character.root.children
    .filter((child) => child && child.material && child.material.uniforms)
    .map((child) => child.material.uniforms.u_blink)
    .filter(Boolean)
    .map((uniform) => uniform.value);
}

test('breathing adds a small offset to the authored base height', async () => {
  const character = await createCharacter();

  assert.ok(Math.abs(character.root.position.y - 2) < 0.001, 'initial role height should match the stage framing');
  character.update('idle', 0, false, 1 / 60);
  assert.ok(
    Math.abs(character.root.position.y - 2) <= 0.021,
    `breathing moved the role from its base height: y=${character.root.position.y}`
  );
});

test('blink state completes closing, a brief hold, opening, and returns to open', async () => {
  const character = await createCharacter();
  const samples = [];

  for (let i = 0; i < 210; i += 1) {
    character.update('idle', i / 60, false, 1 / 60);
    samples.push(...blinkUniforms(character));
  }

  assert.ok(Math.max(...samples, 0) >= 0.9, 'blink never reached a fully closed eyelid state');
  const finalValues = blinkUniforms(character);
  assert.ok(finalValues.length > 0, 'eyelid state uniform is missing');
  assert.ok(
    finalValues.every((value) => value <= 0.02),
    `blink did not return to open eyes: ${JSON.stringify(finalValues)}`
  );
});

test('character owns the only horizontal rotation authority', () => {
  const companionSource = fs.readFileSync(COMPANION_PATH, 'utf8');
  assert.doesNotMatch(
    companionSource,
    /character\.root\.rotation\.y\s*=/,
    'companion.js writes rotation.y after character.update and can overwrite the animation'
  );
});

test('pose changes use one aligned mesh so two full-body images cannot overlap', async () => {
  const character = await createCharacter();
  const poseMeshes = character.root.children.filter((child) => child.material && child.material.uniforms);

  assert.equal(poseMeshes.length, 1, 'more than one full-body pose mesh is renderable');
  const idleTexture = poseMeshes[0].material.uniforms.u_map.value;
  character.update('thinking', 0, false, 1 / 30);
  for (let i=1;i<20;i++) character.update('thinking', i/30, false, 1/30);
  const thinkTexture = poseMeshes[0].material.uniforms.u_map.value;
  assert.notEqual(thinkTexture, idleTexture, 'thinking pose did not replace the texture');
  assert.equal(poseMeshes[0].material.uniforms.u_opacity.value, 1);
});

test('idle pose resolves the character before slower alternate poses finish', async () => {
  const pending = {};
  class DeferredTextureLoader {
    load(url, onLoad) {
      pending[url] = onLoad;
    }
  }

  const loading = createCharacter(DeferredTextureLoader);
  await Promise.resolve();
  assert.ok(Object.keys(pending).some((url) => /pose_idle/.test(url)), 'idle pose request was not started');
  assert.equal(Object.keys(pending).length, 1, 'alternate poses block the first render');

  pending[Object.keys(pending)[0]]({ colorSpace: null, anisotropy: 0 });
  const result = await Promise.race([
    loading.then(() => 'ready'),
    new Promise((resolve) => setTimeout(() => resolve('timeout'), 40))
  ]);
  assert.equal(result, 'ready');
});

test('animation speed is based on elapsed time rather than render rate', async () => {
  const fast = await createCharacter();
  const slow = await createCharacter();

  for (let i = 1; i <= 60; i += 1) {
    fast.update('idle', i / 60, false, 1 / 60);
  }
  for (let i = 1; i <= 20; i += 1) {
    slow.update('idle', i / 20, false, 1 / 20);
  }

  assert.ok(
    Math.abs(fast.root.position.y - slow.root.position.y) <= 0.002,
    `frame rate changed breathing position: 60fps=${fast.root.position.y}, 20fps=${slow.root.position.y}`
  );
});

test('speech opens an oral cavity with teeth and tongue, and silence closes it', async () => {
  const source = fs.readFileSync(CHARACTER_PATH, 'utf8');
  const context = vm.createContext({window: {forestSpeechLevel: () => 0.8}, console, Math});
  vm.runInContext(source, context);
  const role = await context.window.loadForestCharacter2D(createThreeStub());
  role.update('speaking', 1, false, 0.05);
  const mat = role.root.children[0].material;
  assert.ok(mat.uniforms.u_jaw.value > 0.5);
  assert.match(mat.fragmentShader, /upperTeeth/);
  assert.match(mat.fragmentShader, /tongue/);
  assert.match(mat.fragmentShader, /oralCavity/);
  context.window.forestSpeechLevel = () => 0;
  for (let i=0;i<20;i++) role.update('speaking',1+i/30,false,1/30);
  assert.equal(mat.uniforms.u_jaw.value, 0);
});

test('pose changes interpolate over time rather than cutting the texture', async () => {
  const role = await createCharacter();
  role.update('thinking', 1, false, 0.05);
  const first = role.animationState();
  assert.ok(first.transition > 0 && first.transition < 1);
  for (let i=0;i<20;i++)role.update('thinking',1+i/30,false,1/30);
  assert.equal(role.animationState().visiblePose, 'think');
  assert.equal(role.animationState().transition, 1);
});

test('mouth aperture follows the original image lip seam within 2.5 pixels', async () => {
  const role = await createCharacter();
  const u = role.root.children[0].material.uniforms;
  // Measured dark lip pixels from the 1672 x 2508 original, independent of shader.
  const landmarks = [[787,545],[799,547],[823,545],[835,542],[859,536],[883,528]];
  for (const [x,y] of landmarks) {
    const dx=x/1672-u.u_mouthPos.value.x;
    const predicted=u.u_mouthPos.value.y+dx*0.136315+2.845063*dx*dx;
    assert.ok(Math.abs((1-predicted)*2508-y)<2.5, `lip seam is displaced at original pixel ${x},${y}`);
  }
});
