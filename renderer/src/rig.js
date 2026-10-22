// Low-poly 3D stickman on a CC0 rig.
//
// The skeleton and its 14 animation clips come from "RobotExpressive" by Tomás Laulhé (Quaternius),
// CC0 1.0 (public/models/stickman-rig.glb, see THIRD_PARTY.md). Its robot meshes are hidden; we build
// our own faceted stick figure on the animated bones every frame, plus a face with expressions,
// blinking and a talking mouth.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { Tube } from "./tube.js";
import { clamp, ease, hash, lerp, noise1, stepFade } from "./util.js";

export const CLIPS = ["Idle", "Walking", "Running", "Dance", "Death", "Sitting", "Standing", "Jump", "Yes", "No",
  "Wave", "Punch", "ThumbsUp", "WalkJump"];
const LOOPING = new Set(["Idle", "Walking", "Running", "Dance"]);

export const EXPRESSIONS = {
  neutral: { browY: 0, browTilt: 0, browAsym: 0, eye: 1, smile: 0.15, open: 0, lookX: 0, lookY: 0 },
  happy: { browY: 0.05, browTilt: 0.1, browAsym: 0, eye: 0.82, smile: 1, open: 0.12, lookX: 0, lookY: 0 },
  surprised: { browY: 0.14, browTilt: 0.12, browAsym: 0, eye: 1.25, smile: 0, open: 0.75, lookX: 0, lookY: 0 },
  sad: { browY: -0.02, browTilt: 0.5, browAsym: 0, eye: 0.88, smile: -0.85, open: 0, lookX: 0, lookY: -0.2 },
  angry: { browY: -0.06, browTilt: -0.55, browAsym: 0, eye: 0.86, smile: -0.45, open: 0.08, lookX: 0, lookY: 0 },
  confused: { browY: 0.03, browTilt: 0, browAsym: 0.55, eye: 1, smile: -0.2, open: 0, lookX: 0.25, lookY: 0, tilt: 0.16 },
  thinking: { browY: 0.03, browTilt: 0.2, browAsym: 0.3, eye: 0.94, smile: 0, open: 0, lookX: 0.3, lookY: 0.35, tilt: 0.12 },
  skeptical: { browY: 0, browTilt: -0.15, browAsym: 0.65, eye: 0.8, smile: -0.1, open: 0, lookX: -0.15, lookY: 0, tilt: -0.1 },
};

export const GESTURES = ["point", "present", "think", "facepalm", "hips", "crossed", "shrug", "cheer", "hold", "explain", "rest"];
export const HATS = ["none", "cap", "tophat", "crown", "helmet", "headband", "beanie"];
export const LOOKS = ["camera", "left", "right", "up", "down"];
export const HAIR_STYLES = ["long", "bob", "short", "ponytail", "bun", "none"];
export const GLASSES = ["round", "square", "none"];

// Stick-figure proportions (metres). Only bone DIRECTIONS come from the rig's animation; lengths are
// ours, so the figure keeps classic stickman proportions whatever the source character looked like.
const HEAD_R = 0.2;
const LEN = { spine: 0.5, neck: 0.07, shoulder: 0.05, upperArm: 0.3, lowerArm: 0.27, hip: 0.07, upperLeg: 0.42, lowerLeg: 0.42 };
const ANKLE = 0.045;          // ankle height above the floor in the rest pose
const LIMB_R = 0.034;
const SPINE_R = 0.04;

/** Body builds. "stick" is the classic stick figure (the constants above, unchanged). "chibi" is a stylised
 *  person: a big head, short limbs, puffy sleeves and a jacket torso. k scales gesture reach to arm length. */
export const BUILDS = {
  stick: { headR: HEAD_R, len: LEN, ankle: ANKLE, limbR: LIMB_R, spineR: SPINE_R, k: 1, headY: 1.62, size: 1 },
  chibi: {
    headR: 0.235, ankle: 0.05, limbR: 0.058, spineR: 0.125, neckR: 0.045, shoulderR: 0.066, handR: 0.06, footR: 0.07,
    len: { spine: 0.34, neck: 0.03, shoulder: 0.07, upperArm: 0.2, lowerArm: 0.19, hip: 0.07, upperLeg: 0.27, lowerLeg: 0.26 },
  },
};
{
  const c = BUILDS.chibi, L = c.len;
  c.k = (L.upperArm + L.lowerArm) / (LEN.upperArm + LEN.lowerArm);
  c.headY = L.upperLeg + L.lowerLeg + c.ankle + L.spine + L.neck + c.headR * 0.92;
  c.size = c.headY / BUILDS.stick.headY;
}

// Bone names for each logical joint across common humanoid rigs: this project's CC0 rig, Quaternius /
// Unreal mannequin (upperarm_l, thigh_l...), Mixamo (mixamorig:LeftArm...) and Blender (upper_arm.L...).
const JOINTS = {
  Hips: ["hips", "pelvis", "mixamorighips"], Neck: ["neck", "neck01", "mixamorigneck", "upperchest", "chest", "spine2"], Head: ["head", "mixamorighead"],
  "UpperArm.L": ["upperarml", "mixamorigleftarm", "leftarm", "arml"], "UpperArm.R": ["upperarmr", "mixamorigrightarm", "rightarm", "armr"],
  "LowerArm.L": ["lowerarml", "forearml", "mixamorigleftforearm", "leftforearm"], "LowerArm.R": ["lowerarmr", "forearmr", "mixamorigrightforearm", "rightforearm"],
  "Palm2.L": ["palm2l", "handl", "mixamoriglefthand", "lefthand"], "Palm2.R": ["palm2r", "handr", "mixamorigrighthand", "righthand"],
  "UpperLeg.L": ["upperlegl", "thighl", "upperleglegl", "mixamorigleftupleg", "leftupleg"], "UpperLeg.R": ["upperlegr", "thighr", "mixamorigrightupleg", "rightupleg"],
  "LowerLeg.L": ["lowerlegl", "calfl", "shinl", "mixamorigleftleg", "leftleg"], "LowerLeg.R": ["lowerlegr", "calfr", "shinr", "mixamorigrightleg", "rightleg"],
  "Foot.L": ["footl", "mixamorigleftfoot", "leftfoot"], "Foot.R": ["footr", "mixamorigrightfoot", "rightfoot"],
};
const norm = (n) => String(n).toLowerCase().replace(/[^a-z0-9]/g, "");
// pack clips that replace the base rig's robot moves (first match wins)
const PACK_ALIASES = {
  Idle: [/^idle$/i, /^idle_?loop$/i, /idle/i], Walking: [/^walk(_?loop)?$/i, /^walk_?f(or)?w(ar)?d/i, /walk/i],
  Running: [/^(jog|run)(_?f(or)?w(ar)?d)?(_?loop)?$/i, /jog|run|sprint/i], Jump: [/^jump(_?start)?$/i, /^jump_?full_?short$/i, /jump/i],
  Sitting: [/^sit(ting)?(_?idle)?(_?loop)?$/i, /^sit_?chair_?idle$/i, /sit.*idle/i, /sit/i], Standing: [/stand_?up|get_?up/i], Wave: [/wave/i],
  Yes: [/^yes$|nod/i], No: [/^no$|head_?shake/i], ThumbsUp: [/thumb/i], Punch: [/punch/i], Dance: [/dance/i], Death: [/death|die/i],
};

