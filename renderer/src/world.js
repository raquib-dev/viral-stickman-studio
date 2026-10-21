// Room, lights and the glowing UI elements (code panels, stat badges, signs). All text is drawn by
// the engine on canvases, so it is crisp at any resolution (unlike text from a video model).
import * as THREE from "three";
import { clamp, ease, lerp, noise1 } from "./util.js";

export const THEMES = {
  "warm-dark": { bg: "#120d0a", floor: "#2a1b13", wall: "#1a120d", glow: "#ff9a4d", key: "#ffc08a", rim: "#ff8a3d",
    fill: "#4a5a7a", ink: "#f1ece4", accent: "#ffc76b", panel: "#14161b" },
  "cool-dark": { bg: "#0b0e14", floor: "#151a24", wall: "#0f131b", glow: "#4d9aff", key: "#cfe0ff", rim: "#6aa8ff",
    fill: "#3a2a4a", ink: "#eef2f7", accent: "#7cc4ff", panel: "#11151c" },
  light: { bg: "#efe9df", floor: "#e3dbcf", wall: "#f3eee6", glow: "#ffd2a1", key: "#fff4e6", rim: "#ffb36b",
    fill: "#b9c7dc", ink: "#2b2622", accent: "#e8602c", panel: "#ffffff" },
};

export function buildRoom(scene, theme) {
  scene.background = new THREE.Color(theme.bg);
  scene.fog = new THREE.Fog(theme.bg, 7, 18);
  const floor = new THREE.Mesh(new THREE.CircleGeometry(30, 48),
    new THREE.MeshStandardMaterial({ color: theme.floor, roughness: 0.75, metalness: 0.05 }));
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);
  // back wall with a soft warm glow behind the character
  const c = document.createElement("canvas");
  c.width = 512; c.height = 512;
  const g = c.getContext("2d");
  g.fillStyle = theme.wall; g.fillRect(0, 0, 512, 512);
  const rg = g.createRadialGradient(256, 300, 10, 256, 300, 300);
  rg.addColorStop(0, theme.glow + "55"); rg.addColorStop(1, theme.glow + "00");
  g.fillStyle = rg; g.fillRect(0, 0, 512, 512);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const wall = new THREE.Mesh(new THREE.PlaneGeometry(26, 14), new THREE.MeshBasicMaterial({ map: tex, fog: true }));
  wall.position.set(0, 6, -7);
  scene.add(wall);

  scene.add(new THREE.HemisphereLight(theme.key, theme.floor, 0.6));
  const front = new THREE.DirectionalLight(theme.key, 0.55);   // soft camera-side fill so faces never go black
  front.position.set(0.5, 1.6, 6);
  scene.add(front);
  const key = new THREE.DirectionalLight(theme.key, 2.2);
  key.position.set(-1.6, 6.5, 3.2);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.camera.left = -4; key.shadow.camera.right = 4; key.shadow.camera.top = 4; key.shadow.camera.bottom = -2;
  key.shadow.radius = 4;
  key.shadow.bias = -0.0004;
  scene.add(key);
  const rim = new THREE.SpotLight(theme.rim, 28, 14, Math.PI / 6, 0.6, 1.4);
  rim.position.set(2.2, 3.4, -3.2);
  rim.target.position.set(0, 1.2, 0);
  scene.add(rim, rim.target);
  const fill = new THREE.DirectionalLight(theme.fill, 0.5);
  fill.position.set(3, 2, 3);
  scene.add(fill);
}

// ---- canvas helpers -------------------------------------------------------------------------

function roundRect(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
}

const KW = /\b(import|export|from|const|let|var|function|return|if|else|for|while|class|new|async|await|def|self|None|True|False|type|interface)\b/g;

/** Tiny syntax colouring for code panels: strings, comments, keywords, numbers, punctuation. */
function codeTokens(line) {
  const out = [];
  const re = /(\/\/.*$|#.*$)|('[^']*'|"[^"]*"|`[^`]*`)|\b(\d+(?:\.\d+)?)\b|([A-Za-z_]\w*)|(\s+)|(.)/g;
  let m;
  while ((m = re.exec(line))) {
    const [s] = m;
    if (m[1]) out.push([s, "#6b7280"]);
    else if (m[2]) out.push([s, "#e8c07d"]);
    else if (m[3]) out.push([s, "#f0a36b"]);
    else if (m[4]) out.push([s, KW.test(s) ? "#c9a7ff" : /^[A-Z]/.test(s) ? "#8ed1ff" : "#e6e1d6"]);
    else out.push([s, "#9aa3b2"]);
    KW.lastIndex = 0;
  }
  return out;
}

function canvasTexture(w, h, draw) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const g = c.getContext("2d");
  draw(g, w, h);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

function roundedShape(w, h, r) {
  const s = new THREE.Shape();
  s.moveTo(-w / 2 + r, -h / 2);
  s.lineTo(w / 2 - r, -h / 2); s.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
  s.lineTo(w / 2, h / 2 - r); s.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2);
  s.lineTo(-w / 2 + r, h / 2); s.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
  s.lineTo(-w / 2, -h / 2 + r); s.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
  return s;
}

