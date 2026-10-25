(function () {
  'use strict';
  // 2D 立绘角色：基于定妆图的 4 个姿势，用着色器做嘴部变形 + 交叉淡化
  var POSES = {
    idle:      '/assets/character_optimized/pose_idle.webp?v=20261025optimized1',
    talkRight: '/assets/character_optimized/pose_talk_right.webp?v=20261025optimized1',
    openBoth:  '/assets/character_optimized/pose_open_both.webp?v=20261025optimized1',
    think:     '/assets/character_optimized/pose_think.webp?v=20261025optimized1'
  };

  // 顶点着色器只移动嘴唇附近的少量网格，避免整块下巴或面颊被拉动。
  var VERT = [
    'uniform float u_jaw;',
    'uniform vec2 u_mouthPos;',   // uv 中心
    'uniform vec2 u_mouthR;',     // uv 椭圆半径
    'varying vec2 vUv;',
    'void main() {',
    '  vUv = uv;',
    '  vec3 pos = position;',
    '  vec2 mouth = (uv - u_mouthPos) / u_mouthR;',
    '  float dist = length(mouth);',
    '  if (dist < 1.0) {',
    '    float f = 1.0 - smoothstep(0.12, 1.0, dist);',
    '    pos.y -= u_jaw * f * 0.065;',
    '  }',
    '  gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);',
    '}'
  ].join('\n');

  var FRAG = [
    'uniform sampler2D u_map;',
    'uniform float u_opacity;',
    'uniform vec2 u_eyeL;',
    'uniform vec2 u_eyeR;',
    'uniform float u_blink;',
    'varying vec2 vUv;',
    'float eyeCover(vec2 uv, vec2 center, float blink) {',
    '  vec2 q = vec2((uv.x - center.x) / 0.034, (uv.y - center.y) / 0.031);',
    '  float inside = 1.0 - smoothstep(0.78, 1.0, length(q));',
    '  float boundary = mix(center.y + 0.029, center.y - 0.029, blink);',
    '  float descended = smoothstep(boundary - 0.0025, boundary + 0.0025, uv.y);',
    '  return inside * descended * smoothstep(0.0, 0.08, blink);',
    '}',
    'float eyeSeam(vec2 uv, vec2 center) {',
    '  vec2 q = vec2((uv.x - center.x) / 0.034, (uv.y - center.y) / 0.031);',
    '  float inside = 1.0 - smoothstep(0.78, 1.0, length(q));',
    '  float seamY = mix(center.y + 0.029, center.y - 0.010, u_blink);',
    '  seamY += 0.0025 * (1.0 - min(abs(q.x), 1.0));',
    '  return inside * (1.0 - smoothstep(0.0, 0.0016, abs(uv.y - seamY))) * smoothstep(0.15, 0.75, u_blink);',
    '}',
    'void main() {',
    '  vec4 c = texture2D(u_map, vUv);',
    '  float eyelid = max(eyeCover(vUv, u_eyeL, u_blink), eyeCover(vUv, u_eyeR, u_blink));',
    '  vec3 skinL = texture2D(u_map, u_eyeL - vec2(0.0, 0.052)).rgb;',
    '  vec3 skinR = texture2D(u_map, u_eyeR - vec2(0.0, 0.052)).rgb;',
    '  vec3 lidColor = mix(skinL, skinR, smoothstep(u_eyeL.x, u_eyeR.x, vUv.x));',
    '  float domeL = sqrt(max(0.0, 1.0 - length((vUv - u_eyeL) / vec2(0.034, 0.031))));',
    '  float domeR = sqrt(max(0.0, 1.0 - length((vUv - u_eyeR) / vec2(0.034, 0.031))));',
    '  float lidDome = mix(domeL, domeR, smoothstep(u_eyeL.x, u_eyeR.x, vUv.x));',
    '  lidColor *= 0.90 + 0.10 * lidDome;',
    '  c.rgb = mix(c.rgb, lidColor, eyelid);',
    '  float lidLine = max(eyeSeam(vUv, u_eyeL), eyeSeam(vUv, u_eyeR));',
    '  c.rgb = mix(c.rgb, vec3(0.30, 0.13, 0.08), lidLine * 0.68);',
    '  c.a *= u_opacity;',
    '  if (c.a < 0.02) discard;',
    '  gl_FragColor = c;',
    '}'
  ].join('\n');

  window.loadForestCharacter2D = function (THREE) {
    return new Promise(function (resolve, reject) {
      var loader = new THREE.TextureLoader();
      var textures = {};
      var keys = Object.keys(POSES);
      var failed = 0;
      var built = false;
      var secondaryStarted = false;

      function loadPose(key) {
        loader.load(POSES[key], function (tex) {
          tex.colorSpace = THREE.SRGBColorSpace;
          tex.anisotropy = 4;
          textures[key] = tex;
          if (!built) {
            built = true;
            build();
          }
          if (key === 'idle') loadSecondaryPoses();
        }, undefined, function (err) {
          console.warn('2d-character pose load fail', key, err);
          failed++;
          if (key === 'idle') loadSecondaryPoses();
          if (failed === keys.length && !built) {
            reject(new Error('All poses failed to load'));
          }
        });
      }

      function loadSecondaryPoses() {
        if (secondaryStarted) return;
        secondaryStarted = true;
        keys.forEach(function (key) {
          if (key !== 'idle') loadPose(key);
        });
      }

      loadPose('idle');

      function build() {
        var group = new THREE.Group();
        var W = 5.0, H = 7.5;
        var geo = new THREE.PlaneGeometry(W, H, 48, 72);
        var mouthPos = new THREE.Vector2(0.5, 0.779);
        var mouthR = new THREE.Vector2(0.052, 0.027);
        var eyeL = new THREE.Vector2(0.438, 0.827);
        var eyeR = new THREE.Vector2(0.545, 0.827);
        var BASE_Y = 2.0;

        // 角色基础位置固定在场景中，呼吸和摆动只在 update() 中叠加。
        group.position.y = BASE_Y;
        group.scale.set(0.5, 0.5, 0.5);

        var initialKey = textures.idle ? 'idle' : keys.filter(function (key) {
          return !!textures[key];
        })[0];
        var material = new THREE.ShaderMaterial({
          uniforms: {
            u_map: { value: textures[initialKey] },
            u_jaw: { value: 0 },
            u_opacity: { value: 1 },
            u_mouthPos: { value: mouthPos },
            u_mouthR: { value: mouthR },
            u_eyeL: { value: eyeL },
            u_eyeR: { value: eyeR },
            u_blink: { value: 0 }
          },
          vertexShader: VERT,
          fragmentShader: FRAG,
          transparent: true,
          depthWrite: false
        });
        var mesh = new THREE.Mesh(geo, material);
        mesh.renderOrder = 1;
        group.add(mesh);

        // 状态
        var target = 'idle';
        var visiblePose = initialKey;
        var gestureTimer = 0;
        var jawLevel = 0;
        var breathPhase = 0;
        var lastState = '';

        // 眼睛随姿态图缩放，不额外覆盖黑色横条。
        // 状态机按秒推进：闭合 90ms、停留 60ms、睁开 135ms。
        var blinkPhase = 'open';
        var blinkElapsed = 0;
        var blinkProgress = 0;
        var blinkDelay = 2.2;

        var api = {
          root: group,
          update: function (state, t, reduced, deltaSeconds) {
            var dt = Number(deltaSeconds);
            if (!isFinite(dt) || dt < 0) dt = 0;
            dt = Math.min(dt, 0.05);
            var level = (state === 'speaking' && window.forestSpeechLevel) ? window.forestSpeechLevel() : 0;
            level = Math.max(0, Math.min(1, level));

            // 状态切换时重置手势计时器
            if (state !== lastState) {
              lastState = state;
              gestureTimer = 0;
            }

            // 姿势选择
            if (state === 'speaking') {
              gestureTimer -= dt;
              if (gestureTimer <= 0) {
                var choices = ['talkRight', 'openBoth', 'idle', 'talkRight', 'openBoth'];
                target = choices[Math.floor(Math.random() * choices.length)];
                gestureTimer = reduced ? 3.5 + Math.random() * 2.5 : 2.2 + Math.random() * 2.0;
              }
            } else if (state === 'thinking') {
              target = 'think';
            } else {
              target = 'idle';
            }

            // 四张图五官与画布已对齐，单网格直接换贴图可杜绝整身重影。
            if (target !== visiblePose && textures[target]) {
              visiblePose = target;
              material.uniforms.u_map.value = textures[target];
            }

            // 嘴型（快开慢合）
            if (state === 'speaking') {
              var jawRate = level > jawLevel ? 22 : 40;
              jawLevel += (level - jawLevel) * (1 - Math.exp(-jawRate * dt));
              if (jawLevel < 0.012) jawLevel = 0;
            } else {
              jawLevel = 0;
            }
            var jawScale = reduced ? 0.6 : 1.0;
            material.uniforms.u_jaw.value = jawLevel * jawScale;

            // 呼吸
            breathPhase += dt * 1.5;
            var breath = Math.sin(breathPhase) * (reduced ? 0.012 : 0.02);
            group.position.y = BASE_Y + breath;
            var motionScale = reduced ? 0.25 : 1;
            group.rotation.z = Math.sin(breathPhase * 0.5) * 0.008 * motionScale;

            // 2D 角色只做很小幅度的自然摆动，rotation.y 仅由本模块控制。
            var sway = state === 'speaking'
              ? Math.sin(t * 2.2) * 0.045 + Math.sin(t * 5.0) * 0.01
              : Math.sin(t * 0.6) * 0.02;
            group.rotation.y = sway * motionScale;

            // 眨眼由跨帧状态机推进；着色器只在眼睛椭圆内绘制与肤色一致的上下眼睑。
            blinkElapsed += dt;
            if (blinkPhase === 'open') {
              blinkDelay -= dt;
              if (blinkDelay <= 0) {
                blinkPhase = 'closing';
                blinkElapsed = 0;
              }
            } else if (blinkPhase === 'closing') {
              blinkProgress = Math.min(1, blinkElapsed / 0.09);
              if (blinkElapsed >= 0.09) {
                blinkPhase = 'closed';
                blinkElapsed = 0;
                blinkProgress = 1;
              }
            } else if (blinkPhase === 'closed') {
              blinkProgress = 1;
              if (blinkElapsed >= 0.06) {
                blinkPhase = 'opening';
                blinkElapsed = 0;
              }
            } else {
              blinkProgress = Math.max(0, 1 - blinkElapsed / 0.135);
              if (blinkElapsed >= 0.135) {
                blinkPhase = 'open';
                blinkElapsed = 0;
                blinkProgress = 0;
                blinkDelay = 2.8 + Math.random() * 3.2;
              }
            }
            var easedBlink = blinkProgress * blinkProgress * (3 - 2 * blinkProgress);
            material.uniforms.u_blink.value = easedBlink;
          },
          animationState: function () {
            return {
              target: target,
              visiblePose: visiblePose,
              blinkPhase: blinkPhase,
              blinkProgress: blinkProgress,
              blinkDelay: blinkDelay,
              blinkElapsed: blinkElapsed,
              jawLevel: jawLevel,
              baseY: BASE_Y
            };
          },
          triggerBlink: function () {
            if (blinkPhase !== 'open') return false;
            blinkPhase = 'closing';
            blinkElapsed = 0;
            blinkProgress = 0;
            return true;
          }
        };
        resolve(api);
      }
    });
  };
})();
