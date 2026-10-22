// UI elements in the scene: code/note panels and stat badges. All text is drawn by the engine on
// canvases (crisp at any resolution). The card skin follows the style pack: glow (modern), glass
// (cinematic), flat (minimal), paper (cozy), parchment (historic), slate (prehistoric). Frames and glows
// take the live palette, so they follow the mood.
import * as THREE from "three";
import { clamp, ease, lerp, noise1 } from "./util.js";

/** Scene files from Phase 1 used "theme": these map onto style + theme + mood. */
export const LEGACY_THEMES = {
  "warm-dark": { style: "modern", theme: "dark", mood: "neutral" },
  "cool-dark": { style: "modern", theme: "dark", mood: "tech" },
  light: { style: "minimal", theme: "light", mood: "neutral" },
};

const hex = (c) => `#${c.getHexString()}`;

function roundRect(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
}

const KW = /^(import|export|from|const|let|var|function|return|if|else|for|while|class|new|async|await|def|self|None|True|False|type|interface)$/;

/** Tiny syntax colouring: strings, comments, keywords, numbers, types, punctuation. */
function codeTokens(line, light) {
  const C = light ? { com: "#8a8f98", str: "#a3591b", num: "#b5482a", kw: "#7a3fd1", type: "#1f6fbf", id: "#1f2430", punct: "#5b6270" }
    : { com: "#6b7280", str: "#e8c07d", num: "#f0a36b", kw: "#c9a7ff", type: "#8ed1ff", id: "#e6e1d6", punct: "#9aa3b2" };
  const out = [];
  const re = /(\/\/.*$|#.*$)|('[^']*'|"[^"]*"|`[^`]*`)|\b(\d+(?:\.\d+)?)\b|([A-Za-z_]\w*)|(\s+)|(.)/g;
  let m;
  while ((m = re.exec(line))) {
    const [s] = m;
    out.push([s, m[1] ? C.com : m[2] ? C.str : m[3] ? C.num : m[4] ? (KW.test(s) ? C.kw : /^[A-Z]/.test(s) ? C.type : C.id) : C.punct]);
  }
  return out;
}

function canvasTexture(w, h, draw) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  draw(c.getContext("2d"), w, h);
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

/** Outline around a rounded rectangle; HDR colour for the glowing skins so bloom picks it up. */
function frameMesh(w, h, r, width) {
  const outer = roundedShape(w + width * 2, h + width * 2, r + width);
  outer.holes.push(roundedShape(w, h, r));
  return new THREE.Mesh(new THREE.ShapeGeometry(outer, 12), new THREE.MeshBasicMaterial({ toneMapped: false, transparent: true }));
}

const SKIN = {
  glow: { frame: 0.025, glow: 2.2, radius: 36, alpha: 0.94, shadow: false },
  glass: { frame: 0.012, glow: 1.6, radius: 28, alpha: 0.72, shadow: false },
  flat: { frame: 0, glow: 0, radius: 26, alpha: 1, shadow: true },
  paper: { frame: 0, glow: 0, radius: 10, alpha: 1, shadow: true, tilt: 0.04 },
  parchment: { frame: 0.012, glow: 0.9, radius: 6, alpha: 1, shadow: true },
  slate: { frame: 0.02, glow: 0.7, radius: 18, alpha: 1, shadow: true },
};

function paintCard(g, cw, ch, skin, pal, r) {
  const card = hex(pal.card);
  roundRect(g, 0, 0, cw, ch, r);
  if (skin === "parchment") {
    const lg = g.createRadialGradient(cw / 2, ch / 2, ch * 0.2, cw / 2, ch / 2, Math.max(cw, ch) * 0.75);
    lg.addColorStop(0, card); lg.addColorStop(1, "#b89a62");
    g.fillStyle = lg; g.fill();
  } else if (skin === "slate") {
    g.fillStyle = card; g.fill();
    g.globalAlpha = 0.08; g.fillStyle = "#ffffff";
    for (let i = 0; i < 40; i++) g.fillRect((i * 97) % cw, (i * 53) % ch, 40, 3);
    g.globalAlpha = 1;
  } else {
    g.fillStyle = card; g.globalAlpha = SKIN[skin].alpha; g.fill(); g.globalAlpha = 1;
  }
}

function elementGroup(w, h, tex, skinName, pal, radius) {
  const skin = SKIN[skinName] ?? SKIN.glow;
  const group = new THREE.Group();
  const face = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: tex, transparent: true }));
  const mats = [face.material];
  let frame = null;
  if (skin.frame > 0) {
    frame = frameMesh(w, h, radius, skin.frame);
    frame.position.z = -0.002;
    group.add(frame);
    mats.push(frame.material);
  }
  if (skin.shadow) {
    const sh = new THREE.Mesh(new THREE.PlaneGeometry(w * 1.04, h * 1.06), new THREE.MeshBasicMaterial({ color: "#000000", transparent: true, opacity: 0.25 }));
    sh.position.set(0.03, -0.035, -0.01);
    group.add(sh);
    mats.push(sh.material);
    sh.material.userData.maxOpacity = 0.25;
  }
  group.add(face);
  if (skin.tilt) group.rotation.z = skin.tilt;
  return { group, mats, frame, skin };
}

