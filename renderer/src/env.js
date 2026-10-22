// Sets for the style packs. Every set is low-poly and built in code (no downloads), and every colour in
// it comes from the palette, so a mood change re-colours the whole set live (apply(palette, t) runs every
// frame). Lights are shared by all sets.
import * as THREE from "three";
import catalog from "../catalog.json";
import { clamp, ease, hash, noise1 } from "./util.js";

const std = (opts = {}) => new THREE.MeshStandardMaterial({ flatShading: true, roughness: 0.8, metalness: 0, ...opts });

function add(parent, geo, mat, pos = [0, 0, 0], rot = [0, 0, 0], scale = 1, shadow = true) {
  const m = new THREE.Mesh(geo, mat);
  m.position.set(...pos);
  m.rotation.set(...rot);
  if (Array.isArray(scale)) m.scale.set(...scale); else m.scale.setScalar(scale);
  m.castShadow = shadow;
  m.receiveShadow = true;
  parent.add(m);
  return m;
}

/** Key, rim, fill, front and sky light; recoloured from the palette every frame. */
export function buildLights(scene) {
  const hemi = new THREE.HemisphereLight("#ffffff", "#222222", 0.6);
  const key = new THREE.DirectionalLight("#ffffff", 2.2);
  key.position.set(-1.6, 6.5, 3.2);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  Object.assign(key.shadow.camera, { left: -5, right: 5, top: 5, bottom: -2 });
  key.shadow.radius = 4;
  key.shadow.bias = -0.0004;
  const rim = new THREE.SpotLight("#ffffff", 28, 14, Math.PI / 6, 0.6, 1.4);
  rim.position.set(2.2, 3.4, -3.2);
  rim.target.position.set(0, 1.2, 0);
  const fill = new THREE.DirectionalLight("#ffffff", 0.5);
  fill.position.set(3, 2, 3);
  const front = new THREE.DirectionalLight("#ffffff", 0.55);
  front.position.set(0.5, 1.6, 6);
  scene.add(hemi, key, rim, rim.target, fill, front);
  return {
    apply(p, mult = {}, cols = null) {
      hemi.color.copy(p.key); hemi.groundColor.copy(p.floor);
      key.color.copy(p.key); rim.color.copy(p.rim); fill.color.copy(p.fill); front.color.copy(p.key);
      if (cols) {
        // a set's own light (daylight through a window, a dusk sky) replaces the palette's
        if (cols.key) { key.color.set(cols.key); front.color.set(cols.key); }
        if (cols.rim) rim.color.set(cols.rim);
        if (cols.fill) fill.color.set(cols.fill);
        if (cols.hemi) hemi.color.set(cols.hemi);
      }
      key.intensity = 2.2 * (mult.key ?? 1); rim.intensity = 28 * (mult.rim ?? 1);
      hemi.intensity = 0.6 * (mult.hemi ?? 1); front.intensity = 0.55 * (mult.front ?? 1);
    },
  };
}

function glowTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const g = c.getContext("2d");
  const rg = g.createRadialGradient(128, 128, 4, 128, 128, 128);
  rg.addColorStop(0, "rgba(255,255,255,1)"); rg.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = rg; g.fillRect(0, 0, 256, 256);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/** A soft additive glow sprite on the back wall (the "warm light behind the character"). */
function wallGlow(group, pos, size) {
  // subtle: in strong moods (danger red, success gold) a brighter glow floods the whole 9:16 background
  const m = new THREE.MeshBasicMaterial({ map: glowTexture(), transparent: true, opacity: 0.16, depthWrite: false,
    blending: THREE.AdditiveBlending, fog: false });
  const s = add(group, new THREE.PlaneGeometry(size, size), m, pos, [0, 0, 0], 1, false);
  s.receiveShadow = false;
  return m;
}

// ---- the six sets -------------------------------------------------------------------------------

function minimal(group) {
  // seamless studio: one flat colour for floor and wall, fog hides the seam
  const floorMat = std({ roughness: 0.95 });
  const floor = add(group, new THREE.PlaneGeometry(40, 30), floorMat, [0, 0, 3], [-Math.PI / 2, 0, 0], 1, false);
  const wall = add(group, new THREE.PlaneGeometry(40, 20), floorMat, [0, 10, -9], [0, 0, 0], 1, false);
  floor.castShadow = wall.castShadow = false;
  return { apply(p) { floorMat.color.copy(p.floor); }, lights: { rim: 0.5, hemi: 1.2 }, fog: [6, 22] };
}

function modern(group) {
  const floorMat = std({ roughness: 0.35, metalness: 0.15, flatShading: false });
  add(group, new THREE.CircleGeometry(30, 48), floorMat, [0, 0, 0], [-Math.PI / 2, 0, 0], 1, false);
  const wallMat = std({ roughness: 0.9 });
  add(group, new THREE.PlaneGeometry(26, 14), wallMat, [0, 6, -7], [0, 0, 0], 1, false);
  // LED strips on the back wall and a floor grid, lit by the accent colour
  const led = new THREE.MeshBasicMaterial({ toneMapped: false });
  for (let i = -5; i <= 5; i++) add(group, new THREE.BoxGeometry(0.04, 7, 0.04), led, [i * 1.6, 3.6, -6.95], [0, 0, 0], 1, false);
  const gridMat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.18, toneMapped: false });
  for (let i = -8; i <= 8; i++) {
    add(group, new THREE.BoxGeometry(0.012, 0.002, 18), gridMat, [i * 0.8, 0.002, -1], [0, 0, 0], 1, false);
    add(group, new THREE.BoxGeometry(14, 0.002, 0.012), gridMat, [0, 0.002, i * 0.8 - 1], [0, 0, 0], 1, false);
  }
  const glow = wallGlow(group, [0, 2.4, -6.9], 6);
  return {
    apply(p) {
      floorMat.color.copy(p.floor); wallMat.color.copy(p.wall);
      led.color.copy(p.glow).multiplyScalar(1.6); gridMat.color.copy(p.accent); glow.color.copy(p.glow);
    },
    fog: [7, 18],
  };
}

