/* Replace this factory to change the character without changing conversation UI.
 * Contract: {root: THREE.Object3D, update(state, seconds, reducedMotion)}.
 * All geometry is built locally. No child photos or third-party character assets.
 */
(function () {
  'use strict';
  window.createForestCharacter = function (T) {
    var root = new T.Group(), sphere = new T.SphereGeometry(1, 32, 24);
    var colors = {skin:0xffd7b5,coat:0x718e65,light:0xe5edce,hair:0x483b30,hat:0xe0c794,
      band:0x769363,shoe:0x5f5b44,eye:0x2f352e,white:0xfffdf4,blush:0xf2ac96};
    var mats = {};
    Object.keys(colors).forEach(function (key) { mats[key]=new T.MeshStandardMaterial({color:colors[key],roughness:.78}); });
    function ell(parent,mat,x,y,z,sx,sy,sz) {
      var m=new T.Mesh(sphere,mats[mat]);m.position.set(x,y,z);m.scale.set(sx,sy,sz);
      m.castShadow=true;m.receiveShadow=true;parent.add(m);return m;
    }
    function cylinder(parent,mat,top,bottom,height,x,y,z) {
      var m=new T.Mesh(new T.CylinderGeometry(top,bottom,height,40),mats[mat]);
      m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;parent.add(m);return m;
    }
    var body = new T.Group();root.add(body);
    ell(body,'shoe',-.29,.15,.12,.27,.15,.39);ell(body,'shoe',.29,.15,.12,.27,.15,.39);
    ell(body,'light',-.28,.53,0,.18,.44,.19);ell(body,'light',.28,.53,0,.18,.44,.19);
    ell(body,'coat',0,1.4,0,.65,.80,.39);
    ell(body,'light',0,1.83,.34,.20,.40,.07);
    [-1,1].forEach(function (sign) {
      var lapel=ell(body,'coat',sign*.22,1.93,.34,.15,.32,.065);lapel.rotation.z=sign*-.40;
      ell(body,'light',sign*.37,1.21,.34,.15,.13,.055);
    });
    [1.29,1.52,1.75].forEach(function (y) {ell(body,'hat',0,y,.405,.035,.035,.025);});
    var left = new T.Group(), right = new T.Group();left.position.set(-.58,1.96,0);right.position.set(.58,1.96,0);
    body.add(left,right);
    ell(left,'coat',-.10,-.34,0,.19,.40,.22);ell(left,'skin',-.14,-.74,.03,.18,.20,.18);
    ell(right,'coat',.10,-.34,0,.19,.40,.22);ell(right,'skin',.14,-.74,.03,.18,.20,.18);
    ell(body,'skin',0,2.23,0,.20,.25,.19);
    var head = new T.Group();head.position.y=2.95;body.add(head);
    ell(head,'hair',0,.04,-.045,.79,.85,.64);
    ell(head,'skin',0,-.04,.12,.73,.74,.59);
    ell(head,'skin',-.73,-.06,.06,.12,.20,.15);ell(head,'skin',.73,-.06,.06,.12,.20,.15);
    [-1,1].forEach(function (s) {
      ell(head,'hair',s*.39,.50,.43,.28,.23,.20).rotation.z=s*.35;
      ell(head,'blush',s*.43,-.23,.57,.12,.066,.016);
      ell(head,'hair',s*.27,.24,.66,.13,.026,.024).rotation.z=s*-.09;
    });
    var eyes=[];
    [-1,1].forEach(function (s) {
      var eye=ell(head,'eye',s*.265,.063,.681,.065,.095,.031);eyes.push(eye);
      ell(head,'white',s*.265-.015,.09,.711,.016,.022,.008);
      var rim=new T.Mesh(new T.TorusGeometry(.195,.024,10,48),mats.shoe);
      rim.position.set(s*.265,.07,.69);head.add(rim);
    });
    ell(head,'shoe',0,.08,.704,.082,.021,.025);
    ell(head,'skin',0,-.12,.72,.10,.10,.10);
    var mouth=ell(head,'eye',0,-.34,.655,.12,.035,.023);
    // A small lower lip keeps the neutral expression soft.
    ell(head,'blush',0,-.392,.633,.092,.017,.015);
    cylinder(head,'hat',.93,.96,.07,0,.62,0);
    cylinder(head,'hat',.57,.69,.42,0,.86,-.015);
    cylinder(head,'band',.68,.70,.105,0,.69,0);
    var leaf=ell(head,'coat',.52,.80,.48,.095,.20,.025);leaf.rotation.z=-.55;
    // A field notebook tucked at the side.
    var book=new T.Mesh(new T.BoxGeometry(.30,.42,.09),mats.hat);book.position.set(-.65,1.02,.15);book.rotation.z=.15;body.add(book);
    root.rotation.y=-.10;
    return {
      root:root,
      update:function (state,t,reduced) {
        var motion=reduced?0:1, speak=state==='speaking', listen=state==='listening', think=state==='thinking';
        body.position.y=Math.sin(t*1.8)*.025*motion;
        head.rotation.z=(listen?-.10:think?.10:Math.sin(t*.7)*.025)*motion;
        head.rotation.y=(think?-.15:Math.sin(t*.6)*.035)*motion;
        left.rotation.z=(-.10+Math.sin(t*1.5)*.025)*motion;
        right.rotation.z=(listen?-.70:speak?-.35+Math.sin(t*3)*.09:.1)*motion;
        var blink=motion && (t%5.2<.14) ? .14 : 1;
        eyes.forEach(function (e) {e.scale.y=.095*blink;});
        mouth.scale.y=speak && motion ? .045+.055*(.5+.5*Math.sin(t*15)) : .035;
        mouth.scale.x=speak && motion ? .105+.015*Math.sin(t*9) : .12;
      }
    };
  };
})();
