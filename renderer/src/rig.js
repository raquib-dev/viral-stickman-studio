// Low-poly 3D stickman on a CC0 rig.
//
// The skeleton and its 14 animation clips come from "RobotExpressive" by Tomás Laulhé (Quaternius),
// CC0 1.0 (public/models/stickman-rig.glb, see THIRD_PARTY.md). Its robot meshes are hidden; we build
// our own faceted stick figure on the animated bones every frame, plus a face with expressions,
// blinking and a talking mouth.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { clamp, hash, lerp, noise1, stepFade } from "./util.js";

export const CLIPS = ["Idle", "Walking", "Running", "Dance", "Death", "Sitting", "Standing", "Jump", "Yes", "No",
  "Wave", "Punch", "ThumbsUp", "WalkJump"];
const LOOPING = new Set(["Idle", "Walking", "Running", "Dance"]);

export const EXPRESSIONS = {
  neutral: { browY: 0, browTilt: 0, browAsym: 0, eye: 1, smile: 0.15, open: 0, lookX: 0, lookY: 0 },
  happy: { browY: 0.05, browTilt: 0.1, browAsym: 0, eye: 0.82, smile: 1, open: 0.12, lookX: 0, lookY: 0 },
  surprised: { browY: 0.14, browTilt: 0.12, browAsym: 0, eye: 1.25, smile: 0, open: 0.75, lookX: 0, lookY: 0 },
  sad: { browY: -0.02, browTilt: 0.5, browAsym: 0, eye: 0.88, smile: -0.85, open: 0, lookX: 0, lookY: -0.2 },
  angry: { browY: -0.06, browTilt: -0.55, browAsym: 0, eye: 0.86, smile: -0.45, open: 0.08, lookX: 0, lookY: 0 },
  confused: { browY: 0.03, browTilt: 0, browAsym: 0.55, eye: 1, smile: -0.2, open: 0, lookX: 0.25, lookY: 0 },
  thinking: { browY: 0.03, browTilt: 0.2, browAsym: 0.3, eye: 0.94, smile: 0, open: 0, lookX: 0.3, lookY: 0.35 },
  skeptical: { browY: 0, browTilt: -0.15, browAsym: 0.65, eye: 0.8, smile: -0.1, open: 0, lookX: -0.15, lookY: 0 },
};

// Stick-figure proportions (metres). Only bone DIRECTIONS come from the rig's animation; lengths are
// ours, so the figure keeps classic stickman proportions whatever the source character looked like.
const HEAD_R = 0.2;
const LEN = { spine: 0.5, neck: 0.07, shoulder: 0.05, upperArm: 0.3, lowerArm: 0.27, hip: 0.07, upperLeg: 0.42, lowerLeg: 0.42 };
const ANKLE = 0.045;          // ankle height above the floor in the rest pose
const LIMB_R = 0.034;
const SPINE_R = 0.04;

let gltfCache = null;
export async function loadRig(url) {
  if (!gltfCache) gltfCache = await new GLTFLoader().loadAsync(url);
  return gltfCache;
}

export class Stickman {
  constructor(gltfSource, opts = {}) {
    const { SkeletonUtils } = opts;
    this.opts = { color: "#f1ece4", seed: 1, ...opts };
    this.group = new THREE.Group();
    this.model = SkeletonUtils.clone(gltfSource.scene);
    this.group.add(this.model);
    this.model.traverse((o) => { if (o.isMesh) o.visible = false; });
    let skinned = null;
    this.model.traverse((o) => { if (o.isSkinnedMesh && !skinned) skinned = o; });
    this.bones = Object.fromEntries(skinned.skeleton.bones.map((b) => [b.name, b]));
    this.mixer = new THREE.AnimationMixer(this.model);
    this.actions = {};
    for (const clip of gltfSource.animations) {
      const a = this.mixer.clipAction(clip);
      a.play();
      a.setEffectiveWeight(0);
      this.actions[clip.name] = a;
    }
    this.mixer.update(0);
    this._measure();
    this._build();
  }

  _bone(name) {
    // GLTFLoader sanitises node names ("Foot.L" -> "FootL")
    return this.bones[name] ?? this.bones[name.replace(/[.\s]/g, "")];
  }

  _p(name, out = new THREE.Vector3()) {
    this._bone(name).getWorldPosition(out);
    return this.group.worldToLocal(out);
  }