function cinematic(group, seed) {
  const floorMat = std({ roughness: 0.6 });
  add(group, new THREE.CircleGeometry(30, 48), floorMat, [0, 0, 0], [-Math.PI / 2, 0, 0], 1, false);
  // a hard top light cone and floating dust: the "spotlight on a dark stage" look
  // single-sided and faint: in a 9:16 frame the beam fills the whole view, so it must stay a hint
  const coneMat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.022, depthWrite: false, blending: THREE.AdditiveBlending });
  add(group, new THREE.ConeGeometry(1.15, 6.5, 24, 1, true), coneMat, [0, 3.25, 0], [0, 0, 0], 1, false);
  const poolMat = new THREE.MeshBasicMaterial({ map: glowTexture(), transparent: true, opacity: 0.22, depthWrite: false, blending: THREE.AdditiveBlending });
  add(group, new THREE.PlaneGeometry(4, 4), poolMat, [0, 0.01, 0], [-Math.PI / 2, 0, 0], 1, false);
  const n = 160, pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) pos.set([(hash(i, seed) - 0.5) * 4, hash(i + 99, seed) * 4.5, (hash(i + 199, seed) - 0.5) * 3], i * 3);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const dustMat = new THREE.PointsMaterial({ size: 0.018, transparent: true, opacity: 0.55, depthWrite: false });
  const dust = new THREE.Points(geo, dustMat);
  group.add(dust);
  const base = pos.slice();
  return {
    apply(p, t) {
      floorMat.color.copy(p.floor); coneMat.color.copy(p.key); poolMat.color.copy(p.key); dustMat.color.copy(p.key);
      const a = geo.attributes.position.array;
      for (let i = 0; i < n; i++) {
        a[i * 3] = base[i * 3] + noise1(t * 0.2 + i, seed) * 0.08;
        a[i * 3 + 1] = ((base[i * 3 + 1] + t * 0.05 * (0.5 + hash(i, seed + 3))) % 4.5);
      }
      geo.attributes.position.needsUpdate = true;
    },
    lights: { rim: 1.3, hemi: 0.45, front: 0.6 }, fog: [5, 14],
  };
}

function cozy(group, seed) {
  // wooden floor, rug, back wall with a window, floor lamp, bookshelf, plant
  const plankA = std({ roughness: 0.7 }), plankB = std({ roughness: 0.7 });
  for (let i = -10; i <= 10; i++) add(group, new THREE.BoxGeometry(0.42, 0.04, 14), i % 2 ? plankA : plankB, [i * 0.42, -0.02, -1], [0, 0, 0], 1, false);
  const rug = std({ roughness: 1 });
  add(group, new THREE.CylinderGeometry(1.5, 1.5, 0.02, 10), rug, [0, 0.012, 0.2], [0, 0, 0], [1, 1, 0.6], false);
  const wallMat = std({ roughness: 0.95 });
  add(group, new THREE.BoxGeometry(14, 6, 0.2), wallMat, [0, 3, -3.2], [0, 0, 0], 1, false);
  const frame = std({ roughness: 0.6 });
  const pane = new THREE.MeshBasicMaterial({ toneMapped: false });
  add(group, new THREE.BoxGeometry(1.5, 1.7, 0.05), pane, [-1.7, 2.3, -3.08], [0, 0, 0], 1, false);
  for (const [x, y, w, h] of [[-1.7, 3.17, 1.65, 0.08], [-1.7, 1.43, 1.65, 0.08], [-2.48, 2.3, 0.08, 1.8], [-0.92, 2.3, 0.08, 1.8], [-1.7, 2.3, 0.05, 1.7], [-1.7, 2.3, 1.5, 0.05]])
    add(group, new THREE.BoxGeometry(w, h, 0.09), frame, [x, y, -3.05], [0, 0, 0], 1, false);
  // floor lamp with a warm point light
  const lampMetal = std({ roughness: 0.4, metalness: 0.3 }), shade = new THREE.MeshStandardMaterial({ flatShading: true, emissive: "#000000", roughness: 0.9 });
  add(group, new THREE.CylinderGeometry(0.03, 0.03, 1.6, 6), lampMetal, [1.9, 0.8, -2.2]);
  add(group, new THREE.CylinderGeometry(0.22, 0.22, 0.04, 8), lampMetal, [1.9, 0.02, -2.2]);
  add(group, new THREE.CylinderGeometry(0.18, 0.3, 0.32, 8, 1, true), shade, [1.9, 1.7, -2.2]);
  const bulb = new THREE.PointLight("#ffb46b", 6, 6, 1.6);
  bulb.position.set(1.9, 1.6, -2.2);
  group.add(bulb);
  // bookshelf
  const wood = std({ roughness: 0.7 });
  add(group, new THREE.BoxGeometry(1.2, 2.0, 0.35), wood, [2.9, 1.0, -2.9]);
  const bookMats = [0, 1, 2, 3].map(() => std({ roughness: 0.8 }));
  for (let row = 0; row < 3; row++) {
    let x = 2.42;
    for (let k = 0; k < 7; k++) {
      const w = 0.08 + hash(row * 10 + k, seed) * 0.06, h = 0.32 + hash(row * 10 + k + 50, seed) * 0.12;
      add(group, new THREE.BoxGeometry(w, h, 0.26), bookMats[(row + k) % 4], [x + w / 2, 0.35 + row * 0.6 + h / 2, -2.82], [0, 0, 0], 1, false);
      x += w + 0.015;
    }
  }
  // plant
  const pot = std({ roughness: 0.8 }), leaf = std({ roughness: 0.7 });
  add(group, new THREE.CylinderGeometry(0.2, 0.15, 0.35, 7), pot, [-2.6, 0.17, -2.4]);
  for (let k = 0; k < 6; k++) add(group, new THREE.IcosahedronGeometry(0.22, 0), leaf, [-2.6 + (hash(k, seed) - 0.5) * 0.4, 0.55 + k * 0.12, -2.4 + (hash(k + 9, seed) - 0.5) * 0.3]);
  const glow = wallGlow(group, [1.9, 1.9, -3.05], 3.5);
  return {
    apply(p) {
      plankA.color.copy(p.floor); plankB.color.copy(p.floor).multiplyScalar(0.88);
      rug.color.copy(p.floor).multiplyScalar(1.15).lerp(p.accent, 0.18); wallMat.color.copy(p.wall); frame.color.copy(p.floor).multiplyScalar(0.8);
      pane.color.copy(p.fill).lerp(p.bg, 0.3).multiplyScalar(1.1);
      lampMetal.color.copy(p.ink).multiplyScalar(0.35); shade.color.copy(p.card); shade.emissive.copy(p.glow).multiplyScalar(0.6);
      bulb.color.copy(p.glow); wood.color.copy(p.floor).multiplyScalar(0.7); glow.color.copy(p.glow);
      bookMats.forEach((m, i) => m.color.copy([p.accent, p.rim, p.fill, p.card][i]).multiplyScalar(0.85));
      pot.color.copy(p.accent).lerp(p.floor, 0.5); leaf.color.set("#5f8f4e").lerp(p.fill, 0.15);
    },
    lights: { rim: 0.7, hemi: 0.9 }, fog: [8, 20],
  };
}

