// Deterministic helpers. Nothing in the renderer may read a clock or Math.random:
// every frame is a pure function of (scene, t), so a re-render is identical.

export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, t) => a + (b - a) * t;

export const EASE = {
  linear: (t) => t,
  inOutSine: (t) => -(Math.cos(Math.PI * t) - 1) / 2,
  inOutCubic: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  outCubic: (t) => 1 - Math.pow(1 - t, 3),
  outQuint: (t) => 1 - Math.pow(1 - t, 5),
  outBack: (t) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); },
  outElastic: (t) => (t === 0 || t === 1 ? t : Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * (2 * Math.PI) / 3) + 1),
};
export const ease = (name, t) => (EASE[name] ?? EASE.inOutCubic)(clamp(t));

/** Seeded hash noise in [0, 1). */
export function hash(n, seed = 0) {
  const x = Math.sin(n * 127.1 + seed * 311.7) * 43758.5453123;
  return x - Math.floor(x);
}

/** Smooth 1-D value noise in [-1, 1]. */
export function noise1(t, seed = 0) {
  const i = Math.floor(t), f = t - i;
  const u = f * f * (3 - 2 * f);
  return lerp(hash(i, seed), hash(i + 1, seed), u) * 2 - 1;
}

/** Keyframes [{t, ...}] sorted by t: the segment around time t and its local progress. */
export function segment(keys, t) {
  if (!keys.length) return null;
  let i = 0;
  while (i + 1 < keys.length && keys[i + 1].t <= t) i++;
  const a = keys[i], b = keys[i + 1];
  if (!b || t < a.t) return { a, b: a, k: 0, i };
  return { a, b, k: (t - a.t) / Math.max(1e-6, b.t - a.t), i };
}

/** Value of a step track [{t, value}] with a cross-fade of `fade` seconds: returns [prev, cur, w]. */
export function stepFade(keys, t, fade = 0.3) {
  let i = -1;
  for (let k = 0; k < keys.length; k++) if (keys[k].t <= t) i = k;
  if (i < 0) return [keys[0], keys[0], 1];
  const cur = keys[i], prev = keys[i - 1] ?? cur;
  return [prev, cur, clamp((t - cur.t) / fade)];
}