class Source {
  constructor(gltf, SkeletonUtils, parent, kind) {
    this.kind = kind;
    this.model = SkeletonUtils.clone(gltf.scene);
    parent.add(this.model);
    this.model.traverse((o) => { if (o.isMesh) o.visible = false; });
    const bones = [];
    this.model.traverse((o) => { if (o.isBone) bones.push(o); });
    const byNorm = new Map(bones.map((b) => [norm(b.name), b]));
    this.map = {};
    const missing = [];
    for (const [j, cands] of Object.entries(JOINTS)) {
      let b = byNorm.get(norm(j)) ?? cands.map((c) => byNorm.get(c)).find(Boolean);
      // suffix match, e.g. "Armature_mixamorig:LeftArm" or "DEF-upper_arm.L"
      if (!b) b = bones.find((x) => cands.some((c) => norm(x.name).endsWith(c)));
      if (b) this.map[j] = b; else missing.push(j);
    }
    if (missing.length) throw new Error(`${kind}: no bone for ${missing.join(", ")}`);
    this.mixer = new THREE.AnimationMixer(this.model);
    this.actions = {};
    for (const clip of gltf.animations) {
      const a = this.mixer.clipAction(clip);
      a.play();
      a.setEffectiveWeight(0);
      this.actions[clip.name] = a;
    }
    this.alias = {};
    if (kind === "pack") {
      for (const [core, res] of Object.entries(PACK_ALIASES)) {
        const hit = res.map((re) => Object.keys(this.actions).find((n) => re.test(n))).find(Boolean);
        if (hit) this.alias[core] = hit;
      }
    }
    this.w = kind === "base" ? 1 : 0;
    this.mixer.update(0);
  }

  joint(name) {
    return this.map[name];
  }
}

let gltfCache = null;
export async function loadRig(url) {
  if (!gltfCache) gltfCache = await new GLTFLoader().loadAsync(url);
  return gltfCache;
}

/** The optional humanoid animation pack (renderer/public/models/anim-pack.glb); null when absent. */
export async function loadPack(url) {
  try {
    return await new GLTFLoader().loadAsync(url);
  } catch {
    return null;
  }
}

export class Stickman {
  constructor(gltfSource, opts = {}) {
    const { SkeletonUtils } = opts;
    this.opts = { color: "#f1ece4", seed: 1, ...opts };
    this.P = BUILDS[opts.build] ?? BUILDS.stick;
    this.headY = this.P.headY;   // head-centre height at rest (camera shots frame from it)
    this.size = this.P.size;     // relative to the stick figure (shot distances scale with it)
    this.group = new THREE.Group();
    // skeleton sources: the base CC0 rig, plus an optional humanoid animation pack (any naming scheme).
    // Only bone DIRECTIONS are read from them, so different skeletons blend and retarget cleanly.
    this.sources = [new Source(gltfSource, SkeletonUtils, this.group, "base")];
    if (opts.pack) {
      try { this.sources.push(new Source(opts.pack, SkeletonUtils, this.group, "pack")); }
      catch (e) { console.warn("animation pack ignored:", e.message); }
    }
    this.base = this.sources[0];
    this.pack = this.sources[1] ?? null;
    for (const src of this.sources) this._measure(src);
    this._build();
  }

  /** Clip name -> [source, action]. "pack:Name" picks a pack clip; core names prefer the pack's version. */
  _action(name) {
    if (name?.startsWith("pack:") && this.pack?.actions[name.slice(5)]) return [this.pack, this.pack.actions[name.slice(5)]];
    if (this.pack && this.pack.alias[name]) return [this.pack, this.pack.actions[this.pack.alias[name]]];
    const a = this.base.actions[name] ?? this.base.actions.Idle;
    return [this.base, a];
  }

  _bone(name, src = this.base) {
    return src.joint(name);
  }

  /** Position of a joint in actor space, from one source (default: blended over the active sources). */
  _p(name, out = new THREE.Vector3(), src = null) {
    if (src) {
      src.joint(name).getWorldPosition(out);
      return this.group.worldToLocal(out);
    }
    const acc = new THREE.Vector3();
    let wsum = 0;
    for (const s of this._active()) {
      acc.addScaledVector(this._p(name, new THREE.Vector3(), s), s.w);
      wsum += s.w;
    }
    return out.copy(acc.divideScalar(wsum || 1));
  }

  _active() {
    const act = this.sources.filter((s) => s.w > 1e-4);
    return act.length ? act : [this.base];
  }

  _measure(src) {
    // rest pose: how far this skeleton's hips sit above its feet, so hip height (and with it jumps and
    // crouches) scales to our leg length and the feet stay on the floor; also face +Z with left at +X
    for (const a of Object.values(src.actions)) a.setEffectiveWeight(0);
    this.group.updateMatrixWorld(true);
    const lr = this._p("UpperArm.L", new THREE.Vector3(), src).sub(this._p("UpperArm.R", new THREE.Vector3(), src)).setY(0);
    if (lr.lengthSq() > 1e-10) {
      src.model.rotation.y += Math.atan2(lr.z, lr.x);
      this.group.updateMatrixWorld(true);
    }
    const foot = this._p("Foot.L", new THREE.Vector3(), src);
    src.model.position.y -= foot.y;
    this.group.updateMatrixWorld(true);
    src.w = 1;
    const saved = this.sources.map((s) => s.w);
    this.sources.forEach((s) => { s.w = s === src ? 1 : 0; });
    const hips = this._p("Hips", new THREE.Vector3(), src);
    const legs = this._legChain(hips, "L", 1);
    src.hipScale = (hips.y - legs[2].y + this.P.ankle) / Math.max(1e-6, hips.y);
    this.sources.forEach((s, i) => { s.w = saved[i]; });
    const hq = new THREE.Quaternion();
    src.joint("Head").getWorldQuaternion(hq);
    src.headBindInv = this.group.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(hq).invert();
  }

  /** Hips position in actor space, scaled to our proportions, blended over the active sources. */
  _hips() {
    const acc = new THREE.Vector3();
    let wsum = 0;
    for (const s of this._active()) {
      const r = this._p("Hips", new THREE.Vector3(), s);
      acc.addScaledVector(new THREE.Vector3(r.x * s.hipScale, r.y * s.hipScale, r.z * s.hipScale), s.w);
      wsum += s.w;
    }
    return acc.divideScalar(wsum || 1);
  }

  /** Head rotation relative to the rest pose, blended over the active sources. */
  _headQuat() {
    const inv = this.group.getWorldQuaternion(new THREE.Quaternion()).invert();
    let q = null, wsum = 0;
    for (const s of this._active()) {
      const hq = new THREE.Quaternion();
      s.joint("Head").getWorldQuaternion(hq);
      const local = inv.clone().multiply(hq).multiply(s.headBindInv);
      if (!q) { q = local; wsum = s.w; continue; }
      wsum += s.w;
      q.slerp(local, s.w / wsum);
    }
    return q ?? new THREE.Quaternion();
  }