  _measure() {
    // rest pose: how far the rig's hips sit above its feet, so we can scale the hip height (and with it
    // jumps and crouches) to our leg length and keep the feet on the floor
    for (const a of Object.values(this.actions)) a.setEffectiveWeight(0);
    this.group.updateMatrixWorld(true);
    const hips = this._p("Hips"), foot = this._p("Foot.L");
    this.model.position.y -= foot.y;
    this.group.updateMatrixWorld(true);
    const legs = this._legChain(this._p("Hips"), "L", 1);
    const drop = this._p("Hips").y - legs[2].y;              // hips-to-ankle drop with our lengths
    this.hipScale = (drop + ANKLE) / Math.max(1e-6, hips.y - foot.y);
    const hq = new THREE.Quaternion();
    this._bone("Head").getWorldQuaternion(hq);
    this.headBindInv = this.group.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(hq).invert();
  }

  _dir(from, to) {
    return this._p(to).sub(this._p(from)).normalize();
  }

  _legChain(hipsPos, side, _k) {
    const a = hipsPos.clone().addScaledVector(this._dir("Hips", `UpperLeg.${side}`), LEN.hip);
    const b = a.clone().addScaledVector(this._dir(`UpperLeg.${side}`, `LowerLeg.${side}`), LEN.upperLeg);
    const c = b.clone().addScaledVector(this._dir(`LowerLeg.${side}`, `Foot.${side}`), LEN.lowerLeg);
    return [a, b, c];
  }

  _armChain(chest, side) {
    const a = chest.clone().addScaledVector(this._dir("Neck", `UpperArm.${side}`).setY(0).normalize(), LEN.shoulder);
    const b = a.clone().addScaledVector(this._dir(`UpperArm.${side}`, `LowerArm.${side}`), LEN.upperArm);
    const c = b.clone().addScaledVector(this._dir(`LowerArm.${side}`, `Palm2.${side}`), LEN.lowerArm);
    return [a, b, c];
  }

