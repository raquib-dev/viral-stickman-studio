// Low-poly prop library. Props are built from primitives in code, share palette-driven materials (so they
// re-colour with the mood), and have named parts for the motions in animateProp (pop, drop, grow, spin,
// bob, pulse, shake) and a "grip" point where a character can hold them.
import * as THREE from "three";
import { clamp, ease, noise1 } from "./util.js";

export function propMaterials() {
  const std = (o = {}) => new THREE.MeshStandardMaterial({ flatShading: true, roughness: 0.6, metalness: 0, ...o });
  const m = {
    accent: std(), ink: std(), card: std({ roughness: 0.8 }), dark: std({ roughness: 0.4 }),
    metal: std({ roughness: 0.3, metalness: 0.6 }), gold: std({ roughness: 0.3, metalness: 0.7 }),
    wood: std({ roughness: 0.8 }), green: std(), red: std(), glow: new THREE.MeshBasicMaterial({ toneMapped: false }),
    screen: new THREE.MeshBasicMaterial({ toneMapped: false }), glass: std({ transparent: true, opacity: 0.35, roughness: 0.1 }),
  };
  m.apply = (p) => {
    m.accent.color.copy(p.accent); m.ink.color.copy(p.ink); m.card.color.copy(p.card); m.dark.color.copy(p.bg).lerp(p.ink, 0.12);
    m.metal.color.copy(p.ink).multiplyScalar(0.6); m.gold.color.set("#e2b13c").lerp(p.accent, 0.15); m.wood.color.copy(p.floor).lerp(new THREE.Color("#8a5a35"), 0.5);
    m.green.color.set("#58b368").lerp(p.accent, 0.1); m.red.color.set("#e04b3c"); m.glow.color.copy(p.glow).multiplyScalar(1.8);
    m.screen.color.copy(p.accent).lerp(p.card, 0.35).multiplyScalar(1.15); m.glass.color.copy(p.fill);
  };
  return m;
}

const G = {
  box: (w, h, d) => new THREE.BoxGeometry(w, h, d), cyl: (r1, r2, h, n = 8) => new THREE.CylinderGeometry(r1, r2, h, n),
  ico: (r, d = 0) => new THREE.IcosahedronGeometry(r, d), cone: (r, h, n = 8) => new THREE.ConeGeometry(r, h, n),
  torus: (r, t, arc = Math.PI * 2) => new THREE.TorusGeometry(r, t, 5, 12, arc),
};

function part(g, geo, mat, pos = [0, 0, 0], rot = [0, 0, 0], name) {
  const m = new THREE.Mesh(geo, mat);
  m.position.set(...pos); m.rotation.set(...rot);
  m.castShadow = true; m.receiveShadow = true;
  if (name) m.name = name;
  g.add(m);
  return m;
}

function extrudeShape(shape, depth) {
  return new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false, curveSegments: 6 });
}

function heartShape(s) {
  const h = new THREE.Shape();
  h.moveTo(0, -s * 0.9);
  h.bezierCurveTo(s * 1.3, -s * 0.1, s * 0.9, s, 0, s * 0.45);
  h.bezierCurveTo(-s * 0.9, s, -s * 1.3, -s * 0.1, 0, -s * 0.9);
  return h;
}

function arrowShape(s) {
  const a = new THREE.Shape();
  a.moveTo(-s * 0.18, -s); a.lineTo(s * 0.18, -s); a.lineTo(s * 0.18, s * 0.1); a.lineTo(s * 0.45, s * 0.1);
  a.lineTo(0, s); a.lineTo(-s * 0.45, s * 0.1); a.lineTo(-s * 0.18, s * 0.1); a.closePath();
  return a;
}

