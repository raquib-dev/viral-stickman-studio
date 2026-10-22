// Sets for the style packs. Every set is low-poly and built in code (no downloads), and every colour in
// it comes from the palette, so a mood change re-colours the whole set live (apply(palette, t) runs every
// frame). Lights are shared by all sets.
import * as THREE from "three";
import catalog from "../catalog.json";
import { hash, noise1 } from "./util.js";

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
    apply(p, mult = {}) {
      hemi.color.copy(p.key); hemi.groundColor.copy(p.floor);
      key.color.copy(p.key); rim.color.copy(p.rim); fill.color.copy(p.fill); front.color.copy(p.key);
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

/** Late-night desk for two-character dialogue shorts: a desk (its front panel hides legs), a monitor with a
 *  glowing code UI, keyboard, sticky notes, and a window onto a city at night whose lights become bokeh with
 *  depth of field. Layout numbers are shared with the Python scene builder through catalog.json (sets.office). */
function office(group, seed) {
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
  // the night outside: a sky gradient, building silhouettes with lit windows, and soft city lights
  const sky = new THREE.MeshBasicMaterial({ fog: false, map: canvasTex(4, 256, (g, w, h) => {
    const gr = g.createLinearGradient(0, 0, 0, h);
    gr.addColorStop(0, "#04060d"); gr.addColorStop(0.65, "#0b1430"); gr.addColorStop(1, "#13204a");
    g.fillStyle = gr; g.fillRect(0, 0, w, h);
  }) });
  add(group, new THREE.PlaneGeometry(40, 16), sky, [0, 5, -16], [0, 0, 0], 1, false);
  const bldg = new THREE.MeshBasicMaterial({ color: "#05070c", fog: false });
  const lit = [new THREE.MeshBasicMaterial({ color: "#ffd59a", fog: false, toneMapped: false }),
    new THREE.MeshBasicMaterial({ color: "#9cc8ff", fog: false, toneMapped: false })];
  for (let k = 0; k < 14; k++) {
    const bx = -9 + k * 1.35 + (hash(k, seed) - 0.5) * 0.6, bh = 2.5 + hash(k + 20, seed) * 6, bw = 0.9 + hash(k + 40, seed) * 0.7, bz = -11 - hash(k + 60, seed) * 3;
    add(group, new THREE.BoxGeometry(bw, bh, 0.3), bldg, [bx, bh / 2 - 0.5, bz], [0, 0, 0], 1, false);
    for (let r = 0; r < Math.floor(bh / 0.45); r++) for (let c = 0; c < 3; c++) {
      if (hash(k * 97 + r * 7 + c, seed) > 0.32) continue;
      add(group, new THREE.PlaneGeometry(0.12, 0.16), lit[(k + r + c) % 2], [bx - bw / 2 + 0.22 + c * (bw - 0.44) / 2, r * 0.45, bz + 0.16], [0, 0, 0], 1, false);
    }
  }
  const dotColors = ["#ffcf8a", "#7fb6ff", "#ff6b6b", "#ffe8b0", "#8ff0ff"];
  const dotTex = glowTexture();
  for (let k = 0; k < 26; k++) {
    const m = new THREE.MeshBasicMaterial({ map: dotTex, color: dotColors[k % dotColors.length], transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending, fog: false, toneMapped: false, opacity: 0.85 });
    const sz = 0.12 + hash(k + 300, seed) * 0.18;
    add(group, new THREE.PlaneGeometry(sz, sz), m, [-6 + hash(k + 100, seed) * 12, 0.3 + hash(k + 200, seed) * 4.2, -7 - hash(k + 400, seed) * 3], [0, 0, 0], 1, false);
  }
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
  // the warm light on the person's face (a desk lamp out of frame, front left)
  const warm = new THREE.PointLight("#ffb070", 2.4, 3.2, 1.5);
  warm.position.set(...L.warm_light);
  group.add(warm);
  const wallGlowM = wallGlow(group, [-0.6, 1.6, wz + 0.12], 4);
  return {
    apply(p) {
      floor.color.copy(p.floor); wallMat.color.copy(p.wall); frameMat.color.copy(p.wall).multiplyScalar(0.55);
      wood.color.set("#5a3d29").lerp(p.floor, 0.15); plastic.color.set("#1a1c22");
      warm.color.copy(p.key); monLight.color.copy(p.rim).lerp(new THREE.Color("#7fa8ff"), 0.5);
      wallGlowM.color.copy(p.rim).multiplyScalar(0.6);
    },
    lights: { key: 0.3, rim: 0.55, hemi: 0.45, front: 0.6 }, fog: [7, 40],
  };
}

const SETS = { minimal, modern, cinematic, cozy, historic, prehistoric, office };

export function buildSet(scene, kind, seed = 1) {
  const group = new THREE.Group();
  scene.add(group);
  const set = (SETS[kind] ?? modern)(group, seed);
  scene.fog = new THREE.Fog("#000000", ...(set.fog ?? [7, 18]));
  return set;
}