  _build() {
    const mat = new THREE.MeshStandardMaterial({ color: this.opts.color, flatShading: true, roughness: 0.55, metalness: 0.0 });
    const dark = new THREE.MeshStandardMaterial({ color: "#16120f", roughness: 0.18, metalness: 0.1 });
    const shine = new THREE.MeshBasicMaterial({ color: "#ffffff" });
    const mouthMat = new THREE.MeshStandardMaterial({ color: "#3a1612", roughness: 0.6 });
    this.mat = mat;
    const cyl = (r) => {
      const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, 1, 6, 1), mat);
      m.castShadow = true;
      this.group.add(m);
      return m;
    };
    const ball = (r, detail = 0) => {
      const m = new THREE.Mesh(new THREE.IcosahedronGeometry(r, detail), mat);
      m.castShadow = true;
      this.group.add(m);
      return m;
    };
    this.segs = {
      spine: cyl(SPINE_R), neck: cyl(LIMB_R * 0.9),
      uaL: cyl(LIMB_R), laL: cyl(LIMB_R * 0.95), uaR: cyl(LIMB_R), laR: cyl(LIMB_R * 0.95),
      ulL: cyl(LIMB_R * 1.1), llL: cyl(LIMB_R), ulR: cyl(LIMB_R * 1.1), llR: cyl(LIMB_R),
      shL: cyl(LIMB_R), shR: cyl(LIMB_R), hpL: cyl(LIMB_R * 1.1), hpR: cyl(LIMB_R * 1.1),
    };
    this.joints = {
      hips: ball(SPINE_R * 1.25), chest: ball(SPINE_R * 1.2),
      shL: ball(LIMB_R * 1.15), shR: ball(LIMB_R * 1.15), hpL: ball(LIMB_R * 1.2), hpR: ball(LIMB_R * 1.2),
      elL: ball(LIMB_R * 1.2), elR: ball(LIMB_R * 1.2), knL: ball(LIMB_R * 1.25), knR: ball(LIMB_R * 1.25),
      handL: ball(LIMB_R * 1.9, 0), handR: ball(LIMB_R * 1.9, 0),
      footL: ball(LIMB_R * 1.7, 0), footR: ball(LIMB_R * 1.7, 0),
    };
    this.joints.footL.scale.set(1, 0.55, 1.7);
    this.joints.footR.scale.set(1, 0.55, 1.7);

    // head: faceted icosphere + face parts in a group that follows the Head bone
    this.head = new THREE.Group();
    this.group.add(this.head);
    const skull = new THREE.Mesh(new THREE.IcosahedronGeometry(HEAD_R, 1), mat);
    skull.castShadow = true;
    this.head.add(skull);
    const r = HEAD_R, onSkin = (x, y) => Math.sqrt(Math.max(0, r * r - x * x - y * y)) * 0.97;
    this.eyes = [-1, 1].map((sx) => {
      const g = new THREE.Group();
      const x = sx * r * 0.36, y = r * 0.06;
      g.position.set(x, y, onSkin(x, y) - r * 0.02);
      g.add(new THREE.Mesh(new THREE.SphereGeometry(r * 0.17, 12, 8), dark));
      const hl = new THREE.Mesh(new THREE.SphereGeometry(r * 0.05, 8, 6), shine);
      hl.position.set(r * 0.05, r * 0.06, r * 0.13);
      const hl2 = new THREE.Mesh(new THREE.SphereGeometry(r * 0.024, 6, 4), shine);
      hl2.position.set(-r * 0.05, -r * 0.05, r * 0.14);
      g.add(hl, hl2);
      g.userData = { x, y };
      this.head.add(g);
      return g;
    });
    this.brows = [-1, 1].map((sx) => {
      const b = new THREE.Mesh(new THREE.BoxGeometry(r * 0.34, r * 0.07, r * 0.06), dark);
      b.userData = { sx, x: sx * r * 0.36, y: r * 0.36 };
      this.head.add(b);
      return b;
    });
    const arc = Math.PI * 0.62;
    this.mouthSmile = new THREE.Mesh(new THREE.TorusGeometry(r * 0.17, r * 0.03, 4, 12, arc), dark);
    this.mouthSmile.userData.arc = arc;
    this.mouthOpen = new THREE.Mesh(new THREE.SphereGeometry(r * 0.13, 12, 8), mouthMat);
    this.head.add(this.mouthSmile, this.mouthOpen);
    this.onSkin = onSkin;
    // blinks at seeded, irregular times
    this.blinks = [];
    for (let t = 1.2 + hash(1, this.opts.seed) * 1.5, k = 0; t < 600; k++) {
      this.blinks.push(t);
      t += 2.4 + hash(k + 2, this.opts.seed) * 2.2;
    }
  }

  /** Pose the bones for time t from the actor's animation track. */
  _animate(track, t) {
    for (const a of Object.values(this.actions)) a.setEffectiveWeight(0);
    const keys = track?.length ? track : [{ t: 0, clip: "Idle" }];
    const [prev, cur, w] = stepFade(keys, t, 0.35);
    const set = (key, weight, start) => {
      const a = this.actions[key.clip] ?? this.actions.Idle;
      const dur = a.getClip().duration, speed = key.speed ?? 1;
      let local = Math.max(0, t - start) * speed;
      const loop = key.loop ?? LOOPING.has(key.clip);
      if (loop) local %= dur;
      else if (local > dur) {
        // one-shot gestures settle back into Idle
        const back = clamp((local - dur) / 0.4);
        a.time = dur - 1e-4;
        a.setEffectiveWeight(a.getEffectiveWeight() + weight * (1 - back));
        const idle = this.actions.Idle;
        idle.time = ((local - dur) / speed) % idle.getClip().duration;
        idle.setEffectiveWeight(idle.getEffectiveWeight() + weight * back);
        return;
      }
      a.time = local;
      a.setEffectiveWeight(a.getEffectiveWeight() + weight);
    };
    if (prev !== cur && w < 1) set(prev, 1 - w, prev.t);
    set(cur, prev !== cur ? w : 1, cur.t);
    this.mixer.update(0);
  }

  _expression(face, talk, t, mouth) {
    const keys = face?.length ? face : [{ t: 0, expr: "neutral" }];
    const [prev, cur, w] = stepFade(keys, t, 0.25);
    const A = EXPRESSIONS[prev.expr] ?? EXPRESSIONS.neutral, B = EXPRESSIONS[cur.expr] ?? EXPRESSIONS.neutral;
    const e = Object.fromEntries(Object.keys(A).map((k) => [k, lerp(A[k], B[k], w)]));
    // talking: the voiceover's loudness per frame when the app supplies it (real lip sync), otherwise
    // syllable-like motion inside the talk windows
    let speak = 0;
    if (mouth?.values?.length) {
      const i = Math.floor(t * (mouth.fps ?? 24));
      speak = clamp(mouth.values[Math.min(mouth.values.length - 1, Math.max(0, i))] ?? 0);
      talk = [];
    }
    for (const [a, b] of talk ?? []) {
      if (t >= a && t <= b) {
        const edge = clamp((t - a) / 0.12) * clamp((b - t) / 0.12);
        const syl = 0.5 + 0.5 * Math.sin(t * Math.PI * 2 * 4.1 + noise1(t * 3, this.opts.seed) * 2.5);
        speak = edge * (0.25 + 0.75 * syl * (0.6 + 0.4 * (noise1(t * 1.3, this.opts.seed + 5) * 0.5 + 0.5)));
      }
    }
    // blink
    let blink = 1;
    for (const bt of this.blinks) {
      const d = Math.abs(t - bt);
      if (d < 0.09) blink = Math.min(blink, 0.08 + d / 0.09 * 0.92);
    }
    return { ...e, open: clamp(e.open + speak * 0.62), blink };
  }

  update(actor, t) {
    this._animate(actor.anim, t);
    this.group.updateMatrixWorld(true);
    const raw = this._p("Hips");
    const hips = new THREE.Vector3(raw.x, raw.y * this.hipScale, raw.z);
    const chest = hips.clone().addScaledVector(this._dir("Hips", "Neck"), LEN.spine);
    const up = this._dir("Neck", "Head");
    const neckTop = chest.clone().addScaledVector(up, LEN.neck);
    const headC = neckTop.clone().addScaledVector(up, HEAD_R * 0.92);
    const [shL, elL, wrL] = this._armChain(chest, "L"), [shR, elR, wrR] = this._armChain(chest, "R");
    const [hpL, knL, anL] = this._legChain(hips, "L"), [hpR, knR, anR] = this._legChain(hips, "R");
    const seg = (m, a, b) => {
      const d = b.clone().sub(a), len = d.length();
      m.position.copy(a).addScaledVector(d, 0.5);
      m.scale.set(1, Math.max(1e-4, len), 1);
      m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
    };
    const S = this.segs, J = this.joints;
    seg(S.spine, hips, chest); seg(S.neck, chest, neckTop.clone().addScaledVector(up, HEAD_R * 0.3));
    seg(S.uaL, shL, elL); seg(S.laL, elL, wrL); seg(S.uaR, shR, elR); seg(S.laR, elR, wrR);
    seg(S.ulL, hpL, knL); seg(S.llL, knL, anL); seg(S.ulR, hpR, knR); seg(S.llR, knR, anR);
    seg(S.shL, chest, shL); seg(S.shR, chest, shR); seg(S.hpL, hips, hpL); seg(S.hpR, hips, hpR);
    J.hips.position.copy(hips); J.chest.position.copy(chest);
    J.shL.position.copy(shL); J.shR.position.copy(shR); J.hpL.position.copy(hpL); J.hpR.position.copy(hpR);
    J.elL.position.copy(elL); J.elR.position.copy(elR); J.knL.position.copy(knL); J.knR.position.copy(knR);
    J.handL.position.copy(wrL); J.handR.position.copy(wrR);
    // feet point the way the hips face
    const fwd = this._dir("Hips", "Neck").cross(this._dir("UpperLeg.R", "UpperLeg.L")).normalize();
    for (const [f, an] of [[J.footL, anL], [J.footR, anR]]) {
      f.position.copy(an).addScaledVector(fwd, 0.035).add(new THREE.Vector3(0, -0.012, 0));
      f.rotation.set(0, Math.atan2(fwd.x, fwd.z), 0);
    }
    // head follows the Head bone's rotation relative to the rest pose
    const hq = new THREE.Quaternion();
    this._bone("Head").getWorldQuaternion(hq);
    const local = this.group.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(hq);
    this.head.quaternion.copy(local.multiply(this.headBindInv));
    this.head.position.copy(headC);
    this._face(this._expression(actor.face, actor.talk, t, actor.mouth));
  }

  _face(e) {
    const r = HEAD_R;
    for (const g of this.eyes) {
      const { x, y } = g.userData;
      const nx = x + e.lookX * r * 0.06, ny = y + e.lookY * r * 0.06;
      g.position.set(nx, ny, this.onSkin(nx, ny) - r * 0.02);
      g.scale.set(1, e.eye * e.blink, 1);
    }
    for (const b of this.brows) {
      const { sx, x, y } = b.userData;
      const by = y + e.browY * r + (sx > 0 ? e.browAsym : -e.browAsym * 0.4) * r * 0.12;
      b.position.set(x, by, this.onSkin(x, by) + r * 0.01);
      b.rotation.set(-0.25, 0, -sx * e.browTilt * 0.5);
    }
    const my = -r * 0.36;
    const z = this.onSkin(0, my);
    const arc = this.mouthSmile.userData.arc;
    const smiling = e.smile >= 0;
    this.mouthSmile.visible = e.open < 0.32 && Math.abs(e.smile) > 0.05;
    this.mouthSmile.rotation.set(-0.3, 0, smiling ? -Math.PI / 2 - arc / 2 : Math.PI / 2 - arc / 2);
    this.mouthSmile.scale.set(1, 0.35 + 0.65 * Math.abs(e.smile), 1);
    this.mouthSmile.position.set(0, my + (smiling ? r * 0.1 : -r * 0.06) * Math.abs(e.smile), z);
    this.mouthOpen.visible = e.open > 0.04 || Math.abs(e.smile) <= 0.05;
    this.mouthOpen.scale.set(0.75 + 0.25 * e.open, Math.max(0.12, e.open), 0.35);
    this.mouthOpen.position.set(0, my, z - r * 0.02);
  }

  /** Head-centre world position, for camera focus. */
  headWorld(out = new THREE.Vector3()) {
    return this.head.getWorldPosition(out);
  }
}