export function panel(spec, ctx) {
  const { pal, skin, font } = ctx;
  const kind = spec.kind ?? (spec.title?.match(/\.\w+$/) ? "code" : "note");
  const w = spec.w ?? 1.8, lines = spec.lines ?? [];
  const lineH = kind === "code" ? 0.145 : 0.16;
  const h = spec.h ?? Math.max(0.6, 0.34 + lines.length * lineH);
  const PX = 512, r = SKIN[skin]?.radius ?? 30;
  const light = pal.card.getHSL({}).l > 0.5;
  const inkCol = hex(pal.cardInk);
  const tex = canvasTexture(Math.round(w * PX), Math.round(h * PX), (g, cw, ch) => {
    paintCard(g, cw, ch, skin, pal, r);
    g.textBaseline = "middle";
    if (kind === "code") {
      g.fillStyle = light ? "#00000010" : "#ffffff10"; g.fillRect(0, 0, cw, 96);
      ["#ff5f57", "#febc2e", "#28c840"].forEach((c, i) => { g.fillStyle = c; g.beginPath(); g.arc(52 + i * 44, 48, 13, 0, 7); g.fill(); });
      g.font = "500 40px 'JetBrains Mono'"; g.fillStyle = inkCol;
      g.fillText(spec.title ?? "", 200, 50);
      g.font = "400 44px 'JetBrains Mono'";
      lines.forEach((ln, i) => {
        let x = 60;
        for (const [s, col] of codeTokens(ln, light)) { g.fillStyle = col; g.fillText(s, x, 160 + i * 74); x += g.measureText(s).width; }
      });
    } else {
      const big = font === "Caveat" ? 72 : 54, small = font === "Caveat" ? 58 : 44;
      const family = font === "EB Garamond" ? "'EB Garamond'" : font;
      g.fillStyle = hex(pal.accent);
      g.font = `700 ${big}px ${family}`;
      g.fillText(spec.title ?? "", 56, 70);
      g.fillStyle = inkCol; g.font = `400 ${small}px ${family}`;
      lines.forEach((ln, i) => {
        g.fillStyle = hex(pal.accent); g.beginPath(); g.arc(70, 160 + i * 82, 9, 0, 7); g.fill();
        g.fillStyle = inkCol; g.fillText(ln, 100, 160 + i * 82);
      });
    }
  });
  const el = elementGroup(w, h, tex, skin, pal, 0.07);
  return { ...el, spec };
}

export function badge(spec, ctx) {
  const { pal, skin, font } = ctx;
  const text = spec.text ?? "";
  const size = spec.size ?? 1;
  const family = font === "EB Garamond" ? "'EB Garamond'" : font;
  const weight = font === "Inter" ? 800 : 700;
  const hpx = 150;
  const measure = document.createElement("canvas").getContext("2d");
  measure.font = `${weight} 96px ${family}`;
  const wpx = Math.ceil(measure.measureText(text).width + 140);
  // 0.16 m tall at size 1; the width follows the text
  const h = 0.16 * size, w = h * (wpx / hpx);
  const dark = pal.card.getHSL({}).l < 0.5;
  const tex = canvasTexture(wpx, hpx, (g, cw, ch) => {
    if (skin === "glow" || skin === "glass") {
      roundRect(g, 0, 0, cw, ch, ch / 2);
      const lg = g.createLinearGradient(0, 0, 0, ch);
      lg.addColorStop(0, hex(pal.card.clone().lerp(pal.accent, 0.18))); lg.addColorStop(1, hex(pal.card));
      g.fillStyle = lg; g.fill();
      g.shadowColor = hex(pal.accent); g.shadowBlur = 18;
    } else paintCard(g, cw, ch, skin, pal, ch / 2);
    g.font = `${weight} 96px ${family}`; g.textAlign = "center"; g.textBaseline = "middle";
    g.fillStyle = dark ? "#fff7ea" : hex(pal.cardInk);
    g.fillText(text, cw / 2, ch / 2 + 4);
  });
  const el = elementGroup(w, h, tex, skin, pal, h / 2);
  return { ...el, spec };
}

/** Enter/exit motion shared by panels and badges, plus live frame colour from the palette. */
export function animateElement(el, t, seed, pal) {
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
  el.group.rotation.set(rot[0] + (1 - k) * 0.4, rot[1] + (1 - k) * -0.3, rot[2] + (el.skin.tilt ?? 0) * (seed % 2 ? 1 : -1));
  el.group.scale.setScalar((s.scale ?? 1) * lerp(0.85, 1, ease("outCubic", kin)));
  const op = ease("outCubic", kin) * (1 - kout);
  for (const m of el.mats) m.opacity = op * (m.userData.maxOpacity ?? 1);
  if (el.frame) el.frame.material.color.copy(s.glow ? new THREE.Color(s.glow) : pal.accent).multiplyScalar(Math.max(1, el.skin.glow));
}