function historic(group, seed) {
  const tileA = std({ roughness: 0.9 }), tileB = std({ roughness: 0.9 });
  for (let i = -7; i <= 7; i++) for (let j = -6; j <= 3; j++)
    add(group, new THREE.BoxGeometry(0.98, 0.06, 0.98), (i + j) % 2 ? tileA : tileB, [i, -0.03, j], [0, 0, 0], 1, false);
  const stone = std({ roughness: 0.9 });
  add(group, new THREE.BoxGeometry(16, 7, 0.4), stone, [0, 3.5, -4.6], [0, 0, 0], 1, false);
  for (const x of [-3, -1.5, 1.5, 3]) {
    add(group, new THREE.CylinderGeometry(0.22, 0.25, 4, 8), stone, [x, 2, -3.9]);
    add(group, new THREE.BoxGeometry(0.62, 0.18, 0.62), stone, [x, 4.05, -3.9]);
    add(group, new THREE.BoxGeometry(0.62, 0.18, 0.62), stone, [x, 0.09, -3.9]);
  }
  // banners between the columns, in the accent colour
  const banner = std({ roughness: 1, side: THREE.DoubleSide });
  for (const x of [-2.25, 2.25]) add(group, new THREE.PlaneGeometry(0.7, 2.2), banner, [x, 2.6, -4.35], [0, 0, 0], 1, false);
  // torches with flickering light
  const flameMat = new THREE.MeshBasicMaterial({ toneMapped: false });
  const torches = [-0.75, 0.75].map((x) => {
    add(group, new THREE.CylinderGeometry(0.04, 0.03, 0.5, 6), std({ color: "#3a2a1c" }), [x * 3.4, 2.1, -4.3]);
    const flame = add(group, new THREE.ConeGeometry(0.08, 0.22, 6), flameMat, [x * 3.4, 2.45, -4.3], [0, 0, 0], 1, false);
    const light = new THREE.PointLight("#ff9c4a", 4, 5, 1.8);
    light.position.set(x * 3.4, 2.5, -4.0);
    group.add(light);
    return { flame, light };
  });
  const glow = wallGlow(group, [0, 2.4, -4.35], 6);
  return {
    apply(p, t) {
      tileA.color.copy(p.floor); tileB.color.copy(p.floor).multiplyScalar(0.86); stone.color.copy(p.wall).lerp(p.card, 0.25);
      banner.color.copy(p.accent); flameMat.color.copy(p.glow).multiplyScalar(2); glow.color.copy(p.glow);
      torches.forEach(({ flame, light }, i) => {
        const f = 0.85 + 0.15 * noise1(t * 6 + i * 3, seed);
        light.intensity = 4 * f; light.color.copy(p.glow); flame.scale.set(1, f * 1.15, 1);
      });
    },
    lights: { rim: 0.8, hemi: 0.8 }, fog: [7, 18],
  };
}

function prehistoric(group, seed) {
  // uneven ground, boulders, a cave wall and a campfire
  const geo = new THREE.PlaneGeometry(30, 22, 30, 22);
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) pos.setZ(i, (hash(i, seed) - 0.5) * 0.08 * Math.min(1, Math.hypot(pos.getX(i), pos.getY(i)) / 3));
  geo.computeVertexNormals();
  const ground = std({ roughness: 1 });
  add(group, geo, ground, [0, 0, -2], [-Math.PI / 2, 0, 0], 1, false);
  const rock = std({ roughness: 1 });
  const cave = add(group, new THREE.IcosahedronGeometry(6, 1), rock, [0, 2.2, -9.5], [0, 0.4, 0], [1.6, 1, 0.6], false);
  cave.castShadow = false;
  for (let k = 0; k < 7; k++) {
    const x = (hash(k, seed) - 0.5) * 9, z = -2 - hash(k + 5, seed) * 4, s = 0.25 + hash(k + 9, seed) * 0.6;
    if (Math.abs(x) < 1.2 && z > -3) continue;
    add(group, new THREE.DodecahedronGeometry(s, 0), rock, [x, s * 0.6, z], [hash(k, 1), hash(k, 2), 0]);
  }
  const log = std({ color: "#4a3020", roughness: 1 });
  for (let k = 0; k < 4; k++) add(group, new THREE.CylinderGeometry(0.05, 0.05, 0.6, 6), log, [1.5, 0.06, -1.2], [Math.PI / 2, 0, k * Math.PI / 4]);
  const flameMat = new THREE.MeshBasicMaterial({ toneMapped: false });
  const flames = [0, 1, 2].map((k) => add(group, new THREE.ConeGeometry(0.12 - k * 0.025, 0.42 - k * 0.08, 6), flameMat, [1.5 + (k - 1) * 0.05, 0.25, -1.2], [0, k, 0], 1, false));
  const fire = new THREE.PointLight("#ff8a3d", 10, 7, 1.7);
  fire.position.set(1.5, 0.6, -1.0);
  group.add(fire);
  return {
    apply(p, t) {
      ground.color.copy(p.floor); rock.color.copy(p.wall).lerp(p.floor, 0.4); flameMat.color.copy(p.glow).multiplyScalar(2.2);
      const f = 0.8 + 0.2 * noise1(t * 7, seed);
      fire.intensity = 10 * f; fire.color.copy(p.glow);
      flames.forEach((m, k) => m.scale.set(1, f * (1 + 0.1 * noise1(t * 9 + k, seed + k)), 1));
    },
    lights: { rim: 0.9, hemi: 0.7 }, fog: [6, 16],
  };
}

/** Canvas texture helper (sRGB). */
function canvasTex(w, h, draw) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