// Every builder adds parts to g (origin = bottom centre, +Z toward the camera) and may set g.userData.grip.
export const PROPS = {
  desk: (g, m) => { part(g, G.box(1.4, 0.06, 0.7), m.wood, [0, 0.74, 0]); for (const x of [-0.62, 0.62]) for (const z of [-0.28, 0.28]) part(g, G.box(0.05, 0.72, 0.05), m.wood, [x, 0.36, z]); },
  chair: (g, m) => { part(g, G.box(0.45, 0.05, 0.45), m.accent, [0, 0.46, 0]); part(g, G.box(0.45, 0.5, 0.05), m.accent, [0, 0.72, -0.2]); for (const x of [-0.19, 0.19]) for (const z of [-0.19, 0.19]) part(g, G.box(0.04, 0.46, 0.04), m.metal, [x, 0.23, z]); },
  laptop: (g, m) => { part(g, G.box(0.42, 0.02, 0.3), m.metal, [0, 0.01, 0]); const lid = part(g, G.box(0.42, 0.28, 0.015), m.metal, [0, 0.15, -0.15], [-0.25, 0, 0], "lid"); part(lid, G.box(0.38, 0.24, 0.002), m.screen, [0, 0, 0.009]); },
  monitor: (g, m) => { part(g, G.box(0.9, 0.55, 0.04), m.dark, [0, 0.55, 0]); part(g, G.box(0.84, 0.49, 0.01), m.screen, [0, 0.55, 0.022]); part(g, G.box(0.06, 0.28, 0.06), m.metal, [0, 0.14, -0.02]); part(g, G.box(0.3, 0.02, 0.2), m.metal, [0, 0.01, 0]); },
  phone: (g, m) => { part(g, G.box(0.09, 0.18, 0.012), m.dark, [0, 0.09, 0]); part(g, G.box(0.08, 0.16, 0.002), m.screen, [0, 0.09, 0.007]); g.userData.grip = [0, 0.06, 0]; },
  mug: (g, m) => { part(g, G.cyl(0.06, 0.055, 0.12, 8), m.accent, [0, 0.06, 0]); part(g, G.torus(0.035, 0.012, Math.PI), m.accent, [0.065, 0.06, 0], [0, 0, -Math.PI / 2]); g.userData.grip = [0.07, 0.06, 0]; },
  lamp: (g, m) => { part(g, G.cyl(0.1, 0.12, 0.03), m.metal, [0, 0.015, 0]); part(g, G.cyl(0.015, 0.015, 0.4, 6), m.metal, [0, 0.22, 0]); part(g, G.cone(0.14, 0.16, 8), m.accent, [0, 0.46, 0]); part(g, G.ico(0.04), m.glow, [0, 0.4, 0]); },
  plant: (g, m) => { part(g, G.cyl(0.13, 0.1, 0.22, 7), m.card, [0, 0.11, 0]); for (let k = 0; k < 5; k++) part(g, G.ico(0.13), m.green, [Math.sin(k * 1.3) * 0.08, 0.3 + k * 0.07, Math.cos(k * 1.7) * 0.06]); },
  books: (g, m) => { [m.accent, m.ink, m.card, m.red].forEach((mat, k) => part(g, G.box(0.32 - k * 0.02, 0.06, 0.22), mat, [0, 0.03 + k * 0.062, 0], [0, k * 0.12, 0])); },
  clock: (g, m) => { part(g, G.cyl(0.25, 0.25, 0.05, 16), m.card, [0, 0, 0], [Math.PI / 2, 0, 0]); part(g, G.torus(0.25, 0.025), m.accent); part(g, G.box(0.02, 0.17, 0.01), m.dark, [0, 0.07, 0.03], [0, 0, 0], "hand_m"); part(g, G.box(0.025, 0.11, 0.01), m.dark, [0, 0.045, 0.035], [0, 0, 0], "hand_h"); },
  hourglass: (g, m) => { part(g, G.cone(0.12, 0.2, 8), m.glass, [0, 0.12, 0], [Math.PI, 0, 0]); part(g, G.cone(0.12, 0.2, 8), m.glass, [0, 0.32, 0]); part(g, G.cone(0.08, 0.1, 8), m.gold, [0, 0.07, 0], [Math.PI, 0, 0]); for (const y of [0, 0.44]) part(g, G.cyl(0.15, 0.15, 0.03, 8), m.wood, [0, y, 0]); },
  bulb: (g, m) => { part(g, G.ico(0.17, 1), m.glow, [0, 0.3, 0]); part(g, G.cyl(0.07, 0.07, 0.12, 8), m.metal, [0, 0.08, 0]); g.userData.light = true; },
  chart: (g, m) => { [0.25, 0.4, 0.62, 0.9].forEach((h, k) => part(g, G.box(0.14, h, 0.14), k === 3 ? m.accent : m.card, [-0.27 + k * 0.18, h / 2, 0], [0, 0, 0], `bar${k}`)); const ar = part(g, extrudeShape(arrowShape(0.18), 0.03), m.accent, [0.36, 1.08, 0], [0, 0, -0.6], "arrow"); ar.scale.setScalar(0.9); },
  arrow_up: (g, m) => { part(g, extrudeShape(arrowShape(0.3), 0.06), m.green, [0, 0.3, 0]); },
  arrow_down: (g, m) => { part(g, extrudeShape(arrowShape(0.3), 0.06), m.red, [0, 0.3, 0], [0, 0, Math.PI]); },
  trophy: (g, m) => { part(g, G.box(0.22, 0.06, 0.22), m.dark, [0, 0.03, 0]); part(g, G.cyl(0.03, 0.03, 0.14, 6), m.gold, [0, 0.13, 0]); part(g, G.cyl(0.14, 0.06, 0.2, 8), m.gold, [0, 0.3, 0]); for (const s of [-1, 1]) part(g, G.torus(0.06, 0.015, Math.PI), m.gold, [s * 0.14, 0.32, 0], [0, 0, s > 0 ? -Math.PI / 2 : Math.PI / 2]); },
  coin: (g, m) => { part(g, G.cyl(0.14, 0.14, 0.03, 12), m.gold, [0, 0.14, 0], [Math.PI / 2, 0, 0], "face"); },
  coins: (g, m) => { for (let k = 0; k < 6; k++) part(g, G.cyl(0.1, 0.1, 0.025, 10), m.gold, [Math.sin(k) * 0.01, 0.0125 + k * 0.027, 0]); for (let k = 0; k < 4; k++) part(g, G.cyl(0.1, 0.1, 0.025, 10), m.gold, [0.22, 0.0125 + k * 0.027, 0.05]); },
  moneybag: (g, m) => { part(g, G.ico(0.22, 1), m.card, [0, 0.22, 0]); part(g, G.cone(0.1, 0.14, 7), m.card, [0, 0.47, 0], [Math.PI, 0, 0]); part(g, G.torus(0.06, 0.015), m.accent, [0, 0.42, 0], [Math.PI / 2, 0, 0]); part(g, G.box(0.1, 0.12, 0.02), m.accent, [0, 0.22, 0.21]); g.userData.grip = [0, 0.45, 0]; },
  piggybank: (g, m) => { part(g, G.ico(0.22, 1), m.accent, [0, 0.25, 0]); part(g, G.cyl(0.06, 0.06, 0.06, 8), m.accent, [0, 0.25, 0.23], [Math.PI / 2, 0, 0]); for (const x of [-0.1, 0.1]) for (const z of [-0.1, 0.1]) part(g, G.cyl(0.035, 0.035, 0.1, 6), m.accent, [x, 0.05, z]); part(g, G.box(0.08, 0.01, 0.02), m.dark, [0, 0.47, 0]); },
  rocket: (g, m) => { part(g, G.cyl(0.12, 0.12, 0.5, 8), m.card, [0, 0.35, 0]); part(g, G.cone(0.12, 0.22, 8), m.accent, [0, 0.71, 0]); for (let k = 0; k < 3; k++) part(g, G.box(0.02, 0.16, 0.12), m.accent, [Math.sin(k * 2.09) * 0.12, 0.16, Math.cos(k * 2.09) * 0.12], [0, k * 2.09, 0]); part(g, G.cyl(0.04, 0.04, 0.02, 8), m.glass, [0, 0.45, 0.12], [Math.PI / 2, 0, 0]); part(g, G.cone(0.08, 0.2, 7), m.glow, [0, 0.0, 0], [Math.PI, 0, 0], "flame"); },
  house: (g, m) => { part(g, G.box(0.7, 0.5, 0.6), m.card, [0, 0.25, 0]); part(g, G.cone(0.58, 0.35, 4), m.accent, [0, 0.67, 0], [0, Math.PI / 4, 0]); part(g, G.box(0.14, 0.24, 0.02), m.wood, [0, 0.12, 0.31]); part(g, G.box(0.14, 0.14, 0.02), m.glow, [0.2, 0.3, 0.31]); },
  gift: (g, m) => { part(g, G.box(0.36, 0.3, 0.36), m.accent, [0, 0.15, 0]); part(g, G.box(0.38, 0.06, 0.38), m.accent, [0, 0.33, 0], [0, 0, 0], "lid"); part(g, G.box(0.06, 0.37, 0.39), m.gold, [0, 0.18, 0]); part(g, G.box(0.39, 0.37, 0.06), m.gold, [0, 0.18, 0]); },
  heart: (g, m) => { part(g, extrudeShape(heartShape(0.2), 0.08), m.red, [0, 0.25, -0.04]); },
  warning: (g, m) => { const s = new THREE.Shape(); s.moveTo(0, 0.4); s.lineTo(0.35, -0.2); s.lineTo(-0.35, -0.2); s.closePath(); part(g, extrudeShape(s, 0.05), m.accent, [0, 0.25, 0]); part(g, G.box(0.05, 0.2, 0.06), m.dark, [0, 0.3, 0.02]); part(g, G.box(0.05, 0.05, 0.06), m.dark, [0, 0.12, 0.02]); },
  question: (g, m) => { part(g, G.torus(0.13, 0.04, Math.PI * 1.4), m.accent, [0, 0.55, 0], [0, 0, -0.4]); part(g, G.box(0.08, 0.14, 0.08), m.accent, [0.01, 0.33, 0]); part(g, G.ico(0.05), m.accent, [0.01, 0.16, 0]); },
  exclamation: (g, m) => { part(g, G.box(0.09, 0.36, 0.09), m.accent, [0, 0.42, 0]); part(g, G.ico(0.06), m.accent, [0, 0.12, 0]); },
  target: (g, m) => { [0.32, 0.22, 0.12].forEach((r, k) => part(g, G.cyl(r, r, 0.03 + k * 0.01, 16), k % 2 ? m.card : m.red, [0, 0.35, k * 0.012], [Math.PI / 2, 0, 0])); part(g, G.cyl(0.015, 0.015, 0.4, 6), m.wood, [0.06, 0.38, 0.18], [Math.PI / 2.4, 0, 0], "dart"); },
  key: (g, m) => { part(g, G.torus(0.08, 0.025), m.gold, [0, 0.3, 0]); part(g, G.box(0.04, 0.26, 0.03), m.gold, [0, 0.1, 0]); part(g, G.box(0.07, 0.03, 0.03), m.gold, [0.04, 0.02, 0]); part(g, G.box(0.05, 0.03, 0.03), m.gold, [0.03, 0.07, 0]); g.userData.grip = [0, 0.3, 0]; },
  lock: (g, m) => { part(g, G.box(0.3, 0.26, 0.12), m.gold, [0, 0.13, 0]); part(g, G.torus(0.1, 0.025, Math.PI), m.metal, [0, 0.27, 0], [0, 0, 0], "shackle"); part(g, G.cyl(0.025, 0.025, 0.13, 6), m.dark, [0, 0.13, 0.06], [Math.PI / 2, 0, 0]); },
  calendar: (g, m) => { part(g, G.box(0.42, 0.42, 0.03), m.card, [0, 0.21, 0]); part(g, G.box(0.42, 0.1, 0.035), m.red, [0, 0.38, 0]); for (let r = 0; r < 3; r++) for (let c = 0; c < 4; c++) part(g, G.box(0.06, 0.05, 0.01), m.dark, [-0.14 + c * 0.095, 0.25 - r * 0.08, 0.02]); },
  scroll: (g, m) => { part(g, G.box(0.42, 0.55, 0.01), m.card, [0, 0.32, 0]); for (const y of [0.05, 0.6]) part(g, G.cyl(0.035, 0.035, 0.5, 8), m.wood, [0, y, 0], [0, 0, Math.PI / 2]); for (let k = 0; k < 4; k++) part(g, G.box(0.3 - (k % 2) * 0.08, 0.02, 0.012), m.dark, [0, 0.48 - k * 0.09, 0.006]); },
  crown: (g, m) => { part(g, G.cyl(0.16, 0.16, 0.1, 10, true), m.gold, [0, 0.05, 0]); for (let k = 0; k < 5; k++) part(g, G.cone(0.04, 0.1, 4), m.gold, [Math.sin(k * 1.257) * 0.15, 0.15, Math.cos(k * 1.257) * 0.15]); part(g, G.ico(0.03), m.red, [0, 0.06, 0.16]); },
  sword: (g, m) => { part(g, G.box(0.05, 0.6, 0.015), m.metal, [0, 0.45, 0]); part(g, G.box(0.2, 0.03, 0.04), m.gold, [0, 0.14, 0]); part(g, G.cyl(0.02, 0.02, 0.13, 6), m.wood, [0, 0.06, 0]); g.userData.grip = [0, 0.06, 0]; },
  shield: (g, m) => { part(g, G.cyl(0.3, 0.3, 0.05, 8), m.accent, [0, 0.35, 0], [Math.PI / 2, 0, 0]); part(g, G.torus(0.3, 0.025, Math.PI * 2), m.gold, [0, 0.35, 0.02]); part(g, G.ico(0.06), m.gold, [0, 0.35, 0.04]); },
  flag: (g, m) => { part(g, G.cyl(0.015, 0.015, 1.2, 6), m.wood, [0, 0.6, 0]); part(g, G.box(0.42, 0.28, 0.01), m.accent, [0.22, 1.04, 0], [0, 0, 0], "cloth"); },
  torch: (g, m) => { part(g, G.cyl(0.03, 0.02, 0.45, 6), m.wood, [0, 0.22, 0]); part(g, G.cone(0.07, 0.2, 6), m.glow, [0, 0.55, 0], [0, 0, 0], "flame"); g.userData.grip = [0, 0.15, 0]; g.userData.light = true; },
  rock: (g, m) => { part(g, new THREE.DodecahedronGeometry(0.25, 0), m.card, [0, 0.18, 0], [0.3, 0.6, 0]); },
  spear: (g, m) => { part(g, G.cyl(0.015, 0.015, 1.4, 6), m.wood, [0, 0.7, 0]); part(g, G.cone(0.04, 0.16, 4), m.card, [0, 1.47, 0]); g.userData.grip = [0, 0.7, 0]; },
  campfire: (g, m) => { for (let k = 0; k < 4; k++) part(g, G.cyl(0.04, 0.04, 0.45, 6), m.wood, [0, 0.05, 0], [Math.PI / 2, 0, k * Math.PI / 4]); part(g, G.cone(0.12, 0.35, 6), m.glow, [0, 0.2, 0], [0, 0, 0], "flame"); g.userData.light = true; },
  laptop_open: (g, m) => PROPS.laptop(g, m),
  briefcase: (g, m) => { part(g, G.box(0.42, 0.3, 0.12), m.wood, [0, 0.15, 0]); part(g, G.torus(0.05, 0.012, Math.PI), m.metal, [0, 0.31, 0]); g.userData.grip = [0, 0.33, 0]; },
  cart: (g, m) => { part(g, G.box(0.5, 0.25, 0.32), m.metal, [0, 0.32, 0]); for (const x of [-0.18, 0.18]) part(g, G.cyl(0.05, 0.05, 0.03, 8), m.dark, [x, 0.05, 0.16], [Math.PI / 2, 0, 0]); part(g, G.cyl(0.012, 0.012, 0.35, 6), m.metal, [0.28, 0.5, 0], [0, 0, -0.5]); },
};

