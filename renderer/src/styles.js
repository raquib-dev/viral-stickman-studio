// Style packs (the look of the whole video) and moods (the colour of each beat).
//
// A style decides the set, the character's material, the card skin, the fonts and the grade. It maps
// one-to-one to the directing skill's styles (project "style" field). A mood re-colours a style from the
// content: money beats go green-gold, warnings go red, calm beats go blue... Moods blend over time, so a
// clip can move from "danger" to "success" as the line turns.
import * as THREE from "three";
import { clamp } from "./util.js";

const P = (o) => o; // palette literal: bg, floor, wall, key, rim, fill, glow, accent, ink, card, cardInk

export const STYLES = {
  minimal: {
    label: "Classic Minimalist", skill: "1", env: "minimal", card: "flat", font: "Inter",
    char: { material: "clay", roughness: 0.6 }, post: { bloom: 0.35, vignette: 0.2, grain: 0.02 },
    palette: {
      dark: P({ bg: "#0e0f11", floor: "#141518", wall: "#101114", key: "#ffffff", rim: "#9fb4ff", fill: "#5d6b85",
        glow: "#ffffff", accent: "#ffd166", ink: "#f2f2f2", card: "#17181c", cardInk: "#f2f2f2" }),
      light: P({ bg: "#f4f2ee", floor: "#ebe7e0", wall: "#f6f4f0", key: "#ffffff", rim: "#ffd7a8", fill: "#b8c4d8",
        glow: "#ffffff", accent: "#e8602c", ink: "#262626", card: "#ffffff", cardInk: "#1d1d1d" }),
    },
  },
  modern: {
    label: "Modern Studio Tech", skill: "2A", env: "modern", card: "glow", font: "Inter",
    char: { material: "clay", roughness: 0.5 }, post: { bloom: 0.75, vignette: 0.35, grain: 0.035 },
    palette: {
      dark: P({ bg: "#120d0a", floor: "#24170f", wall: "#1a120d", key: "#ffc08a", rim: "#ff8a3d", fill: "#4a5a7a",
        glow: "#ff9a4d", accent: "#ffc76b", ink: "#f1ece4", card: "#14161b", cardInk: "#e6e1d6" }),
      light: P({ bg: "#e9edf3", floor: "#dfe4ec", wall: "#eef1f6", key: "#ffffff", rim: "#7cc4ff", fill: "#c9b8dc",
        glow: "#7cc4ff", accent: "#2f7cf6", ink: "#2b2f36", card: "#ffffff", cardInk: "#1f2430" }),
    },
  },
  cinematic: {
    label: "Cinematic Story", skill: "2B", env: "cinematic", card: "glass", font: "Inter",
    char: { material: "clay", roughness: 0.7 }, post: { bloom: 0.9, vignette: 0.55, grain: 0.05 },
    palette: {
      dark: P({ bg: "#07080b", floor: "#101218", wall: "#0a0c11", key: "#dfe8ff", rim: "#ffb36b", fill: "#2a3550",
        glow: "#8fb6ff", accent: "#ffcf8a", ink: "#ece8e1", card: "#0f1219", cardInk: "#eef2f7" }),
      light: P({ bg: "#d9d4cb", floor: "#c9c2b6", wall: "#ddd7cd", key: "#fff3e0", rim: "#ff9d5c", fill: "#8fa3c4",
        glow: "#ffd6a3", accent: "#b5482a", ink: "#2a2420", card: "#f4efe7", cardInk: "#2a2420" }),
    },
  },
  prehistoric: {
    label: "Prehistoric Hand-Drawn", skill: "3", env: "prehistoric", card: "slate", font: "Caveat",
    char: { material: "toon", roughness: 0.9 }, post: { bloom: 0.55, vignette: 0.45, grain: 0.06 },
    palette: {
      dark: P({ bg: "#1b120c", floor: "#3a2a1c", wall: "#2a1d14", key: "#ffb36b", rim: "#ff7a2e", fill: "#3b4a5c",
        glow: "#ff8a3d", accent: "#ffb347", ink: "#efe2c8", card: "#3b3027", cardInk: "#f3e6cc" }),
      light: P({ bg: "#e9d7b8", floor: "#c9ad82", wall: "#dcc59e", key: "#fff1d6", rim: "#ff9b4a", fill: "#9cb0a2",
        glow: "#ffcf8a", accent: "#b5562a", ink: "#3b2a1c", card: "#efe2c8", cardInk: "#3b2a1c" }),
    },
  },
  cozy: {
    label: "Cozy Storytelling", skill: "4", env: "cozy", card: "paper", font: "Caveat",
    char: { material: "toon", roughness: 0.8 }, post: { bloom: 0.6, vignette: 0.3, grain: 0.03 },
    palette: {
      dark: P({ bg: "#1d1410", floor: "#4a3122", wall: "#2f221b", key: "#ffcf99", rim: "#ff9f5a", fill: "#5a6e8a",
        glow: "#ffb46b", accent: "#ff9f5a", ink: "#fbf1e3", card: "#fff6e8", cardInk: "#3a2a20" }),
      light: P({ bg: "#f6e9d6", floor: "#c89a6c", wall: "#f3e2cb", key: "#fff4e2", rim: "#ffb27a", fill: "#c7d3e6",
        glow: "#ffd8a8", accent: "#e07a4f", ink: "#3a2a20", card: "#fffaf1", cardInk: "#3a2a20" }),
    },
  },
  historic: {
    label: "Historical Cartoon", skill: "5", env: "historic", card: "parchment", font: "EB Garamond",
    char: { material: "toon", roughness: 0.85 }, post: { bloom: 0.45, vignette: 0.45, grain: 0.05 },
    palette: {
      dark: P({ bg: "#17120c", floor: "#3b3226", wall: "#2a2219", key: "#ffd9a0", rim: "#ff9c4a", fill: "#56607a",
        glow: "#ffb35c", accent: "#c9a14a", ink: "#f2e6cf", card: "#efe0bf", cardInk: "#3a2b17" }),
      light: P({ bg: "#efe3c8", floor: "#cdb994", wall: "#e8d9b8", key: "#fff3da", rim: "#e0a35c", fill: "#a8b4c4",
        glow: "#ffe2a8", accent: "#8a2f24", ink: "#3a2b17", card: "#f5e9cf", cardInk: "#3a2b17" }),
    },
  },
};