/** A glowing outline (HDR colour, so bloom picks it up) around a rounded rectangle. */
function glowFrame(w, h, r, color, width = 0.025, intensity = 2.2) {
  const outer = roundedShape(w + width * 2, h + width * 2, r + width);
  outer.holes.push(roundedShape(w, h, r));
  const col = new THREE.Color(color).multiplyScalar(intensity);
  const m = new THREE.Mesh(new THREE.ShapeGeometry(outer, 12), new THREE.MeshBasicMaterial({ color: col, toneMapped: false, transparent: true }));
  return m;
}

// ---- elements -------------------------------------------------------------------------------

export function codePanel(spec, theme) {
  const w = spec.w ?? 2.2, lines = spec.lines ?? [];
  const h = spec.h ?? Math.max(0.7, 0.32 + lines.length * 0.15);
  const PX = 512;
  const tex = canvasTexture(Math.round(w * PX), Math.round(h * PX), (g, cw, ch) => {
    roundRect(g, 0, 0, cw, ch, 36);
    g.fillStyle = theme.panel; g.globalAlpha = 0.94; g.fill(); g.globalAlpha = 1;
    g.fillStyle = "#ffffff10"; g.fillRect(0, 0, cw, 96);
    ["#ff5f57", "#febc2e", "#28c840"].forEach((c, i) => { g.fillStyle = c; g.beginPath(); g.arc(52 + i * 44, 48, 13, 0, 7); g.fill(); });
    g.font = "500 40px 'JetBrains Mono'"; g.fillStyle = "#e6e1d6"; g.textBaseline = "middle";
    g.fillText(spec.title ?? "", 200, 50);
    g.font = "400 44px 'JetBrains Mono'";
    lines.forEach((ln, i) => {
      let x = 60;
      for (const [s, col] of codeTokens(ln)) { g.fillStyle = col; g.fillText(s, x, 160 + i * 74); x += g.measureText(s).width; }
    });
  });
  const group = new THREE.Group();
  const face = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: tex, transparent: true, toneMapped: true }));
  const frame = glowFrame(w, h, 0.07, spec.glow ?? theme.accent);
  frame.position.z = -0.002;
  group.add(frame, face);
  return { group, mats: [face.material, frame.material], spec };
}

export function badge(spec, theme) {
  const text = spec.text ?? "";
  const size = spec.size ?? 1;
  const hpx = 150;
  const measure = document.createElement("canvas").getContext("2d");
  measure.font = "800 96px Inter";
  const wpx = Math.ceil(measure.measureText(text).width + 140);
  // 0.16 m tall at size 1, width follows the text, so "19 files changed • +1,256" is ~1.5 m wide
  const h = 0.16 * size, w = h * (wpx / hpx);
  const tex = canvasTexture(wpx, hpx, (g, cw, ch) => {
    roundRect(g, 0, 0, cw, ch, ch / 2);
    const lg = g.createLinearGradient(0, 0, 0, ch);
    lg.addColorStop(0, "#3a2a1c"); lg.addColorStop(1, "#1c140e");
    g.fillStyle = lg; g.fill();
    g.font = "800 96px Inter"; g.fillStyle = "#fff4e2"; g.textAlign = "center"; g.textBaseline = "middle";
    g.shadowColor = theme.accent; g.shadowBlur = 18;
    g.fillText(text, cw / 2, ch / 2 + 4);
  });
  const group = new THREE.Group();
  const face = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: tex, transparent: true }));
  const frame = glowFrame(w, h, h / 2, spec.glow ?? theme.accent, 0.018 * size, 2.6);
  frame.position.z = -0.002;
  group.add(frame, face);
  return { group, mats: [face.material, frame.material], spec };
}

/** Enter/exit animation shared by panels, badges and signs. */
export function animateElement(el, t, seed = 0) {
  const s = el.spec;
  const tin = s.t_in ?? 0, tout = s.t_out ?? Infinity, dur = s.enter ?? 0.7;
  const kin = clamp((t - tin) / dur), kout = clamp((t - tout) / 0.4);
  const vis = kin > 0 && kout < 1;
  el.group.visible = vis;
  if (!vis) return;
  const to = s.pos ?? [0, 1.5, 0], from = s.from ?? [to[0], to[1] - 0.6, to[2] - 1.2];
  const k = ease(s.ease ?? "outBack", kin);
  const bob = (s.float ?? 0.02) * noise1(t * 0.6 + seed * 7, seed);
  el.group.position.set(lerp(from[0], to[0], k), lerp(from[1], to[1], k) + bob, lerp(from[2], to[2], k));
  const rot = s.rot ?? [0, 0, 0];
  el.group.rotation.set(rot[0] + (1 - k) * 0.4, rot[1] + (1 - k) * -0.3, rot[2]);
  const sc = (s.scale ?? 1) * lerp(0.85, 1, ease("outCubic", kin));
  el.group.scale.setScalar(sc);
  const op = ease("outCubic", kin) * (1 - kout);
  for (const m of el.mats) m.opacity = op;
}