export const PROP_TYPES = Object.keys(PROPS);

// ---- AI-drawn props (Phase 4) ------------------------------------------------------------------
// An AI-drawn prop is DATA: a list of low-poly shapes, each with a colour ROLE (never a free colour, so
// the prop takes the video's palette and mood) and an optional motion. The Python side validates and
// normalises it (assets.py); the renderer only builds what is listed here.
export const ASSET_SHAPES = ["box", "sphere", "ico", "cylinder", "cone", "torus", "capsule", "pyramid", "wedge"];
export const ASSET_COLORS = ["accent", "ink", "card", "dark", "metal", "gold", "wood", "green", "red", "glow", "glass"];
export const ASSET_MOTIONS = ["swing", "spin", "bob", "pulse", "flap"];

function shapeGeometry(shape, size) {
  const [a = 0.1, b = a, c = a] = size ?? [];
  switch (shape) {
    case "box": return new THREE.BoxGeometry(a, b, c);
    case "sphere": return new THREE.SphereGeometry(a, 8, 6);
    case "ico": return new THREE.IcosahedronGeometry(a, 0);
    case "cylinder": return new THREE.CylinderGeometry(a, b, c, 8);
    case "cone": return new THREE.ConeGeometry(a, b, 8);
    case "torus": return new THREE.TorusGeometry(a, b, 5, 12, c > 0 && c <= Math.PI * 2 ? c : Math.PI * 2);
    case "capsule": return new THREE.CapsuleGeometry(a, b, 3, 8);
    case "pyramid": return new THREE.ConeGeometry(a, b, 4);
    case "wedge": {
      const sh = new THREE.Shape();
      sh.moveTo(-a / 2, 0); sh.lineTo(a / 2, 0); sh.lineTo(-a / 2, b); sh.closePath();
      const g = new THREE.ExtrudeGeometry(sh, { depth: c, bevelEnabled: false });
      g.translate(0, -b / 2, -c / 2);
      return g;
    }
    default: return new THREE.IcosahedronGeometry(a, 0);
  }
}