/** The directing skill's style ids -> style packs. */
export const SKILL_STYLE = { "1": "minimal", "2A": "modern", "2B": "cinematic", "3": "prehistoric", "4": "cozy", "5": "historic" };

// Mood = colour offsets applied on top of a style. `tint` pulls the set colours a little toward it;
// accent/glow/rim/key replace or mix; sat/contrast/warm drive the final grade.
export const MOODS = {
  neutral: {},
  money: { accent: "#58d68d", glow: "#ffd166", rim: "#ffd166", tint: "#1f3a2a", key: "#fff1c9", sat: 1.08 },
  success: { accent: "#ffcf3d", glow: "#ffb02e", rim: "#ffcf3d", tint: "#3a2c10", key: "#fff0cc", sat: 1.12, contrast: 1.04 },
  danger: { accent: "#ff4d4d", glow: "#ff3b3b", rim: "#ff5a36", tint: "#3a0f0f", key: "#ffc4b8", sat: 1.05, contrast: 1.1 },
  calm: { accent: "#7cc4ff", glow: "#5aa9ff", rim: "#8fd0ff", tint: "#0f2236", key: "#e4f0ff", sat: 0.95 },
  tech: { accent: "#4de1ff", glow: "#00b3ff", rim: "#4de1ff", tint: "#08202c", key: "#dff6ff", sat: 1.05 },
  mystery: { accent: "#b48cff", glow: "#7b5cff", rim: "#6be2ff", tint: "#1a1033", key: "#d8ccff", sat: 1.0, contrast: 1.08 },
  nostalgia: { accent: "#e8b46b", glow: "#ffc785", rim: "#ffb46b", tint: "#3a2a14", key: "#ffe2b8", sat: 0.78, warm: 0.6 },
  sad: { accent: "#8aa2b8", glow: "#6c8aa6", rim: "#8aa2b8", tint: "#141c26", key: "#d6e0ea", sat: 0.6 },
  love: { accent: "#ff7aa8", glow: "#ff8fb4", rim: "#ff9fc0", tint: "#3a1424", key: "#ffe0ea", sat: 1.06 },
  nature: { accent: "#7ccf6b", glow: "#b6e36b", rim: "#ffd97a", tint: "#16301a", key: "#fff6d6", sat: 1.05 },
};

const COLOR_KEYS = ["bg", "floor", "wall", "key", "rim", "fill", "glow", "accent", "ink", "card", "cardInk"];

/** A style + theme + mood as concrete THREE.Colors and grade numbers. */
export function resolvePalette(styleKey, theme, moodKey, strength = 1) {
  const st = STYLES[styleKey] ?? STYLES.modern;
  const base = st.palette[theme === "light" ? "light" : "dark"];
  const m = MOODS[moodKey] ?? MOODS.neutral;
  const s = clamp(strength);
  const c = (k) => new THREE.Color(base[k]);
  const out = Object.fromEntries(COLOR_KEYS.map((k) => [k, c(k)]));
  if (m.tint) {
    const tint = new THREE.Color(m.tint);
    // dark sets take more tint than light ones (keeps light themes readable)
    const amt = (theme === "light" ? 0.12 : 0.22) * s;
    for (const k of ["bg", "floor", "wall"]) out[k].lerp(tint, amt);
  }
  for (const k of ["accent", "glow", "rim"]) if (m[k]) out[k].lerp(new THREE.Color(m[k]), 0.85 * s);
  if (m.key) out.key.lerp(new THREE.Color(m.key), 0.45 * s);
  out.sat = 1 + ((m.sat ?? 1) - 1) * s;
  out.contrast = 1 + ((m.contrast ?? 1) - 1) * s;
  out.warm = (m.warm ?? 0) * s;
  return out;
}

export function mixPalette(a, b, k) {
  const out = {};
  for (const key of COLOR_KEYS) out[key] = a[key].clone().lerp(b[key], k);
  for (const key of ["sat", "contrast", "warm"]) out[key] = a[key] + (b[key] - a[key]) * k;
  return out;
}

export const FONT = { Inter: "Inter", Caveat: "Caveat", "EB Garamond": "'EB Garamond'" };