/** The window looks for the dialogue sets (the time of day sets the mood): sky gradient stops, buildings, lit
 *  windows, bokeh city lights, rain, and how the room is lit. */
export const LOOKS = {
  morning: { sky: [[0, "#6fa7d8"], [0.7, "#a9cfee"], [1, "#d6ebf7"]], bldg: "#6b7d94", lit: 0, litCols: ["#ffffff"],
    dots: 0, rain: 0, wall: "#39414f", warm: "#ffe2c4", monitor: 0.6, bg: "#a9cfee",
    lights: { key: 0.85, rim: 0.7, hemi: 1.25, front: 0.95 }, lightColors: { key: "#fff1df", rim: "#cfe4ff", fill: "#9fb8d6", hemi: "#e8f2ff" } },
  rain: { sky: [[0, "#1a222d"], [0.6, "#2c3846"], [1, "#3b4858"]], bldg: "#161c25", lit: 0.12, litCols: ["#ffd59a", "#c9dcff"],
    dots: 8, dotCols: ["#ffcf8a", "#ff4a4a", "#9cc8ff"], rain: 90, wall: "#1f2630", monitor: 0.9, bg: "#2c3846",
    lights: { key: 0.5, rim: 0.6, hemi: 0.75, front: 0.75 }, lightColors: { key: "#ffd9b8", rim: "#9fb6d6", fill: "#3a4a60" } },
  night: { sky: [[0, "#04060d"], [0.65, "#0b1430"], [1, "#13204a"]], bldg: "#05070c", lit: 0.32, litCols: ["#ffd59a", "#9cc8ff"],
    dots: 26, dotCols: ["#ffcf8a", "#7fb6ff", "#ff6b6b", "#ffe8b0", "#8ff0ff"], rain: 0, monitor: 1, bg: "#05070d",
    lights: { key: 0.3, rim: 0.55, hemi: 0.45, front: 0.6 } },
  dusk: { sky: [[0, "#2b1f63"], [0.45, "#7a3f8f"], [0.8, "#d8668a"], [1, "#f39a72"]], bldg: "#120d22", lit: 0.25, litCols: ["#ffd59a", "#ffb070"],
    dots: 18, dotCols: ["#ffcf8a", "#ffb35c", "#ffe8b0", "#9cc8ff"], rain: 0, wall: "#241a2e", warm: "#ffb26b", monitor: 0.9, bg: "#7a3f8f",
    lights: { key: 0.55, rim: 0.8, hemi: 0.75, front: 0.75 }, lightColors: { key: "#ffc58f", rim: "#ff9fc0", fill: "#5a3d7a" } },
};

/** The city behind the window for a look: sky, buildings with lit windows, bokeh lights, and falling rain. */
function cityOutside(group, seed, LK) {
  const sky = new THREE.MeshBasicMaterial({ fog: false, map: canvasTex(4, 256, (g, w, h) => {
    const gr = g.createLinearGradient(0, 0, 0, h);
    for (const [k, c] of LK.sky) gr.addColorStop(k, c);
    g.fillStyle = gr; g.fillRect(0, 0, w, h);
  }) });
  add(group, new THREE.PlaneGeometry(40, 16), sky, [0, 5, -16], [0, 0, 0], 1, false);
  const bldg = new THREE.MeshBasicMaterial({ color: LK.bldg, fog: false });
  const lit = LK.litCols.map((c) => new THREE.MeshBasicMaterial({ color: c, fog: false, toneMapped: false }));
  for (let k = 0; k < 14; k++) {
    const bx = -9 + k * 1.35 + (hash(k, seed) - 0.5) * 0.6, bh = 2.5 + hash(k + 20, seed) * 6, bw = 0.9 + hash(k + 40, seed) * 0.7, bz = -11 - hash(k + 60, seed) * 3;
    add(group, new THREE.BoxGeometry(bw, bh, 0.3), bldg, [bx, bh / 2 - 0.5, bz], [0, 0, 0], 1, false);
    if (!LK.lit) continue;
    for (let r = 0; r < Math.floor(bh / 0.45); r++) for (let c = 0; c < 3; c++) {
      if (hash(k * 97 + r * 7 + c, seed) > LK.lit) continue;
      add(group, new THREE.PlaneGeometry(0.12, 0.16), lit[(k + r + c) % lit.length], [bx - bw / 2 + 0.22 + c * (bw - 0.44) / 2, r * 0.45, bz + 0.16], [0, 0, 0], 1, false);
    }
  }
  const dotTex = glowTexture();
  for (let k = 0; k < LK.dots; k++) {
    const m = new THREE.MeshBasicMaterial({ map: dotTex, color: LK.dotCols[k % LK.dotCols.length], transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending, fog: false, toneMapped: false, opacity: 0.85 });
    const sz = 0.12 + hash(k + 300, seed) * 0.18;
    add(group, new THREE.PlaneGeometry(sz, sz), m, [-6 + hash(k + 100, seed) * 12, 0.3 + hash(k + 200, seed) * 4.2, -7 - hash(k + 400, seed) * 3], [0, 0, 0], 1, false);
  }
  // rain: thin bright streaks falling outside the glass, each at its own speed and depth (pure in t)
  const drops = [];
  if (LK.rain) {
    const mat = new THREE.MeshBasicMaterial({ color: "#dfe8f2", transparent: true, opacity: 0.55, fog: false, depthWrite: false });
    const geo = new THREE.PlaneGeometry(0.008, 0.32);
    for (let k = 0; k < LK.rain; k++) {
      const m = add(group, geo, mat, [0, 0, 0], [0, 0, 0.06], 1, false);
      drops.push({ m, x: -3.2 + hash(k + 500, seed) * 6.4, z: -2.9 - hash(k + 600, seed) * 2.2, y0: hash(k + 700, seed) * 4.2,
        v: 3.2 + hash(k + 800, seed) * 1.6, s: 0.7 + hash(k + 900, seed) * 0.7 });
    }
  }
  return {
    apply(t = 0) {
      for (const d of drops) {
        d.m.position.set(d.x, 0.4 + ((((d.y0 - t * d.v) % 4.2) + 4.2) % 4.2), d.z);
        d.m.scale.set(1, d.s, 1);
      }
    },
  };
}

/** Late-night desk for two-character dialogue shorts: a desk (its front panel hides legs), a monitor with a
 *  glowing code UI, keyboard, sticky notes, and a window onto a city at night whose lights become bokeh with
 *  depth of field. Layout numbers are shared with the Python scene builder through catalog.json (sets.office). */