function buildAsset(g, def, mats) {
  const D = Math.PI / 180;
  for (const pt of def.parts ?? []) {
    if (!ASSET_SHAPES.includes(pt.shape)) continue;
    const mat = mats[ASSET_COLORS.includes(pt.color) ? pt.color : "accent"];
    const m = new THREE.Mesh(shapeGeometry(pt.shape, pt.size), mat);
    const [rx = 0, ry = 0, rz = 0] = pt.rot ?? [];
    m.position.set(...(pt.pos ?? [0, 0, 0]));
    m.rotation.set(rx * D, ry * D, rz * D);
    if (pt.scale) m.scale.set(...pt.scale);
    m.castShadow = true; m.receiveShadow = true;
    m.userData.motion = ASSET_MOTIONS.includes(pt.motion?.type) ? pt.motion : null;
    m.userData.rest = { pos: m.position.clone(), rot: m.rotation.clone(), scale: m.scale.clone() };
    g.add(m);
  }
  if (def.grip) g.userData.grip = def.grip;
  if (def.glow) g.userData.light = true;
}

function animateAssetParts(inner, it, seed) {
  for (const m of inner.children) {
    const mo = m.userData.motion;
    if (!mo) continue;
    const r = m.userData.rest, w = Math.PI * 2 * (mo.speed ?? 0.8);
    const axis = ["x", "y", "z"].includes(mo.axis) ? mo.axis : "z";
    const amt = mo.amount ?? 20;
    m.position.copy(r.pos); m.rotation.copy(r.rot); m.scale.copy(r.scale);
    if (mo.type === "swing") m.rotation[axis] += Math.sin(it * w + seed) * amt * Math.PI / 180;
    if (mo.type === "flap") m.rotation[axis] += Math.abs(Math.sin(it * w + seed)) * amt * Math.PI / 180;
    if (mo.type === "spin") m.rotation[axis] += it * w;
    if (mo.type === "bob") m.position.y += Math.sin(it * w + seed) * (amt > 1 ? amt / 1000 : amt);
    if (mo.type === "pulse") m.scale.multiplyScalar(1 + 0.08 * Math.sin(it * w + seed));
  }
}