  _dir(from, to) {
    const acc = new THREE.Vector3();
    for (const s of this._active()) acc.addScaledVector(this._p(to, new THREE.Vector3(), s).sub(this._p(from, new THREE.Vector3(), s)).normalize(), s.w);
    return acc.lengthSq() > 1e-12 ? acc.normalize() : new THREE.Vector3(0, 1, 0);
  }

  _legChain(hipsPos, side, _k) {
    const a = hipsPos.clone().addScaledVector(this._dir("Hips", `UpperLeg.${side}`), this.P.len.hip);
    const b = a.clone().addScaledVector(this._dir(`UpperLeg.${side}`, `LowerLeg.${side}`), this.P.len.upperLeg);
    const c = b.clone().addScaledVector(this._dir(`LowerLeg.${side}`, `Foot.${side}`), this.P.len.lowerLeg);
    return [a, b, c];
  }

  _armChain(chest, side) {
    const a = chest.clone().addScaledVector(this._dir("Neck", `UpperArm.${side}`).setY(0).normalize(), this.P.len.shoulder);
    const b = a.clone().addScaledVector(this._dir(`UpperArm.${side}`, `LowerArm.${side}`), this.P.len.upperArm);
    const c = b.clone().addScaledVector(this._dir(`LowerArm.${side}`, `Palm2.${side}`), this.P.len.lowerArm);
    return [a, b, c];
  }

  _build() {
    if (this.opts.build === "chibi") return this._buildChibi();
    // clay = soft studio plastic; toon = matte, flatter shading for the illustrated styles
    const mat = this.opts.material === "toon"
      ? new THREE.MeshLambertMaterial({ color: this.opts.color, flatShading: true })
      : new THREE.MeshStandardMaterial({ color: this.opts.color, flatShading: true, roughness: this.opts.roughness ?? 0.55, metalness: 0.0 });
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
      spine: cyl(this.P.spineR), neck: cyl(this.P.limbR * 0.9),
      uaL: cyl(this.P.limbR), laL: cyl(this.P.limbR * 0.95), uaR: cyl(this.P.limbR), laR: cyl(this.P.limbR * 0.95),
      ulL: cyl(this.P.limbR * 1.1), llL: cyl(this.P.limbR), ulR: cyl(this.P.limbR * 1.1), llR: cyl(this.P.limbR),
      shL: cyl(this.P.limbR), shR: cyl(this.P.limbR), hpL: cyl(this.P.limbR * 1.1), hpR: cyl(this.P.limbR * 1.1),
    };
    this.joints = {
      hips: ball(this.P.spineR * 1.25), chest: ball(this.P.spineR * 1.2),
      shL: ball(this.P.limbR * 1.15), shR: ball(this.P.limbR * 1.15), hpL: ball(this.P.limbR * 1.2), hpR: ball(this.P.limbR * 1.2),
      elL: ball(this.P.limbR * 1.2), elR: ball(this.P.limbR * 1.2), knL: ball(this.P.limbR * 1.25), knR: ball(this.P.limbR * 1.25),
      handL: ball(this.P.limbR * 1.9, 0), handR: ball(this.P.limbR * 1.9, 0),
      footL: ball(this.P.limbR * 1.7, 0), footR: ball(this.P.limbR * 1.7, 0),
    };
    this.joints.footL.scale.set(1, 0.55, 1.7);
    this.joints.footR.scale.set(1, 0.55, 1.7);
    // bendy limbs (default): one curved tube per limb instead of two cylinders and a joint ball
    this.bendy = this.opts.limbs !== "rigid";
    if (this.bendy) {
      for (const m of Object.values(this.segs)) m.visible = false;
      for (const k of ["elL", "elR", "knL", "knR", "shL", "shR", "hpL", "hpR"]) this.joints[k].visible = false;
      this.joints.chest.scale.setScalar(0.85);
      this.joints.hips.scale.setScalar(0.9);
      this.tubes = {};
      for (const k of ["spine", "neck", "armL", "armR", "legL", "legR", "shL", "shR", "hpL", "hpR"]) {
        const t = new Tube(mat, 6, k.startsWith("arm") || k.startsWith("leg") ? 14 : 6);
        this.group.add(t.mesh);
        this.tubes[k] = t;
      }
    }