function office(group, seed, opts = {}) {
  const L = catalog.sets.office;
  const H = L.desk_height, [dx, dz] = L.desk_center, [dw, dd] = L.desk_size;
  const floor = std({ roughness: 0.95 });
  add(group, new THREE.PlaneGeometry(30, 20), floor, [0, 0, 2], [-Math.PI / 2, 0, 0], 1, false);
  // back wall with a wide window (wall pieces around the opening)
  const wallMat = std({ roughness: 0.95 });
  const wz = L.wall_z, [wx0, wx1, wy0, wy1] = L.window;
  add(group, new THREE.BoxGeometry(16, wy0, 0.2), wallMat, [0, wy0 / 2, wz], [0, 0, 0], 1, false);
  add(group, new THREE.BoxGeometry(16, 6 - wy1, 0.2), wallMat, [0, wy1 + (6 - wy1) / 2, wz], [0, 0, 0], 1, false);
  add(group, new THREE.BoxGeometry(8 + wx0, wy1 - wy0, 0.2), wallMat, [(-8 + wx0) / 2, (wy0 + wy1) / 2, wz], [0, 0, 0], 1, false);
  add(group, new THREE.BoxGeometry(8 - wx1, wy1 - wy0, 0.2), wallMat, [(8 + wx1) / 2, (wy0 + wy1) / 2, wz], [0, 0, 0], 1, false);
  const frameMat = std({ roughness: 0.5 });
  const mull = [[(wx0 + wx1) / 2, wy0, wx1 - wx0, 0.06], [(wx0 + wx1) / 2, wy1, wx1 - wx0, 0.06], [(wx0 + wx1) / 2, (wy0 + wy1) / 2, wx1 - wx0, 0.04]];
  for (let x = wx0; x <= wx1 + 1e-6; x += (wx1 - wx0) / 3) mull.push([x, (wy0 + wy1) / 2, 0.05, wy1 - wy0]);
  for (const [x, y, w, h] of mull) add(group, new THREE.BoxGeometry(w, h, 0.08), frameMat, [x, y, wz + 0.06], [0, 0, 0], 1, false);
  // outside the window: the look sets the sky, the buildings, the city lights and the weather
  const LK = LOOKS[opts.look] ?? LOOKS.night;
  const outside = cityOutside(group, seed, LK);
  // desk: top, a front panel down to the floor (no legs on show), the far edge toward the person
  const wood = std({ roughness: 0.55 });
  add(group, new THREE.BoxGeometry(dw, 0.045, dd), wood, [dx, H - 0.0225, dz]);
  add(group, new THREE.BoxGeometry(dw, H - 0.045, 0.03), wood, [dx, (H - 0.045) / 2, dz + dd / 2 - 0.02], [0, 0, 0], 1, false);
  // monitor angled toward the person, with a code editor on the screen
  const [mx, mz, mry] = L.monitor;
  const mon = new THREE.Group();
  mon.position.set(mx, H, mz); mon.rotation.y = mry;
  group.add(mon);
  const plastic = std({ roughness: 0.4 });
  add(mon, new THREE.BoxGeometry(0.06, 0.24, 0.05), plastic, [0, 0.12, -0.03]);
  add(mon, new THREE.BoxGeometry(0.22, 0.012, 0.16), plastic, [0, 0.006, -0.02]);
  add(mon, new THREE.BoxGeometry(0.66, 0.42, 0.03), plastic, [0, 0.44, 0]);
  const screen = new THREE.MeshBasicMaterial({ toneMapped: false, map: canvasTex(512, 320, (g, w, h) => {
    g.fillStyle = "#0b1a3a"; g.fillRect(0, 0, w, h);
    g.fillStyle = "#11254f"; g.fillRect(0, 0, w * 0.22, h);
    const cols = ["#7fb2ff", "#e6edff", "#ffd27f", "#8ff0c8", "#c0a8ff"];
    for (let r = 0; r < 14; r++) {
      let x = w * 0.26 + (hash(r, seed + 5) > 0.6 ? 24 : 0);
      for (let k = 0; k < 4; k++) {
        const len = 20 + hash(r * 9 + k, seed) * 90;
        if (x + len > w - 16) break;
        g.fillStyle = cols[(r + k) % cols.length]; g.globalAlpha = 0.85;
        g.fillRect(x, 18 + r * 21, len, 9); x += len + 10;
      }
    }
    g.globalAlpha = 1;
  }) });
  add(mon, new THREE.PlaneGeometry(0.62, 0.38), screen, [0, 0.44, 0.016], [0, 0, 0], 1, false);
  const monLight = new THREE.SpotLight("#7fa8ff", 3.2, 3, Math.PI / 3.2, 0.8, 1.6);
  monLight.position.set(0, 0.44, 0.15);
  mon.add(monLight, monLight.target);
  monLight.target.position.set(0, 0.35, 1.2);
  // keyboard, sticky notes, a pen
  const keys = std({ roughness: 0.5, map: canvasTex(256, 96, (g, w, h) => {
    g.fillStyle = "#1c1f26"; g.fillRect(0, 0, w, h);
    g.fillStyle = "#2c3140";
    for (let r = 0; r < 4; r++) for (let c = 0; c < 14; c++) g.fillRect(6 + c * 17.6, 8 + r * 21, 14, 16);
  }) });
  const [kx, kz] = L.keyboard;
  add(group, new THREE.BoxGeometry(0.46, 0.018, 0.15), keys, [kx, H + 0.009, kz], [0, -0.05, 0]);
  const noteCols = ["#ffd84a", "#ff9b54", "#ffe9a8"];
  L.notes.forEach(([nx, nz, rot], i) => add(group, new THREE.BoxGeometry(0.075, 0.004, 0.075), std({ color: noteCols[i % 3], roughness: 0.9 }),
    [nx, H + 0.002, nz], [0, rot, 0], 1, false));
  add(group, new THREE.CylinderGeometry(0.006, 0.006, 0.16, 6), std({ color: "#c8ccd4", roughness: 0.4 }), [L.pen[0], H + 0.006, L.pen[1]], [0, 0, Math.PI / 2 + 0.3]);
  // a mug and a notepad on the desk, and a hanging lamp at the top right (seen in the wides)
  const lay = opts.layout ?? {};
  const ceramic = std({ color: "#f2f0ea", roughness: 0.35 });
  if (lay.desk_mug !== false) {
    const mug = new THREE.Group();
    mug.position.set(L.mug?.[0] ?? 0.32, H, L.mug?.[1] ?? 0.02);
    group.add(mug);
    add(mug, new THREE.CylinderGeometry(0.042, 0.038, 0.1, 14), ceramic, [0, 0.05, 0]);
    add(mug, new THREE.TorusGeometry(0.026, 0.008, 6, 12), ceramic, [0.045, 0.052, 0], [0, 0, 0]);
  }
  add(group, new THREE.BoxGeometry(0.22, 0.006, 0.15), std({ color: "#f4f4f0", roughness: 0.9 }), [L.notepad?.[0] ?? 0.05, H + 0.003, L.notepad?.[1] ?? 0.34], [0, 0.08, 0], 1, false);
  add(group, new THREE.CylinderGeometry(0.005, 0.005, 0.13, 6), std({ color: "#2e7d6b", roughness: 0.4 }), [(L.notepad?.[0] ?? 0.05) + 0.02, H + 0.009, (L.notepad?.[1] ?? 0.34)], [0, 0.4, Math.PI / 2]);
  const lampShade = std({ color: "#7a5a3a", roughness: 0.6, side: THREE.DoubleSide });
  const lampBulb = new THREE.MeshBasicMaterial({ color: "#fff1d6", toneMapped: false });
  const [lx, ly, lz] = L.lamp ?? [1.05, 1.75, -0.45];
  add(group, new THREE.CylinderGeometry(0.004, 0.004, 1.2, 4), std({ color: "#222222" }), [lx, ly + 0.66, lz], [0, 0, 0], 1, false);
  add(group, new THREE.ConeGeometry(0.16, 0.13, 8, 1, true), lampShade, [lx, ly, lz], [0, 0, 0], 1, false);
  add(group, new THREE.SphereGeometry(0.035, 8, 6), lampBulb, [lx, ly - 0.05, lz], [0, 0, 0], 1, false);
  // the warm light on the person's face (a desk lamp out of frame, front left)
  const warm = new THREE.PointLight("#ffb070", 2.4, 3.2, 1.5);
  warm.position.set(...L.warm_light);
  group.add(warm);
  const wallGlowM = wallGlow(group, [-0.6, 1.6, wz + 0.12], 4);
  return {
    apply(p, t) {
      floor.color.copy(p.floor); wallMat.color.copy(p.wall); frameMat.color.copy(p.wall).multiplyScalar(0.55);
      wood.color.set("#5a3d29").lerp(p.floor, 0.15); plastic.color.set("#1a1c22");
      warm.color.copy(p.key); monLight.color.copy(p.rim).lerp(new THREE.Color("#7fa8ff"), 0.5);
      wallGlowM.color.copy(p.rim).multiplyScalar(0.6);
      if (LK.wall) { wallMat.color.set(LK.wall); frameMat.color.set(LK.wall).multiplyScalar(0.55); floor.color.set(LK.wall).multiplyScalar(0.8); }
      if (LK.warm) warm.color.set(LK.warm);
      monLight.intensity = 3.2 * (LK.monitor ?? 1);
      outside.apply(t);
    },
    lights: LK.lights, lightColors: LK.lightColors, fog: [7, 40], background: LK.bg,
  };
}

