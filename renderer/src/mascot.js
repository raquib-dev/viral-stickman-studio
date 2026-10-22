// A small mascot character (the "AI" in dialogue shorts): a faceted, lobed body with two rectangle eyes and
// stubby feet. It has no mouth: it talks by squashing and bobbing with its voice, and its eyes carry the
// expression. Pure in t, like the stick figure. Same interface as Stickman for the main loop:
// group, update(spec, t, ctx), headWorld(), headY, size, hands (none), mat.
import * as THREE from "three";
import { clamp, ease, hash, lerp, noise1, stepFade } from "./util.js";

export const MASCOT_SHAPES = ["flower", "star", "blob", "bean"];

// eye shape per expression: height, width, vertical offset, tilt (radians, inner corners down when > 0)
const EYES = {
  neutral: { h: 1, w: 1, y: 0, tilt: 0 },
  happy: { h: 0.58, w: 1.1, y: 0.18, tilt: 0 },
  surprised: { h: 1.25, w: 1.2, y: 0.05, tilt: 0 },
  sad: { h: 0.7, w: 1, y: -0.15, tilt: -0.35 },
  angry: { h: 0.6, w: 1.1, y: 0, tilt: 0.4 },
  confused: { h: 0.85, w: 1, y: 0, tilt: 0.2 },
  thinking: { h: 0.75, w: 1, y: 0.2, tilt: 0 },
  skeptical: { h: 0.32, w: 1.1, y: 0, tilt: 0 },   // flat slits: the deadpan look
};

function lobedGeometry(shape, R) {
  const g = new THREE.IcosahedronGeometry(1, 3);
  const p = g.attributes.position;
  const lobes = { flower: [6, 0.13], star: [5, 0.2], blob: [0, 0], bean: [0, 0] }[shape] ?? [6, 0.13];
  for (let i = 0; i < p.count; i++) {
    let x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    const phi = Math.atan2(y, x);
    const rim = 1 - Math.abs(z) * 0.55;            // the lobes show from the front; the back stays round
    const f = 1 + lobes[1] * Math.cos(lobes[0] * phi + Math.PI / 2) * rim;
    x *= f; y *= f;
    if (shape === "bean") { x *= 0.85; y *= 1.18; }
    p.setXYZ(i, x * R, y * R, z * R * 0.78);
  }
  g.computeVertexNormals();
  return g;
}

export class Mascot {
  constructor(opts = {}) {
    const ap = { color: "#e8743c", eyes: "#141012", shape: "flower", ...(opts.appearance ?? {}) };
    this.opts = { seed: 1, ...opts };
    this.R = 0.13 * (ap.scale ?? 1);
    this.group = new THREE.Group();
    this.body = new THREE.Group();          // bobs and squashes above the planted feet
    this.group.add(this.body);
    this.mat = new THREE.MeshStandardMaterial({ color: ap.color, roughness: 0.55, metalness: 0, flatShading: true });
    const R = this.R;
    const blob = new THREE.Mesh(lobedGeometry(ap.shape, R), this.mat);
    blob.castShadow = true;
    blob.position.y = R * 1.18;
    this.body.add(blob);
    const eyeMat = new THREE.MeshStandardMaterial({ color: ap.eyes, roughness: 0.35 });
    this.eyes = [-1, 1].map((sx) => {
      const e = new THREE.Mesh(new THREE.BoxGeometry(R * 0.17, R * 0.42, R * 0.08), eyeMat);
      e.userData.sx = sx;
      this.body.add(e);
      return e;
    });
    this.feet = [-1, 1].map((sx) => {
      const f = new THREE.Mesh(new THREE.IcosahedronGeometry(R * 0.3, 1), this.mat);
      f.scale.set(1.05, 0.62, 1.15);
      f.position.set(sx * R * 0.42, R * 0.15, R * 0.12);
      f.castShadow = true;
      this.group.add(f);
      return f;
    });
    this.headY = R * 1.25;      // the face centre, for camera shots
    this.size = 0.5;            // relative to the stick figure: a close-up shows it at about half the frame
    this.hands = null;
    this.blinks = [];
    for (let t = 0.9 + hash(3, this.opts.seed) * 1.4, k = 0; t < 600; k++) {
      this.blinks.push(t);
      t += 2.2 + hash(k + 7, this.opts.seed) * 2.4;
    }
  }

  _speak(actor, t) {
    const m = actor.mouth;
    if (m?.values?.length) {
      const i = Math.floor(t * (m.fps ?? 24));
      return clamp(m.values[Math.min(m.values.length - 1, Math.max(0, i))] ?? 0);
    }
    return 0;
  }

  /** Speech energy smoothed over ~0.2 s (a bounce, not a buzz). */
  _energy(actor, t) {
    let s = 0;
    for (let k = 0; k < 5; k++) s += this._speak(actor, t - k * 0.04);
    return s / 5;
  }

  update(actor, t, ctx = {}) {
    const R = this.R, seed = this.opts.seed;
    // expression
    const faces = actor.face?.length ? actor.face : [{ t: 0, expr: "neutral" }];
    const [prev, cur, w] = stepFade(faces, t, 0.2);
    const A = EYES[prev.expr] ?? EYES.neutral, B = EYES[cur.expr] ?? EYES.neutral;
    const e = Object.fromEntries(Object.keys(A).map((k) => [k, lerp(A[k], B[k], w)]));
    let blink = 1;
    for (const bt of this.blinks) {
      const d = Math.abs(t - bt);
      if (d < 0.08) blink = Math.min(blink, 0.1 + (d / 0.08) * 0.9);
    }
    // speaking: squash and stretch with the voice, a small bob
    const en = this._energy(actor, t);
    const idle = Math.sin(t * Math.PI * 2 * 0.45 + seed) * 0.5 + 0.5;
    let hop = 0;
    for (const g of actor.gestures ?? []) {
      if (g.gesture !== "cheer") continue;               // a little hop of joy
      const k = (t - g.t) / 0.5;
      if (k > 0 && k < 1) hop = Math.max(hop, Math.sin(k * Math.PI));
    }
    this.body.scale.set(1 - 0.035 * en, 1 + 0.07 * en + 0.012 * idle, 1 - 0.035 * en);
    this.body.position.y = R * (0.04 * idle + 0.35 * en * en) + hop * R * 0.9;
    // turn toward what it looks at (another actor, the camera), never fully away from the camera
    let yaw = 0;
    const looks = actor.look?.length ? actor.look : null;
    if (looks && ctx.resolve) {
      const [pl, cl, lw] = stepFade(looks, t, 0.35);
      const ang = (key) => {
        const p = key && key.at !== "none" ? ctx.resolve(key.at, this.group) : null;
        return p ? clamp(Math.atan2(p.x, p.z), -0.6, 0.6) : 0;
      };
      yaw = lerp(ang(pl), ang(cl), ease("inOutSine", lw));
    }
    this.body.rotation.set(0.04 * en - 0.03 * hop, yaw + noise1(t * 0.3, seed) * 0.05, noise1(t * 0.25, seed + 4) * 0.03);
    // eyes on the front surface
    const eyeY = R * (1.24 + 0.18 * e.y), gap = R * 0.24;
    for (const eye of this.eyes) {
      const sx = eye.userData.sx;
      eye.position.set(sx * gap, eyeY, R * 0.79);
      eye.scale.set(e.w, Math.max(0.06, e.h * blink), 1);
      eye.rotation.set(0, 0, sx * e.tilt * 0.5);
    }
  }

  headWorld(out = new THREE.Vector3()) {
    return this.body.localToWorld(out.set(0, this.headY, 0));
  }
}