    // head: faceted icosphere + face parts in a group that follows the Head bone
    this.head = new THREE.Group();
    this.group.add(this.head);
    const skull = new THREE.Mesh(new THREE.IcosahedronGeometry(this.P.headR, 1), mat);
    skull.castShadow = true;
    this.head.add(skull);
    const r = this.P.headR, onSkin = (x, y) => Math.sqrt(Math.max(0, r * r - x * x - y * y)) * 0.97;
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
    this._hat(this.opts.hat ?? "none");
    // blinks at seeded, irregular times
    this.blinks = [];
    for (let t = 1.2 + hash(1, this.opts.seed) * 1.5, k = 0; t < 600; k++) {
      this.blinks.push(t);
      t += 2.4 + hash(k + 2, this.opts.seed) * 2.2;
    }
  }

  /** A stylised person: elliptical faceted head (face shape from `appearance.face`, nudged per `variant`), dot
   *  eyes, glasses, headphones, hair styles, and clothes coloured per part. Same skeleton, motion and face code. */
  _buildChibi() {
    const ap = { skin: "#f1c7a5", hair: "#2b1d16", hair_style: "long", top: "#f2b31b", shirt: "#1d1d22", bottom: "#2c3140",
      shoes: "#2a2a2e", glasses: "round", headphones: true, headphones_color: "#d9d9de", variant: 0, ...(this.opts.appearance ?? {}) };
    const f0 = { width: 1.0, height: 0.96, depth: 0.92, jaw: 0.22, eye_spacing: 0.34, eye_y: -0.02, eye_size: 1.0, mouth_y: -0.42,
      ...(ap.face ?? {}) };
    // slight, repeatable face variation per variant number (the same person, a little different)
    const jitter = (k, amt) => (ap.variant ? (hash(k, ap.variant) - 0.5) * 2 * amt : 0);
    const F = { width: f0.width * (1 + jitter(1, 0.05)), height: f0.height * (1 + jitter(2, 0.05)), depth: f0.depth,
      jaw: Math.max(0, f0.jaw + jitter(3, 0.08)), eye_spacing: f0.eye_spacing * (1 + jitter(4, 0.08)),
      eye_y: f0.eye_y + jitter(5, 0.04), eye_size: f0.eye_size * (1 + jitter(6, 0.1)), mouth_y: f0.mouth_y + jitter(7, 0.03) };
    this.face = F;
    this.fixedColors = true;
    this.bendy = true;
    const std = (color, rough = 0.62) => new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: 0, flatShading: true });
    const M = { skin: std(ap.skin, 0.55), top: std(ap.top, 0.7), shirt: std(ap.shirt, 0.8), bottom: std(ap.bottom, 0.8),
      shoes: std(ap.shoes, 0.6), hair: std(ap.hair, 0.5), dark: new THREE.MeshStandardMaterial({ color: "#141012", roughness: 0.3 }),
      phones: std(ap.headphones_color, 0.4) };
    this.mats = M;
    this.mat = M.skin;
    const ball = (r, mat, detail = 1) => {
      const m = new THREE.Mesh(new THREE.IcosahedronGeometry(r, detail), mat);
      m.castShadow = true;
      this.group.add(m);
      return m;
    };
    const P = this.P;
    this.segs = {};
    this.joints = {
      hips: ball(P.spineR * 1.05, M.bottom), chest: ball(P.spineR * 1.02, M.top),
      shL: ball(P.shoulderR, M.top), shR: ball(P.shoulderR, M.top), hpL: ball(P.limbR, M.bottom), hpR: ball(P.limbR, M.bottom),
      elL: ball(P.limbR, M.top), elR: ball(P.limbR, M.top), knL: ball(P.limbR, M.bottom), knR: ball(P.limbR, M.bottom),
      handL: ball(P.handR, M.skin), handR: ball(P.handR, M.skin), footL: ball(P.footR, M.shoes), footR: ball(P.footR, M.shoes),
    };
    // only hands and shoes show; the rest are inside the clothes (a chest ball read as a scarf under the chin)
    for (const k of ["elL", "elR", "knL", "knR", "hpL", "hpR", "chest", "shL", "shR"]) this.joints[k].visible = false;
    this.joints.footL.scale.set(0.9, 0.55, 1.5);
    this.joints.footR.scale.set(0.9, 0.55, 1.5);
    this.tubes = {};
    const tubeMat = { spine: M.top, neck: M.skin, armL: M.top, armR: M.top, legL: M.bottom, legR: M.bottom,
      shL: M.top, shR: M.top, hpL: M.bottom, hpR: M.bottom };
    for (const [k, m] of Object.entries(tubeMat)) {
      const t = new Tube(m, 10, k.startsWith("arm") || k.startsWith("leg") ? 14 : 8);
      this.group.add(t.mesh);
      this.tubes[k] = t;
    }
    // inner shirt and a puffy collar, placed on the chest every frame (decorate)
    this.shirt = new THREE.Mesh(new THREE.BoxGeometry(P.spineR * 0.55, P.len.spine * 0.75, 0.012), M.shirt);
    this.collar = new THREE.Mesh(new THREE.TorusGeometry(P.spineR * 0.42, P.spineR * 0.16, 6, 18), M.top);
    this.collar.castShadow = true;
    this.group.add(this.shirt, this.collar);
    this.collar.visible = !!ap.collar;

    // head: an ellipsoid with a tapered jaw
    this.head = new THREE.Group();
    this.group.add(this.head);
    const r = P.headR;
    const geo = new THREE.IcosahedronGeometry(r, 3);
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      let x = pos.getX(i) * F.width, y = pos.getY(i) * F.height, z = pos.getZ(i) * F.depth;
      if (y < 0) { const d = Math.pow(-y / (r * F.height), 1.6); x *= 1 - F.jaw * d; z *= 1 - F.jaw * 0.5 * d; }
      pos.setXYZ(i, x, y, z);
    }
    geo.computeVertexNormals();
    const skull = new THREE.Mesh(geo, M.skin);
    skull.castShadow = true;
    this.head.add(skull);
    const onSkin = (x, y) => {
      const ny = y / (r * F.height), jaw = y < 0 ? 1 - F.jaw * Math.pow(-ny, 1.6) : 1;
      const nx = x / (r * F.width * jaw);
      return r * F.depth * (y < 0 ? 1 - F.jaw * 0.5 * Math.pow(-ny, 1.6) : 1) * Math.sqrt(Math.max(0, 1 - nx * nx - ny * ny)) * 0.985;
    };
    this.onSkin = onSkin;
    // dot eyes with one small highlight
    const shine = new THREE.MeshBasicMaterial({ color: "#ffffff" });
    this.eyes = [-1, 1].map((sx) => {
      const g = new THREE.Group();
      const x = sx * r * F.eye_spacing, y = r * F.eye_y;
      g.position.set(x, y, onSkin(x, y) - r * 0.015);
      const dot = new THREE.Mesh(new THREE.SphereGeometry(r * 0.072 * F.eye_size, 12, 8), M.dark);
      dot.scale.set(0.9, 1.12, 0.5);
      const hl = new THREE.Mesh(new THREE.SphereGeometry(r * 0.02 * F.eye_size, 6, 4), shine);
      hl.position.set(r * 0.025, r * 0.03, r * 0.03);
      g.add(dot, hl);
      g.userData = { x, y };
      this.head.add(g);
      return g;
    });
    this.brows = [-1, 1].map((sx) => {
      const b = new THREE.Mesh(new THREE.BoxGeometry(r * 0.2, r * 0.03, r * 0.03), M.dark);
      b.userData = { sx, x: sx * r * F.eye_spacing, y: r * (F.eye_y + 0.38) };
      this.head.add(b);
      return b;
    });
    const arc = Math.PI * 0.6;
    this.mouthSmile = new THREE.Mesh(new THREE.TorusGeometry(r * 0.075, r * 0.016, 4, 12, arc), M.dark);
    this.mouthSmile.userData.arc = arc;
    this.mouthOpen = new THREE.Mesh(new THREE.SphereGeometry(r * 0.065, 12, 8), new THREE.MeshStandardMaterial({ color: "#5a2420", roughness: 0.6 }));
    this.mouthY = r * F.mouth_y;
    this.head.add(this.mouthSmile, this.mouthOpen);
    this._hair(ap, F, M.hair);
    if (ap.glasses && ap.glasses !== "none") this._glasses(ap.glasses, F, M.dark);
    if (ap.headphones) this._headphones(F, M.phones);
    this.blinks = [];
    for (let t = 1.2 + hash(1, this.opts.seed) * 1.5, k = 0; t < 600; k++) {
      this.blinks.push(t);
      t += 2.6 + hash(k + 2, this.opts.seed) * 2.6;
    }
    this.decorate = ({ chest, up, fwd }) => {
      const side = new THREE.Vector3().crossVectors(up, fwd).normalize();
      const basis = new THREE.Matrix4().makeBasis(side, up, fwd);
      this.shirt.quaternion.setFromRotationMatrix(basis);
      this.shirt.position.copy(chest).addScaledVector(up, -P.len.spine * 0.36).addScaledVector(fwd, P.spineR * 1.0);
      this.collar.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), up);
      this.collar.position.copy(chest).addScaledVector(up, P.len.neck * 0.6 + 0.01);
    };
  }

  _hair(ap, F, mat) {
    const r = this.P.headR, add = (geo, p = [0, 0, 0], rot = [0, 0, 0], scale = [1, 1, 1]) => {
      const m = new THREE.Mesh(geo, mat);
      m.position.set(...p); m.rotation.set(...rot); m.scale.set(...scale);
      m.castShadow = true;
      this.head.add(m);
      return m;
    };
    const style = ap.hair_style ?? "long";
    if (style === "none") return;
    mat.side = THREE.DoubleSide;
    // a shell around the head with an oval opening for the face: a curved hairline that frames the cheeks
    const shell = new THREE.SphereGeometry(1, 40, 28).toNonIndexed();
    const sp = shell.attributes.position, keep = [];
    for (let i = 0; i < sp.count; i += 3) {
      let cx = 0, cy = 0, cz = 0;
      for (let k = 0; k < 3; k++) { cx += sp.getX(i + k) / 3; cy += sp.getY(i + k) / 3; cz += sp.getZ(i + k) / 3; }
      const face = cz > 0.15 && (cx / 0.74) ** 2 + ((cy + 0.12) / 0.66) ** 2 < 1;
      const chin = cy < -0.55 && cz > -0.2;            // never under the chin or across the jaw
      if (!face && !chin) for (let k = 0; k < 3; k++) keep.push(sp.getX(i + k), sp.getY(i + k), sp.getZ(i + k));
    }
    const hairGeo = new THREE.BufferGeometry();
    hairGeo.setAttribute("position", new THREE.Float32BufferAttribute(keep, 3));
    hairGeo.computeVertexNormals();
    add(hairGeo, [0, r * 0.02, -r * 0.01], [0, 0, 0], [r * F.width * 1.06, r * F.height * 1.06, r * F.depth * 1.08]);
    const len = { long: r * 2.7, bob: r * 1.25, ponytail: 0, bun: 0, short: 0 }[style] ?? 0;
    if (len) {
      // the back and sides fall straight down from ear level, a little wider at the ends
      add(new THREE.CylinderGeometry(r * F.width * 1.03, r * F.width * 1.14, len, 26, 1, true, Math.PI * 0.44, Math.PI * 1.12),
        [0, r * 0.3 - len / 2, -r * 0.1], [0, 0, 0], [1, 1, F.depth * 0.98]);
    }
    if (style === "ponytail") add(new THREE.CylinderGeometry(r * 0.14, r * 0.05, r * 1.6, 10), [0, -r * 0.35, -r * 1.05], [0.45, 0, 0]);
    if (style === "bun") add(new THREE.IcosahedronGeometry(r * 0.36, 1), [0, r * 0.82, -r * 0.42]);
  }

  _glasses(kind, F, mat) {
    const r = this.P.headR, square = kind === "square";
    for (const sx of [-1, 1]) {
      const x = sx * r * F.eye_spacing, y = r * F.eye_y;
      const ring = new THREE.Mesh(new THREE.TorusGeometry(r * 0.21, r * 0.016, 6, square ? 4 : 30), mat);
      ring.position.set(x, y, this.onSkin(x, y) + r * 0.05);
      if (square) ring.rotation.z = Math.PI / 4;
      this.head.add(ring);
      // temple arm back to the ear
      const arm = new THREE.Mesh(new THREE.BoxGeometry(r * 0.02, r * 0.02, r * 0.6), mat);
      arm.position.set(sx * r * F.width * 0.97, y + r * 0.02, -r * 0.05);
      this.head.add(arm);
    }
    const bridge = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.012, r * 0.012, r * (2 * F.eye_spacing - 0.42), 6), mat);
    bridge.rotation.z = Math.PI / 2;
    bridge.position.set(0, r * (F.eye_y + 0.04), this.onSkin(0, r * F.eye_y) + r * 0.06);
    this.head.add(bridge);
  }

  _headphones(F, mat) {
    const r = this.P.headR;
    const band = new THREE.Mesh(new THREE.TorusGeometry(r * F.width * 1.07, r * 0.04, 6, 26, Math.PI), mat);
    band.position.set(0, -r * 0.02, -r * 0.18);
    band.rotation.x = -0.3;
    band.castShadow = true;
    this.head.add(band);
    for (const sx of [-1, 1]) {
      const cup = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.22, r * 0.22, r * 0.16, 18), mat);
      cup.rotation.z = Math.PI / 2;
      cup.position.set(sx * r * F.width * 1.08, -r * 0.02, -r * 0.1);
      cup.castShadow = true;
      this.head.add(cup);
    }
  }

  _hat(kind) {
    if (!kind || kind === "none") return;
    const r = this.P.headR, g = new THREE.Group();
    const m = new THREE.MeshStandardMaterial({ color: this.opts.hatColor ?? "#2b2f3a", flatShading: true, roughness: 0.7 });
    const gold = new THREE.MeshStandardMaterial({ color: "#e2b13c", flatShading: true, roughness: 0.35, metalness: 0.6 });
    const add = (geo, mat, pos, rot = [0, 0, 0]) => { const x = new THREE.Mesh(geo, mat); x.position.set(...pos); x.rotation.set(...rot); x.castShadow = true; g.add(x); };
    if (kind === "cap") { add(new THREE.SphereGeometry(r * 1.02, 10, 6, 0, Math.PI * 2, 0, Math.PI / 2), m, [0, r * 0.25, 0]); add(new THREE.CylinderGeometry(r * 0.75, r * 0.75, r * 0.05, 10, 1, false, -Math.PI / 2, Math.PI), m, [0, r * 0.28, r * 0.45], [0.15, 0, 0]); }
    if (kind === "tophat") { add(new THREE.CylinderGeometry(r * 1.25, r * 1.25, r * 0.06, 12), m, [0, r * 0.82, 0]); add(new THREE.CylinderGeometry(r * 0.72, r * 0.75, r * 0.9, 12), m, [0, r * 1.25, 0]); }
    if (kind === "crown") { add(new THREE.CylinderGeometry(r * 0.66, r * 0.7, r * 0.34, 10, 1, true), gold, [0, r * 0.8, 0]); for (let k = 0; k < 5; k++) add(new THREE.ConeGeometry(r * 0.11, r * 0.28, 4), gold, [Math.sin(k * 1.257) * r * 0.64, r * 1.08, Math.cos(k * 1.257) * r * 0.64]); }
    if (kind === "helmet") { add(new THREE.SphereGeometry(r * 1.08, 10, 6, 0, Math.PI * 2, 0, Math.PI / 2), gold, [0, r * 0.1, 0]); add(new THREE.BoxGeometry(r * 0.1, r * 0.5, r * 0.12), gold, [0, r * 0.05, r * 1.0]); }
    if (kind === "headband") add(new THREE.TorusGeometry(r * 0.98, r * 0.07, 5, 16), new THREE.MeshStandardMaterial({ color: "#d9453b", flatShading: true }), [0, r * 0.45, 0], [Math.PI / 2, 0, 0]);
    if (kind === "beanie") { add(new THREE.SphereGeometry(r * 1.05, 10, 6, 0, Math.PI * 2, 0, Math.PI / 2), m, [0, r * 0.2, 0]); add(new THREE.IcosahedronGeometry(r * 0.2, 0), m, [0, r * 1.25, 0]); }
    this.head.add(g);
  }

  /** Two-bone IK: elbow position for a shoulder S reaching target T, bending toward `pole`. */
  static ik(S, T, a, b, pole, maxReach = 0.965) {
    // maxReach < 1: a relaxed limb never locks fully straight
    const d = T.clone().sub(S);
    const dist = Math.min(d.length(), (a + b) * maxReach), dir = d.normalize();
    const cosA = clamp((a * a + dist * dist - b * b) / (2 * a * dist), -1, 1);
    const perp = pole.clone().addScaledVector(dir, -pole.dot(dir));
    if (perp.lengthSq() < 1e-6) perp.set(0, -1, 0);
    perp.normalize();
    const E = S.clone().addScaledVector(dir, a * cosA).addScaledVector(perp, a * Math.sqrt(1 - cosA * cosA));
    const H = E.clone().addScaledVector(T.clone().sub(E).normalize(), b);
    return [E, H];
  }

  /** Hand target + elbow hint for a gesture, in actor space. side = +1 for L (at +X), -1 for R. */
  _gestureTarget(g, side, L, t, target) {
    const { chest, headC, hips, sh } = L;
    // offsets are in stick-figure metres; a smaller build reaches proportionally less far
    const k = this.P.k, V = (x, y, z) => new THREE.Vector3(x * k, y * k, z * k);
    switch (g.gesture) {
      case "think": return [headC.clone().add(V(side * 0.03, -this.P.headR * 1.05, this.P.headR * 0.75)), V(side * 0.5, -1, 0.6)];
      case "facepalm": return [headC.clone().add(V(side * 0.02, -this.P.headR * 0.1, this.P.headR * 1.05)), V(side * 0.8, -1, 0.2)];
      case "hips": return [hips.clone().add(V(side * 0.15, 0.02, 0.03)), V(side, 0.3, -0.7)];
      case "crossed": return [chest.clone().add(V(-side * 0.11, -0.16, 0.13 + (side > 0 ? 0.03 : 0))), V(side, -0.7, 0.3)];
      case "shrug": return [chest.clone().add(V(side * 0.4, -0.2, 0.22)), V(side * 0.5, -1, -0.2)];
      case "cheer": return [headC.clone().add(V(side * 0.3, 0.42, 0.02)), V(side, 0, 0)];
      case "present": return [chest.clone().add(V(side * 0.5, -0.12, 0.36)), V(side * 0.3, -1, -0.3)];
      case "hold": return [chest.clone().add(V(side * 0.13, -0.24, 0.3)), V(side, -1, 0)];
      case "rest": return [chest.clone().add(V(side * 0.17, -0.3, 0.36)), V(side, -0.6, -0.4)];
      case "explain": {
        const w = Math.sin(t * 3.1 + side) * 0.06;
        return [chest.clone().add(V(side * 0.3, -0.22 + w, 0.3)), V(side, -1, -0.2)];
      }
      case "point": default: {
        // aim at the target, but keep the arm in front of the body and between waist and eye height (a target
        // far off to the side or behind used to swing a locked-straight arm out of frame)
        const dir = (target ? target.clone().sub(sh) : V(side, 0.1, 0.4)).normalize();
        dir.z = Math.max(dir.z, 0.35);
        dir.y = clamp(dir.y, -0.35, 0.45);
        dir.normalize();
        return [sh.clone().addScaledVector(dir, (this.P.len.upperArm + this.P.len.lowerArm) * 0.9), V(0, -1, -0.2)];
      }
    }
  }

  /** Pose the bones for time t from the actor's animation track. */
  _animate(track, t, move = 0, dist = 0) {
    for (const src of this.sources) for (const a of Object.values(src.actions)) a.setEffectiveWeight(0);
    const keys = track?.length ? track : [{ t: 0, clip: "Idle" }];
    const [prev, cur, w] = stepFade(keys, t, 0.35);
    const add = (a, wt) => a.setEffectiveWeight(a.getEffectiveWeight() + wt);
    const set = (key, weight, start) => {
      const [, a] = this._action(key.clip);
      const dur = a.getClip().duration, speed = key.speed ?? 1;
      let local = Math.max(0, t - start) * speed;
      const base = key.clip?.startsWith("pack:") ? key.clip.slice(5) : key.clip;
      const loop = key.loop ?? (LOOPING.has(base) || /idle|walk|run|jog|loop/i.test(base ?? ""));
      if (loop) local %= dur;
      else if (local > dur) {
        // one-shot gestures settle back into Idle
        const back = clamp((local - dur) / 0.4);
        a.time = dur - 1e-4;
        add(a, weight * (1 - back));
        const [, idle] = this._action("Idle");
        idle.time = ((local - dur) / speed) % idle.getClip().duration;
        add(idle, weight * back);
        return;
      }
      a.time = local;
      add(a, weight);
    };
    // walking/running when the actor moves along its path: speed (m/s) fades the gait in over the track
    const mv = clamp(move / 0.35);
    const keep = 1 - mv;
    if (prev !== cur && w < 1) set(prev, (1 - w) * keep, prev.t);
    set(cur, (prev !== cur ? w : 1) * keep, cur.t);
    if (mv > 0) {
      const running = move > 1.9;
      const [, gait] = this._action(running ? "Running" : "Walking");
      // phase from distance travelled, so feet do not slide when the speed changes
      const stride = running ? 3.2 : 1.15;
      gait.time = ((dist / stride) * gait.getClip().duration) % gait.getClip().duration;
      add(gait, mv);
    }
    for (const src of this.sources) {
      src.mixer.update(0);
      src.w = Object.values(src.actions).reduce((acc, a) => acc + a.getEffectiveWeight(), 0);
    }
    this.group.updateMatrixWorld(true);
    return this._action("Idle")[1].getEffectiveWeight();
  }

  /** Speech energy 0..1 at time t: the voice's loudness when supplied, else syllables in the talk windows. */
  _speak(talk, mouth, t) {
    if (mouth?.values?.length) {
      const i = Math.floor(t * (mouth.fps ?? 24));
      return clamp(mouth.values[Math.min(mouth.values.length - 1, Math.max(0, i))] ?? 0);
    }
    for (const [a, b] of talk ?? []) {
      if (t >= a && t <= b) {
        const edge = clamp((t - a) / 0.12) * clamp((b - t) / 0.12);
        const syl = 0.5 + 0.5 * Math.sin(t * Math.PI * 2 * 4.1 + noise1(t * 3, this.opts.seed) * 2.5);
        return edge * (0.25 + 0.75 * syl * (0.6 + 0.4 * (noise1(t * 1.3, this.opts.seed + 5) * 0.5 + 0.5)));
      }
    }
    return 0;
  }

  /** Speech emphasis: the speech energy averaged over the last ~0.3 s (slow enough to drive arms and nods). */
  _emphasis(actor, t) {
    let sum = 0;
    for (let k = 0; k < 6; k++) sum += this._speak(actor.talk, actor.mouth, t - k * 0.05);
    return sum / 6;
  }

  _expression(face, talk, t, mouth) {
    const keys = face?.length ? face : [{ t: 0, expr: "neutral" }];
    const [prev, cur, w] = stepFade(keys, t, 0.25);
    const A = EXPRESSIONS[prev.expr] ?? EXPRESSIONS.neutral, B = EXPRESSIONS[cur.expr] ?? EXPRESSIONS.neutral;
    const names = new Set([...Object.keys(A), ...Object.keys(B)]);
    const e = Object.fromEntries([...names].map((k) => [k, lerp(A[k] ?? 0, B[k] ?? 0, w)]));
    // talking: the voiceover's loudness per frame when the app supplies it (real lip sync), otherwise
    // syllable-like motion inside the talk windows
    const speak = this._speak(talk, mouth, t);
    // blink
    let blink = 1;
    for (const bt of this.blinks) {
      const d = Math.abs(t - bt);
      if (d < 0.09) blink = Math.min(blink, 0.08 + d / 0.09 * 0.92);
    }
    return { ...e, open: clamp(e.open + speak * 0.62), blink };
  }

  /**
   * The whole skeleton at time t as points in actor space: the rig's animation, then gestures (IK), then
   * the "life" layer that keeps the figure from moving like a robot: breathing, weight shift on planted
   * feet with soft knees, relaxed hanging arms, beat gestures that follow the voice. Pure in t.
   */
  _pose(actor, t, ctx) {
    const idleW = this._animate(actor.anim, t, ctx.speed ?? 0, ctx.dist ?? 0) * (1 - clamp((ctx.speed ?? 0) / 0.35));
    this.group.updateMatrixWorld(true);
    const seed = this.opts.seed;
    const animHips = this._hips();
    const spineDir = this._dir("Hips", "Neck");
    const up = this._dir("Neck", "Head");
    // legs as the animation has them: the ankles are where the feet are planted
    const animLegs = { L: this._legChain(animHips, "L"), R: this._legChain(animHips, "R") };
    // weight shift + breathing (strongest when standing idle)
    const sway = noise1(t * 0.17, seed) * 0.032 * idleW;
    const breath = Math.sin(t * Math.PI * 2 * 0.27 + seed);
    const hips = animHips.clone().add(new THREE.Vector3(sway, -(0.014 + Math.abs(sway) * 0.3) * idleW, 0));
    const lean = spineDir.clone().add(new THREE.Vector3(-sway * 0.6, 0, 0.02 * idleW)).normalize();
    const chest = hips.clone().addScaledVector(lean, this.P.len.spine).addScaledVector(up, 0.006 * breath);
    // legs: IK from the (shifted) hips to the planted ankles, knees bending the way the animation bends them
    const legs = {};
    for (const sd of ["L", "R"]) {
      const [, k0, an] = animLegs[sd];
      const hp = hips.clone().addScaledVector(this._dir("Hips", `UpperLeg.${sd}`), this.P.len.hip);
      // knees bend forward (the way the body faces), following the animation's bend only in depth
      const bend = k0.clone().sub(an.clone().add(animLegs[sd][0]).multiplyScalar(0.5));
      const pole = new THREE.Vector3(bend.x * 0.15, 0, Math.max(0.05, bend.z + 0.05));
      const [kn, ank] = Stickman.ik(hp, an, this.P.len.upperLeg, this.P.len.lowerLeg, pole, 0.985);
      legs[sd] = [hp, kn, ank];
    }
    // arms: animation, then a relaxed hang when idle, beats that follow the voice, then gestures
    const em = this._emphasis(actor, t);
    const talking = clamp(em * 2.2);
    const arms = {};
    const busy = { L: 0, R: 0 };
    const landmarks = { chest, headC: chest.clone().addScaledVector(up, this.P.len.neck + this.P.headR * 0.92), hips };
    for (const g of actor.gestures ?? []) {
      const dur = g.dur ?? 1.8;
      if (t < g.t - 0.05 || t > g.t + dur + 0.4) continue;
      const tgt = g.target && ctx.resolve ? ctx.resolve(g.target, this.group) : null;
      for (const sd of this._sides(g, tgt)) busy[sd] = Math.max(busy[sd], clamp((t - g.t) / 0.4) * clamp((g.t + dur + 0.4 - t) / 0.4));
    }
    for (const sd of ["L", "R"]) {
      const sg = sd === "L" ? 1 : -1;
      let [sh, el, wr] = this._armChain(chest, sd);
      sh.addScaledVector(up, 0.004 * breath);
      const free = 1 - busy[sd];
      // relaxed hang: hands slightly forward and out, elbows soft, a slow swing
      // arms the animation holds out from the body (a chibi pack idle stands with them ~45 degrees out) hang more
      const out = wr.clone().sub(sh).normalize().angleTo(new THREE.Vector3(0, -1, 0));
      const hangW = idleW * (0.65 + 0.25 * clamp((out - 0.45) / 0.5)) * free;
      if (hangW > 0.01) {
        const swing = noise1(t * 0.35 + (sg > 0 ? 0 : 9), seed) * 0.03;
        const T = sh.clone().add(new THREE.Vector3(sg * 0.06, -0.55, 0.05 + swing).multiplyScalar(this.P.k));
        const [E, H] = Stickman.ik(sh, T, this.P.len.upperArm, this.P.len.lowerArm, new THREE.Vector3(sg * 0.12, 0, -1));
        el = el.lerp(E, hangW); wr = wr.lerp(H, hangW);
      }
      // talking beats: the hands lift and settle with the stress of the speech (right hand leads)
      const beatW = talking * free * (sd === "R" ? 0.55 : 0.35);
      if (beatW > 0.01) {
        const lift = this._emphasis(actor, t - (sd === "R" ? 0 : 0.12));
        const T = chest.clone().add(new THREE.Vector3(sg * 0.24, -0.33 + 0.16 * lift, 0.22 + 0.05 * lift).multiplyScalar(this.P.k));
        const [E, H] = Stickman.ik(sh, T, this.P.len.upperArm, this.P.len.lowerArm, new THREE.Vector3(sg, -1, -0.3));
        el = el.lerp(E, beatW); wr = wr.lerp(H, beatW);
      }
      arms[sd] = [sh, el, wr];
    }
    for (const g of actor.gestures ?? []) {
      const dur = g.dur ?? 1.8;
      const kin = clamp((t - g.t) / 0.42), kout = clamp((g.t + dur - t) / 0.4);
      if (kin <= 0 || kout <= 0) continue;
      const k = ease("outBackSoft", kin) * ease("inOutSine", kout);
      const tgt = g.target && ctx.resolve ? ctx.resolve(g.target, this.group) : null;
      for (const sd of this._sides(g, tgt)) {
        const sg = sd === "L" ? 1 : -1;
        const [sh, el, wr] = arms[sd];
        const [T, pole] = this._gestureTarget(g, sg, { ...landmarks, sh }, t, tgt);
        const [E, H] = Stickman.ik(sh, T, this.P.len.upperArm, this.P.len.lowerArm, pole);
        arms[sd] = [sh, el.clone().lerp(E, k), wr.clone().lerp(H, k)];
      }
    }
    return { hips, chest, up, lean, legs, arms, breath, em, idleW, sway };
  }

  _sides(g, tgt) {
    if (g.side === "both" || (["hips", "crossed", "shrug", "cheer"].includes(g.gesture) && !g.side)) return ["L", "R"];
    return [g.side ?? (tgt ? (tgt.x >= 0 ? "L" : "R") : "R")];
  }

  update(actor, t, ctx = {}) {
    // overlap / follow-through: elbows and hands trail the body a little (the pose a moment ago is mixed in)
    const back = (dt) => this._pose(actor, Math.max(0, t - dt), { ...ctx, dist: Math.max(0, (ctx.dist ?? 0) - (ctx.speed ?? 0) * dt) });
    const P2 = back(0.14), P1 = back(0.07);
    const P = this._pose(actor, t, ctx);
    const trail = (sd, i, w0, w1, w2) => P.arms[sd][i].clone().multiplyScalar(w0).addScaledVector(P1.arms[sd][i], w1).addScaledVector(P2.arms[sd][i], w2);
    for (const sd of ["L", "R"]) {
      const [sh] = P.arms[sd];
      const elB = trail(sd, 1, 0.72, 0.2, 0.08), wrB = trail(sd, 2, 0.52, 0.3, 0.18);
      const el = sh.clone().addScaledVector(elB.sub(sh).normalize(), this.P.len.upperArm);
      const wr = el.clone().addScaledVector(wrB.sub(el).normalize(), this.P.len.lowerArm);
      P.arms[sd] = [sh, el, wr];
    }
    const { hips, chest, up, lean, legs, arms } = P;
    this.hands = { L: arms.L[2], R: arms.R[2] };
    const neckTop = chest.clone().addScaledVector(up, this.P.len.neck);
    const headC = neckTop.clone().addScaledVector(up, this.P.headR * 0.92);
    const J = this.joints;
    const fwd = lean.clone().cross(this._dir("UpperLeg.R", "UpperLeg.L")).normalize();
    if (this.bendy) {
      const T = this.tubes, mid = (a, b, bend = 0) => a.clone().lerp(b, 0.5).addScaledVector(fwd, bend);
      T.spine.update(hips, mid(hips, chest, 0.012 + 0.01 * P.breath), chest, this.P.spineR * 1.05, this.P.spineR * 0.95, fwd);
      const neckR = this.P.neckR ?? this.P.limbR * 0.95;
      T.neck.update(chest, mid(chest, headC), headC, neckR, neckR * 0.9, fwd);
      for (const sd of ["L", "R"]) {
        const [sh, el, wr] = arms[sd], [hp, kn, an] = legs[sd];
        T[`arm${sd}`].update(sh, el, wr, this.P.limbR * 1.05, this.P.limbR * 0.85, fwd);
        T[`leg${sd}`].update(hp, kn, an, this.P.limbR * 1.15, this.P.limbR * 0.9, fwd);
        T[`sh${sd}`].update(chest, mid(chest, sh), sh, this.P.shoulderR ?? this.P.limbR, this.P.shoulderR ? this.P.limbR * 1.05 : this.P.limbR, fwd);
        T[`hp${sd}`].update(hips, mid(hips, hp), hp, this.P.limbR * 1.1, this.P.limbR * 1.1, fwd);
      }
    } else {
      const seg = (m, a, b) => {
        const d = b.clone().sub(a), len = d.length();
        m.position.copy(a).addScaledVector(d, 0.5);
        m.scale.set(1, Math.max(1e-4, len), 1);
        m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
      };
      const S = this.segs;
      seg(S.spine, hips, chest); seg(S.neck, chest, neckTop.clone().addScaledVector(up, this.P.headR * 0.3));
      seg(S.uaL, arms.L[0], arms.L[1]); seg(S.laL, arms.L[1], arms.L[2]); seg(S.uaR, arms.R[0], arms.R[1]); seg(S.laR, arms.R[1], arms.R[2]);
      seg(S.ulL, legs.L[0], legs.L[1]); seg(S.llL, legs.L[1], legs.L[2]); seg(S.ulR, legs.R[0], legs.R[1]); seg(S.llR, legs.R[1], legs.R[2]);
      seg(S.shL, chest, arms.L[0]); seg(S.shR, chest, arms.R[0]); seg(S.hpL, hips, legs.L[0]); seg(S.hpR, hips, legs.R[0]);
      J.elL.position.copy(arms.L[1]); J.elR.position.copy(arms.R[1]); J.knL.position.copy(legs.L[1]); J.knR.position.copy(legs.R[1]);
    }
    J.hips.position.copy(hips); J.chest.position.copy(chest);
    J.shL.position.copy(arms.L[0]); J.shR.position.copy(arms.R[0]); J.hpL.position.copy(legs.L[0]); J.hpR.position.copy(legs.R[0]);
    J.handL.position.copy(arms.L[2]); J.handR.position.copy(arms.R[2]);
    for (const [f, an] of [[J.footL, legs.L[2]], [J.footR, legs.R[2]]]) {
      f.position.copy(an).addScaledVector(fwd, 0.035).add(new THREE.Vector3(0, -0.012, 0));
      f.rotation.set(0, Math.atan2(fwd.x, fwd.z), 0);
    }
    // head: the rig's head rotation, then look-at, then life (nods with the speech, small glances, a tilt)
    this.head.quaternion.copy(this._headQuat());
    this.head.position.copy(headC);
    const lk = this._look(actor.look, t, ctx, headC, actor.gaze_max ?? 1.0);
    if (lk) this.head.quaternion.premultiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(lk.pitch, lk.yaw, 0, "YXZ")));
    const seed = this.opts.seed;
    const e = this._expression(actor.face, actor.talk, t, actor.mouth);
    const nod = 0.09 * (this._emphasis(actor, t) - this._emphasis(actor, t - 0.25));
    const glance = noise1(t * 0.31, seed + 2) * 0.07, tilt = noise1(t * 0.23, seed + 3) * 0.045 + (e.tilt ?? 0);
    this.head.quaternion.multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(nod + 0.015 * P.breath, glance, tilt - P.sway * 1.2, "YXZ")));
    if (ctx.ink && !actor.color && !this.fixedColors) this.mat.color.copy(ctx.ink);
    this._face(e);
    this.decorate?.({ hips, chest, up, fwd, headC, arms, legs, t });
  }

  _look(track, t, ctx, headC, maxYaw = 1.0) {
    if (!track?.length) return null;
    const angles = (key) => {
      if (!key || key.at === "none") return { yaw: 0, pitch: 0 };
      const named = { left: [0.9, 0], right: [-0.9, 0], up: [0, -0.35], down: [0, 0.35] }[key.at];
      if (named) return { yaw: named[0], pitch: named[1] };
      const w = ctx.resolve ? ctx.resolve(key.at, this.group) : null;
      if (!w) return { yaw: 0, pitch: 0 };
      const d = w.clone().sub(headC);
      return { yaw: clamp(Math.atan2(d.x, d.z), -maxYaw, maxYaw), pitch: clamp(-Math.atan2(d.y, Math.hypot(d.x, d.z)), -0.45, 0.45) };
    };
    const [prev, cur, w] = stepFade(track, t, 0.4);
    const a = angles(prev), b = angles(cur), k = ease("inOutSine", w);
    return { yaw: lerp(a.yaw, b.yaw, k), pitch: lerp(a.pitch, b.pitch, k) };
  }

  _face(e) {
    const r = this.P.headR;
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
    const my = this.mouthY ?? -r * 0.36;
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
