(function () {
  'use strict';
  // 六姿势2D角色：共享原始面部，嘴型按原图唇线标定，动作缓动衔接。
  var POSES = {
    idle:      '/assets/character_optimized/pose_idle.webp?v=20261025optimized1',
    talkRight: '/assets/character_optimized/pose_talk_right.webp?v=20261025optimized1',
    openBoth:  '/assets/character_optimized/pose_open_both.webp?v=20261025optimized1',
    think:     '/assets/character_optimized/pose_think.webp?v=20261025optimized1',
    listen:    '/assets/character_optimized/pose_listen.webp?v=20261025mouth4',
    point:     '/assets/character_optimized/pose_point.webp?v=20261025mouth4'
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
    '    pos.y -= u_jaw * f * 0.018;',
    '  }',
    '  gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);',
    '}'
  ].join('\n');

  var FRAG = [
    'uniform sampler2D u_map;',
    'uniform sampler2D u_nextMap;',
    'uniform sampler2D u_faceMap;',
    'uniform float u_transition;',
    'uniform float u_opacity;',
    'uniform vec2 u_eyeL;',
    'uniform vec2 u_eyeR;',
    'uniform vec2 u_mouthPos;',
    'uniform vec2 u_mouthR;',
    'uniform float u_jaw;',
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
    // Premultiplied interpolation on one mesh prevents dark alpha fringes.
    // The face is shared across poses, so glasses and mouth never ghost.
    '  vec4 oldPose = texture2D(u_map, vUv);',
    '  vec4 nextPose = texture2D(u_nextMap, vUv);',
    '  float alpha = mix(oldPose.a, nextPose.a, u_transition);',
    '  vec3 body = mix(oldPose.rgb * oldPose.a, nextPose.rgb * nextPose.a, u_transition) / max(alpha, 0.001);',
    '  vec4 face = texture2D(u_faceMap, vUv);',
    '  float sharedFace = smoothstep(0.735, 0.756, vUv.y) * smoothstep(0.04, 0.15, face.a);',
    '  vec4 c = mix(vec4(body, alpha), face, sharedFace);',
    '  float eyelid = max(eyeCover(vUv, u_eyeL, u_blink), eyeCover(vUv, u_eyeR, u_blink));',
    '  vec3 skinL = texture2D(u_faceMap, u_eyeL - vec2(0.0, 0.052)).rgb;',
    '  vec3 skinR = texture2D(u_faceMap, u_eyeR - vec2(0.0, 0.052)).rgb;',
    '  vec3 lidColor = mix(skinL, skinR, smoothstep(u_eyeL.x, u_eyeR.x, vUv.x));',
    '  float domeL = sqrt(max(0.0, 1.0 - length((vUv - u_eyeL) / vec2(0.034, 0.031))));',
    '  float domeR = sqrt(max(0.0, 1.0 - length((vUv - u_eyeR) / vec2(0.034, 0.031))));',
    '  float lidDome = mix(domeL, domeR, smoothstep(u_eyeL.x, u_eyeR.x, vUv.x));',
    '  lidColor *= 0.90 + 0.10 * lidDome;',
    '  c.rgb = mix(c.rgb, lidColor, eyelid);',
    '  float lidLine = max(eyeSeam(vUv, u_eyeL), eyeSeam(vUv, u_eyeR));',
    '  c.rgb = mix(c.rgb, vec3(0.30, 0.13, 0.08), lidLine * 0.68);',
    // A bounded curved aperture, not a darkened smile line. All dimensions are UV units.
    '  float opening = smoothstep(0.025, 0.9, u_jaw);',
    '  float dx = vUv.x - u_mouthPos.x;',
    '  float nx = dx / mix(0.031, 0.036, opening);',
    '  float arch = sqrt(max(0.0, 1.0 - nx * nx));',
    '  float seam = u_mouthPos.y + dx * 0.136315 + 2.845063 * dx * dx;',
    '  float upper = seam + 0.0035 * arch * opening;',
    '  float lower = seam - 0.0145 * arch * opening;',
    '  float horizontal = 1.0 - smoothstep(0.95, 1.025, abs(nx));',
    '  float oralCavity = horizontal * smoothstep(lower - 0.0008, lower + 0.001, vUv.y) * (1.0 - smoothstep(upper - 0.0008, upper + 0.001, vUv.y)) * smoothstep(0.01, 0.12, opening);',
    '  float depth = clamp((vUv.y - lower) / max(upper - lower, 0.001), 0.0, 1.0);',
    '  vec3 inside = mix(vec3(0.27, 0.075, 0.07), vec3(0.095, 0.025, 0.027), depth);',
    '  float upperTeeth = smoothstep(0.77, 0.82, depth) * (1.0 - smoothstep(0.94, 0.99, depth)) * (1.0 - smoothstep(0.78, 0.98, abs(nx)));',
    '  float toothGroove = pow(abs(sin((nx + 1.0) * 19.0)), 28.0) * 0.05;',
    '  vec3 enamel = mix(vec3(0.73, 0.66, 0.55), vec3(0.99, 0.95, 0.85), depth) - toothGroove;',
    '  inside = mix(inside, enamel, upperTeeth * smoothstep(0.1, 0.4, opening));',
    '  float tongue = (1.0 - smoothstep(0.22, 0.43, depth)) * (1.0 - smoothstep(0.35, 0.85, abs(nx)));',
    '  inside = mix(inside, vec3(0.67, 0.25, 0.27), tongue * 0.85);',
    '  float lowerLip = horizontal * (1.0 - smoothstep(0.0007, 0.0028, abs(vUv.y - lower))) * opening;',
    '  vec3 lipSkin = texture2D(u_faceMap, vec2(vUv.x, seam - 0.012)).rgb;',
    '  c.rgb = mix(c.rgb, lipSkin * vec3(1.03, 0.86, 0.83), lowerLip * 0.75);',
    '  c.rgb = mix(c.rgb, inside, oralCavity);',
    '  c.a *= u_opacity;',
    '  if (c.a < 0.02) discard;',
    '  gl_FragColor = c;',
    '  #include <tonemapping_fragment>',
    '  #include <colorspace_fragment>',
    '}'
  ].join('\n');

  window.loadForestCharacter2D = function (THREE) {
    return new Promise(function (resolve, reject) {
      var loader = new THREE.TextureLoader();
      if (loader.setCrossOrigin) loader.setCrossOrigin('anonymous');
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
        // Original 1672x2508 portrait lip pixels were measured and fitted:
        // y(UV)=.783728+.136315*dx+2.845063*dx^2. Never place an extra mouth below it.
        var mouthPos = new THREE.Vector2(0.5, 0.783728);
        var mouthR = new THREE.Vector2(0.049, 0.023);
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
            u_nextMap: { value: textures[initialKey] },
            u_faceMap: { value: textures.idle || textures[initialKey] },
            u_transition: { value: 1 },
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
        var transition = 1, transitionTo = initialKey, gestureIndex = 0, forcedPose = null;

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
                var choices = ['talkRight', 'idle', 'point', 'idle', 'openBoth', 'idle'];
                target = choices[gestureIndex++ % choices.length];
                gestureTimer = reduced ? 5.5 : 3.5;
              }
            } else if (state === 'thinking') {
              target = 'think';
            } else if (state === 'listening') {
              target = 'listen';
            } else {
              target = 'idle';
            }
            if (forcedPose && textures[forcedPose]) target = forcedPose;

            // A 480ms eased change, sharing a single face, with a resting pose
            // between large gestures. Finish an in-flight transition before the next.
            if (transition === 1 && target !== visiblePose && textures[target]) {
              transitionTo = target;
              material.uniforms.u_nextMap.value = textures[target];
              transition = 0;
            }
            if (transition < 1) {
              transition = Math.min(1, transition + dt / (reduced ? 0.18 : 0.48));
              material.uniforms.u_transition.value = transition * transition * (3 - 2 * transition);
              if (transition === 1) {
                visiblePose = transitionTo;
                material.uniforms.u_map.value = textures[visiblePose];
              }
            }

            // 嘴型（快开慢合）
            if (state === 'speaking') {
              var jawRate = level > jawLevel ? 26 : 18;
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
          setPose: function (pose) { forcedPose = keys.indexOf(pose) >= 0 ? pose : null; },
          animationState: function () {
            return {
              target: target,
              visiblePose: visiblePose,
              blinkPhase: blinkPhase,
              blinkProgress: blinkProgress,
              blinkDelay: blinkDelay,
              blinkElapsed: blinkElapsed,
              jawLevel: jawLevel,
              transition: transition,
              poses: keys.slice(),
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