/** The whiteboard's state at time t from its events: a title, jargon words (struck through in red when vetoed),
 *  a diagram row of stick figures and boxes joined by arrows, and "= label" captions under the diagram. */
export function boardState(events, t) {
  const st = { title: "", words: [], items: [], arrows: [], labels: [], last: null };
  for (const ev of events ?? []) {
    if (ev.t > t) break;
    const text = String(ev.text ?? "").slice(0, 28);
    if (ev.op === "title") { st.title = text; st.last = { row: "title", k: 0 }; }
    else if (ev.op === "word" && st.words.length < 3) { st.words.push({ text, struck: false }); st.last = { row: "words", k: st.words.length - 1 }; }
    else if (ev.op === "strike") {
      const hit = st.words.filter((w) => !text || w.text.toLowerCase() === text.toLowerCase());
      for (const w of hit.length ? hit : st.words) w.struck = true;
      st.last = { row: "words", k: Math.max(0, st.words.length - 1) };
    } else if ((ev.op === "figure" || ev.op === "box") && st.items.length < 3) {
      st.items.push({ kind: ev.op, text, k: st.items.length });
      st.last = { row: "items", k: st.items.length - 1 };
    } else if (ev.op === "arrow" && st.items.length >= 2) {
      const k = st.items.length - 2;
      if (!st.arrows.includes(k)) st.arrows.push(k);
      st.last = { row: "arrow", k };
    } else if (ev.op === "label" && st.labels.length < 3) {
      st.labels.push(text);
      st.last = { row: "labels", k: st.labels.length - 1 };
    }
  }
  return st;
}

