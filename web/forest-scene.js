/* Procedural 3D forest environment for the forest doctor.
   Low-dependency: built only from three.js primitives + a canvas sky,
   optimized for mobile (InstancedMesh draw calls, capped particle counts,
   cheap flat-shaded materials). Exposes an update(t, state, level) that
   makes the woods breathe with the character (drifting pollen, falling
   leaves, butterflies, light shafts brightening while the doctor speaks). */
(function (root) {
  'use strict';

  function createForestScene(THREE, scene) {
    var T = THREE;

    // Deterministic PRNG so the layout is stable between loads.
    var seed = 20261022;
    function rnd() { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; }
    function rr(a, b) { return a + rnd() * (b - a); }

    /* ---------- Sky (vertical gradient canvas, warm sun glow) ---------- */
    var skyC = document.createElement('canvas'); skyC.width = 8; skyC.height = 256;
    var sx = skyC.getContext('2d');
    var g = sx.createLinearGradient(0, 0, 0, 256);
    g.addColorStop(0.00, '#86c4e6');
    g.addColorStop(0.40, '#c6e6ef');
    g.addColorStop(0.60, '#e6f3d4');
    g.addColorStop(0.78, '#f2f7dd');
    g.addColorStop(1.00, '#f6fae6');
    sx.fillStyle = g; sx.fillRect(0, 0, 8, 256);
    var rg = sx.createRadialGradient(2, 96, 4, 2, 96, 150);
    rg.addColorStop(0, 'rgba(255,246,210,0.9)');
    rg.addColorStop(0.35, 'rgba(255,242,198,0.28)');
    rg.addColorStop(1, 'rgba(255,242,198,0)');
    sx.fillStyle = rg; sx.fillRect(0, 0, 8, 256);
    var skyTex = new T.CanvasTexture(skyC); skyTex.colorSpace = T.SRGBColorSpace;
    scene.background = skyTex;
    scene.fog = new T.Fog(0xd8eec5, 12, 30);

    /* ---------- Ground ---------- */
    var ground = new T.Mesh(
      new T.CircleGeometry(26, 56),
      new T.MeshStandardMaterial({ color: 0x7fb15b, roughness: 1 })
    );
    ground.rotation.x = -Math.PI / 2; ground.position.y = -0.02; ground.receiveShadow = true;
    scene.add(ground);
    // Soft darker clearing ring around the doctor so the feet read clearly.
    var clearing = new T.Mesh(
      new T.CircleGeometry(2.4, 40),
      new T.MeshStandardMaterial({ color: 0x8fc367, roughness: 1 })
    );
    clearing.rotation.x = -Math.PI / 2; clearing.position.y = -0.012; clearing.receiveShadow = true;
    scene.add(clearing);

    var dummy = new T.Object3D();
    function setInst(mesh, i, x, y, z, sx, sy, sz, ry) {
      dummy.position.set(x, y, z);
      dummy.rotation.set(0, ry || 0, 0);
      dummy.scale.set(sx, sy, sz);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    }

    /* ---------- Trees (instanced trunks + clustered canopy) ---------- */
    var trees = [];
    for (var i = 0; i < 9; i++) {
      var ang = (-78 + i * 19.5) * Math.PI / 180; // arc across the back
      var r = rr(6.6, 10.8);
      trees.push({ x: Math.sin(ang) * r, z: -Math.cos(ang) * r, h: rr(2.0, 3.3), s: rr(0.85, 1.25) });
    }
    // Two framing trees on the near sides.
    trees.push({ x: 4.7, z: 0.6, h: 3.4, s: 1.45 });
    trees.push({ x: -4.7, z: 0.6, h: 3.4, s: 1.45 });

    var trunkGeo = new T.CylinderGeometry(0.1, 0.17, 1, 6);
    var trunkMat = new T.MeshStandardMaterial({ color: 0x8a6a48, roughness: 1, flatShading: true });
    var trunks = new T.InstancedMesh(trunkGeo, trunkMat, trees.length);
    var leafGeo = new T.IcosahedronGeometry(1, 1);
    var leafMat = new T.MeshStandardMaterial({ color: 0xffffff, roughness: 1, flatShading: true });
    var puffs = 3;
    var leaves = new T.InstancedMesh(leafGeo, leafMat, trees.length * puffs);
    var leafCols = [0x57a24c, 0x67b557, 0x4d8f45, 0x74c066];
    var li = 0;
    for (var ti = 0; ti < trees.length; ti++) {
      var tr = trees[ti], h = tr.h, s = tr.s;
      setInst(trunks, ti, tr.x, h * 0.5 * s, tr.z, s, h * s, s);
      // three clustered puffs per tree
      var baseY = h * s;
      var c1 = rr(1.05, 1.5) * s;
      setInst(leaves, li++, tr.x, baseY + 0.35 * s, tr.z, c1 * 1.05, c1 * 0.92, c1 * 1.05, rr(0, 6));
      var c2 = rr(0.8, 1.15) * s;
      setInst(leaves, li++, tr.x + rr(-0.5, 0.5) * s, baseY + 1.0 * s, tr.z + rr(-0.4, 0.4) * s, c2, c2 * 0.95, c2, rr(0, 6));
      var c3 = rr(0.7, 1.0) * s;
      setInst(leaves, li++, tr.x + rr(-0.4, 0.4) * s, baseY + 0.1 * s, tr.z + rr(-0.5, 0.5) * s, c3, c3 * 0.9, c3, rr(0, 6));
    }
    for (var pc = 0; pc < leaves.count; pc++) {
      var col = new T.Color(leafCols[Math.floor(rnd() * leafCols.length)]);
      col.offsetHSL(rr(-0.02, 0.02), rr(-0.05, 0.05), rr(-0.04, 0.06));
      leaves.setColorAt(pc, col);
    }
    leaves.instanceColor.needsUpdate = true;
    leaves.castShadow = false; trunks.castShadow = false;
    scene.add(trunks); scene.add(leaves);

    /* ---------- Distant hills (soft, foggy) ---------- */
    var hillMat = new T.MeshStandardMaterial({ color: 0xa6bcc6, roughness: 1, flatShading: true });
    var hills = [
      { x: -9, z: -17, rad: 7, h: 6 },
      { x: 2, z: -19, rad: 9, h: 7.5 },
      { x: 11, z: -16, rad: 6.5, h: 5.5 }
    ];
    hills.forEach(function (hh) {
      var m = new T.Mesh(new T.ConeGeometry(hh.rad, hh.h, 6), hillMat);
      m.position.set(hh.x, hh.h / 2 - 1.6, hh.z);
      m.rotation.y = rr(0, 3);
      scene.add(m);
    });

    /* ---------- Bushes (instanced) ---------- */
    var bushN = 16;
    var bushes = new T.InstancedMesh(
      new T.DodecahedronGeometry(0.55, 0),
      new T.MeshStandardMaterial({ color: 0xffffff, roughness: 1, flatShading: true }), bushN);
    for (var bi = 0; bi < bushN; bi++) {
      var ba = rr(0, Math.PI * 2), br = rr(3.2, 9.5);
      var bx = Math.cos(ba) * br, bz = Math.sin(ba) * br - 1.5;
      var bs = rr(0.6, 1.3);
      setInst(bushes, bi, bx, 0.35 * bs, bz, bs * 1.3, bs * 0.9, bs * 1.3, rr(0, 6));
      var bc = new T.Color([0x5fa352, 0x6bb05b, 0x569a4c][Math.floor(rnd() * 3)]);
      bushes.setColorAt(bi, bc);
    }
    bushes.instanceColor.needsUpdate = true;
    scene.add(bushes);

    /* ---------- Grass blades (crossed quads, instanced) ---------- */
    var grassN = 170;
    var bladeGeo = new T.BufferGeometry();
    var bv = new Float32Array([
      0, 0, 0, -0.045, 0, 0.001, 0, 0.32, 0,
      0, 0, 0, 0.045, 0, 0.001, 0, 0.32, 0
    ]);
    bladeGeo.setAttribute('position', new T.BufferAttribute(bv, 3));
    bladeGeo.computeVertexNormals();
    var grassMat = new T.MeshStandardMaterial({ color: 0x86c064, roughness: 1, side: T.DoubleSide });
    var grass = new T.InstancedMesh(bladeGeo, grassMat, grassN);
    for (var gi = 0; gi < grassN; gi++) {
      var ga = rr(0, Math.PI * 2), gr = rr(1.2, 7.5);
      setInst(grass, gi, Math.cos(ga) * gr, 0, Math.sin(ga) * gr - 0.5, rr(0.7, 1.5), rr(0.7, 1.7), 1, rr(0, Math.PI));
    }
    scene.add(grass);

    /* ---------- Flowers (colored buds, instanced) ---------- */
    var flowerN = 26;
    var flowers = new T.InstancedMesh(
      new T.IcosahedronGeometry(0.09, 0),
      new T.MeshStandardMaterial({ color: 0xffffff, roughness: 0.8 }), flowerN);
    var fcols = [0xffd6e6, 0xffe98a, 0xc9a7ff, 0xffb3b3, 0xffffff, 0xffc07a];
    for (var fi = 0; fi < flowerN; fi++) {
      var fa = rr(0, Math.PI * 2), fr = rr(1.4, 6.5);
      setInst(flowers, fi, Math.cos(fa) * fr, 0.16, Math.sin(fa) * fr - 0.4, 1, 1, 1, 0);
      flowers.setColorAt(fi, new T.Color(fcols[Math.floor(rnd() * fcols.length)]));
    }
    flowers.instanceColor.needsUpdate = true;
    scene.add(flowers);

    /* ---------- Mushrooms (white stems + red caps, instanced) ---------- */
    var mushN = 12;
    var stems = new T.InstancedMesh(
      new T.CylinderGeometry(0.035, 0.05, 0.22, 6),
      new T.MeshStandardMaterial({ color: 0xf3e7d3, roughness: 1 }), mushN);
    var caps = new T.InstancedMesh(
      new T.SphereGeometry(0.14, 8, 6, 0, Math.PI * 2, 0, Math.PI / 2),
      new T.MeshStandardMaterial({ color: 0xe76553, roughness: 0.9, flatShading: true }), mushN);
    for (var mi = 0; mi < mushN; mi++) {
      var ma = rr(0, Math.PI * 2), mr = rr(1.6, 5.5);
      var mx = Math.cos(ma) * mr, mz = Math.sin(ma) * mr - 0.3;
      setInst(stems, mi, mx, 0.11, mz, 1, 1, 1, 0);
      setInst(caps, mi, mx, 0.22, mz, 1, 0.85, 1, 0);
    }
    scene.add(stems); scene.add(caps);

    /* ---------- Light shafts (additive, breathe with speech) ---------- */
    var shafts = [];
    var shaftDefs = [
      { x: -1.6, z: -4.5, rz: 0.18 },
      { x: 1.8, z: -5.5, rz: -0.12 },
      { x: 0.4, z: -7.2, rz: 0.06 }
    ];
    shaftDefs.forEach(function (sd) {
      var mat = new T.MeshBasicMaterial({
        color: 0xfff3bd, transparent: true, opacity: 0.05,
        blending: T.AdditiveBlending, depthWrite: false, side: T.DoubleSide
      });
      var m = new T.Mesh(new T.CylinderGeometry(0.22, 0.9, 6.2, 12, 1, true), mat);
      m.position.set(sd.x, 4.9, sd.z); m.rotation.z = sd.rz;
      scene.add(m);
      shafts.push(m);
    });

    /* ---------- Pollen points (gold, drifting upward) ---------- */
    function makePoints(n, color, size, area) {
      var pos = new Float32Array(n * 3), ph = new Float32Array(n);
      for (var k = 0; k < n; k++) {
        pos[k * 3] = rr(-area.x, area.x);
        pos[k * 3 + 1] = rr(area.y0, area.y1);
        pos[k * 3 + 2] = rr(area.z0, area.z1);
        ph[k] = rr(0, Math.PI * 2);
      }
      var geo = new T.BufferGeometry();
      geo.setAttribute('position', new T.BufferAttribute(pos, 3));
      var mat = new T.PointsMaterial({
        color: color, size: size, transparent: true, opacity: 0.85,
        depthWrite: false, blending: T.AdditiveBlending
      });
      var pts = new T.Points(geo, mat);
      scene.add(pts);
      return { pts: pts, ph: ph, n: n };
    }
    var pollen = makePoints(90, 0xfff0b0, 0.07, { x: 5, y0: 0.4, y1: 5.6, z0: -4, z1: 3 });
    var leavesFall = makePoints(60, 0xe5944a, 0.11, { x: 6, y0: 0.5, y1: 6.2, z0: -5, z1: 2 });

    /* ---------- Butterflies (flapping wings on drifting paths) ---------- */
    function makeButterfly(color, bx, by, bz, speed) {
      var grp = new T.Group();
      var wMat = new T.MeshBasicMaterial({ color: color, side: T.DoubleSide, transparent: true, opacity: 0.95 });
      // Each wing is a half-disc whose straight edge sits on the body (x=0),
      // so rotating it around Y flaps the wings about the body axis.
      var lw = new T.Mesh(new T.CircleGeometry(0.19, 14, Math.PI / 2, Math.PI), wMat);
      var rw = new T.Mesh(new T.CircleGeometry(0.19, 14, -Math.PI / 2, Math.PI), wMat);
      lw.scale.set(1.05, 1.25, 1); rw.scale.set(1.05, 1.25, 1);
      var body = new T.Mesh(new T.CylinderGeometry(0.014, 0.014, 0.2, 6),
        new T.MeshBasicMaterial({ color: 0x4a3624 }));
      grp.add(lw, rw, body);
      grp.position.set(bx, by, bz);
      scene.add(grp);
      return { g: grp, lw: lw, rw: rw, bx: bx, by: by, bz: bz, speed: speed, p: rr(0, 6.28) };
    }
    var butterflies = [
      makeButterfly(0xff9ed0, 1.7, 2.7, 1.7, 1),
      makeButterfly(0xffd98a, -1.7, 3.0, 1.3, 0.8)
    ];

    /* ---------- Per-frame update ---------- */
    var clock = 0;
    function update(t, state, level) {
      var act = state === 'speaking' ? 1 : state === 'listening' ? 0.55 : state === 'thinking' ? 0.4 : 0.75;
      var dt = clock ? Math.min(0.05, t - clock) : 0.016; clock = t;
      var lv = Math.max(0, level || 0);

      // Pollen drifts upward + sways; faster while speaking.
      var pp = pollen.pts.geometry.attributes.position.array;
      var pv = dt * (0.12 + 0.22 * act);
      for (var i = 0; i < pollen.n; i++) {
        pp[i * 3 + 1] += pv;
        pp[i * 3] += Math.sin(t * 0.8 + pollen.ph[i]) * dt * 0.18;
        pp[i * 3 + 2] += Math.cos(t * 0.6 + pollen.ph[i]) * dt * 0.12;
        if (pp[i * 3 + 1] > 5.8) { pp[i * 3 + 1] = 0.3; }
      }
      pollen.pts.geometry.attributes.position.needsUpdate = true;

      // Leaves drift down + sway.
      var lp = leavesFall.pts.geometry.attributes.position.array;
      var lv2 = dt * (0.18 + 0.22 * act);
      for (var j = 0; j < leavesFall.n; j++) {
        lp[j * 3 + 1] -= lv2;
        lp[j * 3] += Math.sin(t * 1.3 + leavesFall.ph[j]) * dt * 0.4;
        lp[j * 3 + 2] += Math.cos(t * 0.9 + leavesFall.ph[j]) * dt * 0.22;
        if (lp[j * 3 + 1] < 0.15) {
          lp[j * 3 + 1] = 6.0; lp[j * 3] = rr(-6, 6); lp[j * 3 + 2] = rr(-5, 2);
        }
      }
      leavesFall.pts.geometry.attributes.position.needsUpdate = true;

      // Light shafts brighten gently with speech (kept faint, never solid white).
      for (var s = 0; s < shafts.length; s++) {
        var base = 0.038 + 0.012 * Math.sin(t * 0.5 + s);
        shafts[s].material.opacity = Math.min(0.12, base + (state === 'speaking' ? 0.03 + 0.05 * lv : 0));
      }

      // Butterflies trace gentle loops, wing beat rate follows activity.
      for (var b = 0; b < butterflies.length; b++) {
        var bf = butterflies[b], sp = bf.speed * (0.6 + 0.7 * act);
        var u = t * sp + bf.p;
        bf.g.position.x = bf.bx + Math.sin(u * 0.7) * 0.5;
        bf.g.position.y = bf.by + Math.sin(u * 1.3) * 0.28;
        bf.g.position.z = bf.bz + Math.cos(u * 0.5) * 0.4;
        bf.g.rotation.y = Math.sin(u * 0.5) * 0.4;
        // Wings dwell open and sweep closed (cos lingers at the extremes),
        // keeping a readable flapping silhouette instead of a vanishing line.
        var flap = 0.42 - 0.32 * Math.cos(t * (7 + 5 * act) + b * 1.7);
        bf.lw.rotation.y = flap;
        bf.rw.rotation.y = -flap;
      }
    }

    return { update: update };
  }

  root.createForestScene = createForestScene;
})(window);