export function buildProp(spec, mats, assets = {}) {
  const g = new THREE.Group();
  const custom = typeof spec.type === "string" && spec.type.startsWith("custom:") ? assets[spec.type.slice(7)] : null;
  if (custom) buildAsset(g, custom, mats);
  else (PROPS[spec.type] ?? PROPS.question)(g, mats);
  const inner = new THREE.Group();
  inner.add(...g.children);
  inner.userData = g.userData;
  const outer = new THREE.Group();
  outer.add(inner);
  if (inner.userData.light) {
    const l = new THREE.PointLight("#ffffff", 1.2, 2.5, 2);
    l.position.set(0, 0.35, 0.1);
    outer.add(l);
    inner.userData.pointLight = l;
  }
  return { group: outer, inner, spec };
}

/** Prop motion at time t. `hand` = world position of the holding hand (if held). */
export function animateProp(p, t, seed, pal, hand) {
  const s = p.spec;
  const tin = s.t_in ?? 0, tout = s.t_out ?? Infinity;
  const kin = clamp((t - tin) / (s.enter_dur ?? 0.55)), kout = clamp((t - tout) / 0.35);
  p.group.visible = t >= tin && kout < 1;
  if (!p.group.visible) return;
  const sc = (s.scale ?? 1);
  const enter = s.enter ?? "pop";
  let scale = sc, dy = 0, spin = 0;
  if (enter === "pop") scale = sc * ease("outBack", kin);
  else if (enter === "grow") scale = sc * ease("outCubic", kin);
  else if (enter === "drop") dy = (1 - ease("outElastic", kin)) * 1.6;
  else if (enter === "spin") { scale = sc * ease("outBack", kin); spin = (1 - ease("outCubic", kin)) * Math.PI * 2; }
  scale *= 1 - ease("inOutCubic", kout);
  const idle = s.idle ?? "bob";
  const it = Math.max(0, t - tin);
  let bob = 0, rotY = 0, pulse = 1;
  if (idle === "bob") bob = 0.03 * Math.sin(it * 2.2 + seed);
  if (idle === "spin") rotY = it * 1.4;
  if (idle === "pulse") pulse = 1 + 0.06 * Math.sin(it * 5);
  if (idle === "shake") rotY = 0.12 * noise1(it * 14, seed);
  if (hand) {
    const grip = p.inner.userData.grip ?? [0, 0, 0];
    p.group.position.copy(hand).sub(new THREE.Vector3(...grip).multiplyScalar(scale));
  } else {
    const pos = s.pos ?? [0, 0, 0];
    p.group.position.set(pos[0], pos[1] + dy + bob, pos[2]);
  }
  const rot = s.rot ?? [0, 0, 0];
  p.group.rotation.set(rot[0], rot[1] + rotY + spin, rot[2]);
  p.group.scale.setScalar(Math.max(1e-4, scale * pulse));
  // per-prop details
  const find = (n) => p.inner.getObjectByName(n);
  const hm = find("hand_m"), hh = find("hand_h");
  if (hm) { hm.rotation.z = -it * 2.4; hm.position.set(Math.sin(it * 2.4) * 0.07, Math.cos(it * 2.4) * 0.07, 0.03); }
  if (hh) { hh.rotation.z = -it * 0.3; hh.position.set(Math.sin(it * 0.3) * 0.045, Math.cos(it * 0.3) * 0.045, 0.035); }
  animateAssetParts(p.inner, it, seed);
  const fl = find("flame");
  if (fl) fl.scale.set(1, 0.85 + 0.25 * Math.abs(noise1(it * 8, seed)), 1);
  for (let k = 0; k < 4; k++) {
    const bar = find(`bar${k}`);
    if (bar) bar.scale.y = Math.max(0.02, ease("outCubic", clamp((it - k * 0.12) / 0.6)));
  }
  if (p.inner.userData.pointLight) {
    p.inner.userData.pointLight.color.copy(pal.glow);
    p.inner.userData.pointLight.intensity = 1.2 * (0.85 + 0.15 * noise1(it * 6, seed));
  }
}