function drawBoard(g, w, h, st, slots) {
  g.fillStyle = "#f6f5f0"; g.fillRect(0, 0, w, h);
  const X = (k) => slots[k] * w;
  g.textAlign = "center"; g.textBaseline = "middle"; g.lineCap = "round";
  if (st.title) {
    g.fillStyle = "#1c1c1f"; g.font = "700 92px Caveat";
    g.fillText(st.title, w / 2, 72);
    const tw = g.measureText(st.title).width;
    g.strokeStyle = "#1c1c1f"; g.lineWidth = 5;
    g.beginPath(); g.moveTo(w / 2 - tw / 2 - 30, 124); g.lineTo(w / 2 + tw / 2 + 30, 124); g.stroke();
  }
  st.words.forEach((wd, k) => {
    g.fillStyle = "#1f2a6b"; g.font = "700 64px Caveat";
    g.fillText(wd.text, X(k), 182);
    if (wd.struck) {
      const tw = g.measureText(wd.text).width;
      g.strokeStyle = "#d1373b"; g.lineWidth = 6;
      g.beginPath(); g.moveTo(X(k) - tw / 2 - 8, 186); g.lineTo(X(k) + tw / 2 + 8, 186); g.stroke();
    }
  });
  const ROW = 345;
  st.items.forEach((it) => {
    const x = X(it.k), col = it.kind === "figure" && it.k > 0 ? "#2e7d4f" : "#1c1c1f";
    g.strokeStyle = col; g.lineWidth = 7;
    if (it.kind === "figure") {
      g.beginPath(); g.arc(x, ROW - 62, 22, 0, Math.PI * 2); g.stroke();
      g.beginPath(); g.moveTo(x, ROW - 40); g.lineTo(x, ROW + 22);
      g.moveTo(x - 32, ROW - 18); g.lineTo(x + 32, ROW - 18);
      g.moveTo(x, ROW + 22); g.lineTo(x - 26, ROW + 66); g.moveTo(x, ROW + 22); g.lineTo(x + 26, ROW + 66); g.stroke();
    } else {
      g.strokeRect(x - 82, ROW - 62, 164, 120);
    }
    g.fillStyle = col; g.font = "700 54px Caveat";
    g.fillText(it.text.toUpperCase(), x, ROW + 112);
  });
  for (const k of st.arrows) {
    const a = X(k) + 62, b = X(k + 1) - 62;
    g.strokeStyle = "#2e7d4f"; g.lineWidth = 6;
    for (const [y, dir] of [[ROW - 14, 1], [ROW + 14, -1]]) {
      const x0 = dir > 0 ? a : b, x1 = dir > 0 ? b : a;
      g.beginPath(); g.moveTo(x0, y); g.lineTo(x1, y); g.lineTo(x1 - dir * 18, y - 12); g.moveTo(x1, y); g.lineTo(x1 - dir * 18, y + 12); g.stroke();
    }
  }
  st.labels.forEach((lb, k) => {
    g.fillStyle = k % 2 ? "#d1373b" : "#1f4fa8"; g.font = "700 58px Caveat";
    g.fillText(`= ${lb}`, X(k), 540);
  });
}

/** Board point (0..1 across, 0..1 down) that the pointer reaches for: the last thing written. */
function boardTarget(st, slots) {
  const L = st.last;
  if (!L) return [0.5, 0.35];
  if (L.row === "title") return [0.5, 0.12];
  if (L.row === "words") return [slots[L.k], 0.26];
  if (L.row === "items") return [slots[L.k], 0.52];
  if (L.row === "arrow") return [(slots[L.k] + slots[L.k + 1]) / 2, 0.52];
  return [slots[L.k], 0.81];
}

/** Explainer classroom: a whiteboard on an easel that fills in as the lines are spoken (opts.board.events), a
 *  school desk, the mascot on a stack of books holding a long pointer, a window, a bookshelf, a leafy wall. */
function classroom(group, seed, opts = {}) {
  const L = catalog.sets.classroom;
  const LK = LOOKS[opts.look] ?? LOOKS.morning;
  const H = L.desk_height, [dx, dz] = L.desk_center, [dw, dd] = L.desk_size;
  const floor = std({ roughness: 0.95, color: "#5a4636" });
  add(group, new THREE.PlaneGeometry(30, 20), floor, [0, 0, 2], [-Math.PI / 2, 0, 0], 1, false);
  const wallMat = std({ roughness: 0.95, color: "#24303b" });
  const wz = L.wall_z, [wx0, wx1, wy0, wy1] = L.window;
  add(group, new THREE.BoxGeometry(16, wy0, 0.2), wallMat, [0, wy0 / 2, wz], [0, 0, 0], 1, false);
  add(group, new THREE.BoxGeometry(16, 6 - wy1, 0.2), wallMat, [0, wy1 + (6 - wy1) / 2, wz], [0, 0, 0], 1, false);
  add(group, new THREE.BoxGeometry(8 + wx0, wy1 - wy0, 0.2), wallMat, [(-8 + wx0) / 2, (wy0 + wy1) / 2, wz], [0, 0, 0], 1, false);
  add(group, new THREE.BoxGeometry(8 - wx1, wy1 - wy0, 0.2), wallMat, [(8 + wx1) / 2, (wy0 + wy1) / 2, wz], [0, 0, 0], 1, false);
  const frameMat = std({ roughness: 0.5, color: "#141a20" });
  for (let x = wx0; x <= wx1 + 1e-6; x += (wx1 - wx0) / 3) add(group, new THREE.BoxGeometry(0.06, wy1 - wy0, 0.08), frameMat, [x, (wy0 + wy1) / 2, wz + 0.06], [0, 0, 0], 1, false);
  add(group, new THREE.BoxGeometry(wx1 - wx0, 0.06, 0.08), frameMat, [(wx0 + wx1) / 2, (wy0 + wy1) / 2, wz + 0.06], [0, 0, 0], 1, false);
  const outside = cityOutside(group, seed, LK);
  // leafy pattern on the side wall area (left of the window)
  const leaf = std({ color: "#7fa34a", roughness: 0.8 });
  for (let k = 0; k < 22; k++) add(group, new THREE.CircleGeometry(0.07 + hash(k, seed) * 0.04, 6), leaf,
    [-3.4 + hash(k + 30, seed) * 1.7, 0.6 + hash(k + 60, seed) * 2.6, wz + 0.11], [0, 0, hash(k + 90, seed) * 3], 1, false);
  // bookshelf on the right
  const wood = std({ color: "#6b4a2f", roughness: 0.7 });
  const [sx, sz] = L.shelf;
  add(group, new THREE.BoxGeometry(0.9, 2.1, 0.32), wood, [sx, 1.05, sz]);
  const bookCols = ["#e2584a", "#f2c14e", "#4f9d69", "#e8862e", "#4a74c9", "#c46bb0"];
  for (let row = 0; row < 3; row++) {
    let x = sx - 0.38;
    for (let k = 0; k < 8; k++) {
      const w = 0.05 + hash(row * 10 + k, seed) * 0.04, h = 0.24 + hash(row * 10 + k + 50, seed) * 0.1;
      add(group, new THREE.BoxGeometry(w, h, 0.22), std({ color: bookCols[(row * 3 + k) % bookCols.length], roughness: 0.8 }), [x + w / 2, 0.45 + row * 0.6 + h / 2, sz + 0.06], [0, 0, 0], 1, false);
      x += w + 0.012;
    }
  }
  // the whiteboard on an easel
  const [bx, by, bz] = L.board_center, [bw, bh] = L.board_size;
  const metal = std({ color: "#8a919a", roughness: 0.4, metalness: 0.3 });
  add(group, new THREE.BoxGeometry(bw + 0.06, bh + 0.06, 0.03), metal, [bx, by, bz - 0.02]);
  for (const sxx of [-1, 1]) add(group, new THREE.BoxGeometry(0.035, by + bh / 2, 0.035), metal, [bx + sxx * (bw / 2 - 0.08), (by + bh / 2) / 2, bz - 0.05]);
  add(group, new THREE.BoxGeometry(bw * 0.9, 0.025, 0.06), metal, [bx, by - bh / 2 - 0.02, bz + 0.02]);
  for (const [k, col] of [[-0.1, "#d1373b"], [0, "#1f4fa8"], [0.1, "#2e7d4f"]]) add(group, new THREE.BoxGeometry(0.09, 0.016, 0.016), std({ color: col }), [bx + k, by - bh / 2 - 0.0, bz + 0.03], [0, 0, 0], 1, false);
  const cvs = document.createElement("canvas");
  cvs.width = 1024; cvs.height = 640;
  const tex = new THREE.CanvasTexture(cvs);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  const boardFace = add(group, new THREE.PlaneGeometry(bw, bh), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.6 }), [bx, by, bz + 0.0], [0, 0, 0], 1, false);
  boardFace.castShadow = false;
  const events = [...(opts.board?.events ?? [])].sort((a, b) => a.t - b.t);
  const slots = L.board_slots;
  let drawn = null;
  // the school desk, its chair, and what is on it
  const deskWood = std({ color: "#b07a48", roughness: 0.6 });
  add(group, new THREE.BoxGeometry(dw, 0.04, dd), deskWood, [dx, H - 0.02, dz]);
  for (const [ox, oz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) add(group, new THREE.BoxGeometry(0.04, H - 0.04, 0.04), std({ color: "#3a3f46" }), [dx + ox * (dw / 2 - 0.06), (H - 0.04) / 2, dz + oz * (dd / 2 - 0.06)]);
  const [px, , pz] = L.person;
  const teal = std({ color: "#1f5f63", roughness: 0.7 });
  add(group, new THREE.BoxGeometry(0.42, 0.05, 0.4), teal, [px + 0.12, 0.45, pz]);
  add(group, new THREE.BoxGeometry(0.05, 0.5, 0.4), teal, [px + 0.33, 0.72, pz]);
  const [kx, kz] = L.books;
  ["#c9a43a", "#6a3d8f", "#2f7a4f"].forEach((col, k) => add(group, new THREE.BoxGeometry(0.34 - k * 0.02, 0.05, 0.26 - k * 0.01), std({ color: col, roughness: 0.8 }), [kx, H + 0.025 + k * 0.05, kz]));
  add(group, new THREE.CylinderGeometry(0.035, 0.03, 0.09, 10), std({ color: "#1f3a45" }), [-0.18, H + 0.045, 0.34]);
  ["#ff6b6b", "#4ecdc4", "#ffe66d"].forEach((col, k) => add(group, new THREE.CylinderGeometry(0.004, 0.004, 0.12, 5), std({ color: col }), [-0.19 + k * 0.012, H + 0.1, 0.34], [0.1 * (k - 1), 0, 0.12 * (k - 1)], 1, false));
  add(group, new THREE.BoxGeometry(0.2, 0.03, 0.14), std({ color: "#e86a8a", roughness: 0.8 }), [0.05, H + 0.015, 0.36], [0, 0.15, 0]);
  const mug = new THREE.Group(); mug.position.set(0.3, H, 0.3); group.add(mug);
  const ceramic = std({ color: "#f2f0ea", roughness: 0.35 });
  add(mug, new THREE.CylinderGeometry(0.042, 0.038, 0.1, 14), ceramic, [0, 0.05, 0]);
  add(mug, new THREE.TorusGeometry(0.026, 0.008, 6, 12), ceramic, [0.045, 0.052, 0]);
  // the pointer: held at the mascot's side, its tip on the last thing written (eases over 0.3 s)
  const [mx, my, mz] = L.mascot;
  const origin = new THREE.Vector3(mx + 0.09, my + 0.12, mz + 0.03);
  const stick = add(group, new THREE.CylinderGeometry(0.006, 0.008, 1, 6), std({ color: "#efe3c4", roughness: 0.6 }), [0, 0, 0], [0, 0, 0], 1, false);
  const toWorld = (u, v) => new THREE.Vector3(bx - bw / 2 + u * bw, by + bh / 2 - v * bh, bz + 0.02);
  const warm = new THREE.PointLight("#ffd9b0", 1.6, 4, 1.5);
  warm.position.set(0.8, 1.6, 1.0);
  group.add(warm);
  return {
    apply(p, t) {
      const st = boardState(events, t);
      const key = JSON.stringify(st);
      if (key !== drawn) { drawBoard(cvs.getContext("2d"), cvs.width, cvs.height, st, slots); tex.needsUpdate = true; drawn = key; }
      // pointer tip: eases from the previous target to the new one
      const lastT = [...events].reverse().find((e) => e.t <= t)?.t ?? 0;
      const prevSt = boardState(events, lastT - 1e-3);
      const k = ease("inOutSine", clamp((t - lastT) / 0.3));
      const [u0, v0] = boardTarget(prevSt, slots), [u1, v1] = boardTarget(st, slots);
      const tip = toWorld(u0 + (u1 - u0) * k, v0 + (v1 - v0) * k);
      const reach = origin.clone().lerp(tip, 0.94);
      const d = reach.clone().sub(origin);
      stick.position.copy(origin).addScaledVector(d, 0.5);
      stick.scale.set(1, d.length(), 1);
      stick.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
      outside.apply(t);
    },
    lights: { ...LK.lights, key: (LK.lights.key ?? 1) * 1.1, hemi: (LK.lights.hemi ?? 1) * 1.05 }, lightColors: LK.lightColors,
    fog: [7, 40], background: LK.bg,
  };
}

const SETS = { minimal, modern, cinematic, cozy, historic, prehistoric, office, classroom };

export function buildSet(scene, kind, seed = 1, opts = {}) {
  const group = new THREE.Group();
  scene.add(group);
  const set = (SETS[kind] ?? modern)(group, seed, opts);
  scene.fog = new THREE.Fog("#000000", ...(set.fog ?? [7, 18]));
  return set;
}
