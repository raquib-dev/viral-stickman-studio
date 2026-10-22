// Renderer entry: window.vss.load(scene) builds a scene from a scene plan; window.vss.frame(i) renders
// frame i and returns it as a PNG data URL. render.mjs drives it from a headless browser.
import "@fontsource/inter/400.css";
import "@fontsource/inter/800.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/caveat/400.css";
import "@fontsource/caveat/700.css";
import "@fontsource/eb-garamond/400.css";
import "@fontsource/eb-garamond/700.css";
import * as THREE from "three";
import * as SkeletonUtils from "three/addons/utils/SkeletonUtils.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { BokehPass } from "three/addons/postprocessing/BokehPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import catalog from "../catalog.json";
import { buildLights, buildSet } from "./env.js";
import { PROPS, animateProp, buildProp, propMaterials } from "./props.js";
import { CLIPS, EXPRESSIONS, GESTURES, HATS, Stickman, loadRig } from "./rig.js";
import { MOODS, SKILL_STYLE, STYLES, mixPalette, resolvePalette } from "./styles.js";
import { clamp, ease, lerp, noise1, segment, stepFade } from "./util.js";
import { LEGACY_THEMES, animateElement, badge, panel } from "./world.js";

const FinishShader = {
  // colour grade (saturation, contrast, warmth) + transitions (fade, iris, wipe) + vignette + seeded grain
  uniforms: {
    tDiffuse: { value: null }, uFrame: { value: 0 }, uVignette: { value: 0.35 }, uGrain: { value: 0.035 },
    uSat: { value: 1 }, uContrast: { value: 1 }, uWarm: { value: 0 }, uAspect: { value: 0.5625 },
    uFade: { value: 0 }, uFadeColor: { value: new THREE.Color() }, uIris: { value: -1 }, uWipe: { value: -1 },
  },
  vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
  fragmentShader: `uniform sampler2D tDiffuse; uniform float uFrame, uVignette, uGrain, uSat, uContrast, uWarm, uAspect, uFade, uIris, uWipe;
    uniform vec3 uFadeColor; varying vec2 vUv;
    float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233)) + uFrame*0.618) * 43758.5453); }
    void main(){
      vec4 c = texture2D(tDiffuse, vUv);
      float l = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
      c.rgb = mix(vec3(l), c.rgb, uSat);
      c.rgb = (c.rgb - 0.5) * uContrast + 0.5;
      c.rgb *= vec3(1.0 + 0.09 * uWarm, 1.0 + 0.02 * uWarm, 1.0 - 0.1 * uWarm);
      vec2 d = vUv - 0.5;
      float v = smoothstep(0.8, 0.2, length(d * vec2(1.0, 0.8))); c.rgb *= mix(1.0 - uVignette, 1.0, v);
      c.rgb += (h(vUv * 1000.0) - 0.5) * uGrain;
      if (uIris >= 0.0) { float r = length(d * vec2(uAspect, 1.0)); c.rgb = mix(c.rgb, uFadeColor, smoothstep(uIris - 0.01, uIris + 0.01, r)); }
      if (uWipe >= 0.0) { c.rgb = mix(c.rgb, uFadeColor, step(vUv.x, uWipe)); }
      c.rgb = mix(c.rgb, uFadeColor, uFade);
      gl_FragColor = c; }`,
};

const state = { ready: false };
const V = (a) => new THREE.Vector3(a[0], a[1] ?? 0, a[2] ?? 0);

/** Style, theme and mood track from a scene (with Phase 1 "theme" names still accepted). */
function lookOf(spec) {
  const legacy = LEGACY_THEMES[spec.theme];
  const style = SKILL_STYLE[spec.style] ?? (STYLES[spec.style] ? spec.style : legacy?.style ?? "modern");
  const theme = spec.theme === "light" || legacy?.theme === "light" ? "light" : "dark";
  let mood = spec.mood ?? legacy?.mood ?? "neutral";
  if (typeof mood === "string") mood = [{ t: 0, mood }];
  return { style, theme, mood };
}

async function load(spec) {
  await document.fonts.ready;
  await Promise.all(["400 40px Inter", "800 96px Inter", "400 44px 'JetBrains Mono'", "500 40px 'JetBrains Mono'",
    "400 58px Caveat", "700 72px Caveat", "400 44px 'EB Garamond'", "700 54px 'EB Garamond'"].map((f) => document.fonts.load(f)));
  const W = spec.width ?? 720, H = spec.height ?? 1280;
  const look = lookOf(spec);
  const style = STYLES[look.style];
  const palettes = Object.fromEntries(look.mood.map((m) => [`${m.mood}:${m.strength ?? 1}`, resolvePalette(look.style, look.theme, m.mood, m.strength ?? 1)]));
  const pal0 = palettes[`${look.mood[0].mood}:${look.mood[0].strength ?? 1}`];
  document.body.innerHTML = "";
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(1);
  renderer.setSize(W, H);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = spec.exposure ?? (look.theme === "light" ? 0.95 : 1.0);
  document.body.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color();
  const set = buildSet(scene, spec.set ?? style.env, spec.seed ?? 1);
  const lights = buildLights(scene);
  const camera = new THREE.PerspectiveCamera(35, W / H, 0.05, 80);

  const gltf = await loadRig(spec.rig ?? "./models/stickman-rig.glb");
  const actors = (spec.actors ?? []).map((a, i) => {
    const s = new Stickman(gltf, { SkeletonUtils, color: a.color ?? `#${pal0.ink.getHexString()}`, seed: (spec.seed ?? 1) + i * 17,
      material: style.char.material, roughness: style.char.roughness, hat: a.hat, hatColor: a.hat_color, limbs: a.limbs ?? spec.limbs });
    scene.add(s.group);
    return { spec: a, rig: s, id: a.id ?? `actor${i}` };
  });
  const propMats = propMaterials();
  const props = (spec.props ?? []).map((p, i) => {
    const pr = buildProp(p, propMats);
    scene.add(pr.group);
    return { ...pr, id: p.id ?? `${p.type}${i}` };
  });
  const elCtx = { pal: pal0, skin: spec.card ?? style.card, font: style.font };
  const elements = [...(spec.panels ?? []).map((p) => panel(p, elCtx)), ...(spec.badges ?? []).map((b) => badge(b, elCtx))];
  for (const el of elements) scene.add(el.group);

  const composer = new EffectComposer(renderer);
  composer.setPixelRatio(1);
  composer.setSize(W, H);
  composer.addPass(new RenderPass(scene, camera));
  const q = spec.quality ?? "high";
  const bl = spec.bloom ?? {};
  if (q !== "draft") composer.addPass(new UnrealBloomPass(new THREE.Vector2(W, H), bl.strength ?? style.post.bloom, bl.radius ?? 0.45, bl.threshold ?? 0.85));
  let bokeh = null;
  if (q === "high" && spec.dof !== false) {
    bokeh = new BokehPass(scene, camera, { focus: 3.5, aperture: spec.dof?.aperture ?? 0.0012, maxblur: spec.dof?.maxblur ?? 0.006 });
    composer.addPass(bokeh);
  }
  composer.addPass(new OutputPass());
  const finish = new ShaderPass(FinishShader);
  finish.uniforms.uVignette.value = style.post.vignette;
  finish.uniforms.uGrain.value = style.post.grain;
  finish.uniforms.uAspect.value = W / H;
  composer.addPass(finish);

  const gl = renderer.getContext();
  const dbg = gl.getExtension("WEBGL_debug_renderer_info");
  Object.assign(state, {
    spec, look, palettes, renderer, scene, camera, composer, actors, props, elements, bokeh, finish, set, lights, propMats, W, H,
    vertical: H > W, fps: spec.fps ?? 24, frames: Math.round((spec.duration ?? 10) * (spec.fps ?? 24)),
    gpu: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : "unknown",
  });
  return { frames: state.frames, fps: state.fps, width: W, height: H, gpu: state.gpu, style: look.style, theme: look.theme,
    moods: look.mood.map((m) => m.mood) };
}

// ---- time-dependent pieces -------------------------------------------------------------------

function paletteAt(t) {
  const keys = state.look.mood;
  const [prev, cur, w] = stepFade(keys, t, state.spec.mood_fade ?? 0.8);
  const a = state.palettes[`${prev.mood}:${prev.strength ?? 1}`], b = state.palettes[`${cur.mood}:${cur.strength ?? 1}`];
  return prev === cur ? b : mixPalette(a, b, ease("inOutSine", w));
}

function pathPos(path, t) {
  const sg = segment(path, t);
  const k = ease(sg.b.ease ?? "inOutSine", sg.k);
  const a = sg.a.pos, b = sg.b.pos;
  const ax = a[0], az = a.length === 3 ? a[2] : a[1], bx = b[0], bz = b.length === 3 ? b[2] : b[1];
  return new THREE.Vector3(lerp(ax, bx, k), 0, lerp(az, bz, k));
}

/** Actor root position, speed and distance walked at time t (distance integrated, so it is exact). */
function actorMotion(a, t) {
  const sp = a.spec;
  if (!sp.path?.length) {
    const p = sp.position ?? [0, 0, 0];
    return { pos: V(p), speed: 0, dist: 0, vel: new THREE.Vector3() };
  }
  const dt = 1 / 60;
  const pos = pathPos(sp.path, t);
  const vel = pathPos(sp.path, t + dt).sub(pathPos(sp.path, Math.max(0, t - dt))).divideScalar(t > dt ? 2 * dt : dt);
  let dist = 0, prev = pathPos(sp.path, 0);
  for (let s = dt; s <= t + 1e-9; s += dt) { const p = pathPos(sp.path, s); dist += p.distanceTo(prev); prev = p; }
  return { pos, speed: vel.length(), dist, vel };
}

const SHOTS = {
  // [distance, camera height above floor, look height, fov] for a 9:16 frame (16:9 pulls in a little)
  closeup: [1.25, 1.62, 1.58, 32], medium: [3.0, 1.45, 1.2, 36], wide: [5.0, 1.9, 1.0, 40],
  low: [2.4, 0.55, 1.3, 38], high: [3.4, 3.2, 0.9, 38], full: [3.8, 1.3, 0.95, 36],
};

function headOf(id, at) {
  const a = state.actors.find((x) => x.id === id) ?? state.actors[0];
  if (!a) return new THREE.Vector3(0, 1.6, 0);
  return actorMotion(a, at).pos.add(new THREE.Vector3(0, 1.62, 0));
}

/** A camera key as concrete {pos, look, fov}: explicit, or a named shot that follows its target. */
function resolveKey(key, t) {
  if (!key.shot) return { pos: V(key.pos), look: V(key.look), fov: key.fov ?? 35 };
  const s = typeof key.shot === "string" ? { type: key.shot } : key.shot;
  const [dist0, camY, lookY, fov] = SHOTS[s.type] ?? SHOTS.medium;
  const dist = dist0 * (state.vertical ? 1 : 0.8) * (s.zoom ?? 1);
  const ids = [].concat(s.target ?? state.actors[0]?.id ?? []);
  let centre;
  if (s.type === "two_shot" || ids.length > 1) {
    const hs = (ids.length > 1 ? ids : state.actors.map((a) => a.id)).map((id) => headOf(id, t));
    centre = hs.reduce((acc, h) => acc.add(h), new THREE.Vector3()).divideScalar(Math.max(1, hs.length));
    const spread = hs.length > 1 ? hs[0].distanceTo(hs[hs.length - 1]) : 0;
    // a 9:16 frame is narrow: back off far enough to keep both figures, head to toe, inside it
    const d = (state.vertical ? Math.max(4.2, spread * 4.4) : Math.max(2.6, spread * 1.6)) * (s.zoom ?? 1);
    return { pos: centre.clone().add(new THREE.Vector3((s.side ?? 0.15) * d, -0.25, d)), look: centre.clone().add(new THREE.Vector3(0, -0.7, 0)), fov: 36 };
  }
  if (s.type === "over_shoulder" && ids.length && s.subject) {
    const from = headOf(ids[0], t), to = headOf(s.subject, t);
    const dir = to.clone().sub(from).setY(0).normalize();
    const pos = from.clone().addScaledVector(dir, -0.9).add(new THREE.Vector3(dir.z * 0.35, 0.08, -dir.x * 0.35));
    return { pos, look: to, fov: 34 };
  }
  const head = headOf(ids[0], t);
  const base = head.clone().setY(0);
  const ang = (s.angle ?? 0) + (s.side ?? 0);
  const pos = base.clone().add(new THREE.Vector3(Math.sin(ang) * dist, camY, Math.cos(ang) * dist));
  const lookAt = base.clone().add(new THREE.Vector3(0, s.type === "closeup" ? head.y - 0.04 : lookY, 0));
  return { pos, look: lookAt, fov };
}

function placeCamera(t) {
  const { spec, camera } = state;
  const keys = spec.camera?.length ? spec.camera : [{ t: 0, shot: "medium" }];
  const sg = segment(keys, t);
  const k = ease(sg.b.ease ?? "inOutCubic", sg.k);
  const a = resolveKey(sg.a, t), b = resolveKey(sg.b, t);
  const pos = a.pos.lerp(b.pos, k), look = a.look.lerp(b.look, k);
  if (sg.b.orbit) pos.sub(look).applyAxisAngle(new THREE.Vector3(0, 1, 0), sg.b.orbit * k).add(look);
  camera.fov = lerp(a.fov, b.fov, k);
  const shake = spec.handheld ?? 0.012;
  pos.x += noise1(t * 0.7, 3) * shake; pos.y += noise1(t * 0.6, 4) * shake;
  camera.position.copy(pos);
  camera.lookAt(look);
  camera.updateProjectionMatrix();
}

function transitions(t, pal) {
  const tr = state.spec.transition ?? {};
  const dur = tr.dur ?? 0.4, end = state.frames / state.fps;
  const u = state.finish.uniforms;
  u.uFadeColor.value.copy(pal.bg).multiplyScalar(0.6);
  u.uFade.value = 0; u.uIris.value = -1; u.uWipe.value = -1;
  const kin = 1 - clamp(t / dur), kout = clamp((t - (end - dur)) / dur);
  const apply = (kind, k) => {
    if (k <= 0 || !kind || kind === "none") return;
    if (kind === "fade") u.uFade.value = Math.max(u.uFade.value, ease("inOutSine", k));
    if (kind === "iris") u.uIris.value = lerp(0.8, 0.0, ease("inOutCubic", k));
    if (kind === "wipe") u.uWipe.value = ease("inOutCubic", k);
  };
  apply(tr.in, kin);
  apply(tr.out, kout);
}

function resolver(t) {
  return (target, group) => {
    let w = null;
    if (Array.isArray(target)) w = V(target);
    else if (target === "camera") w = state.camera.position.clone();
    else {
      const a = state.actors.find((x) => x.id === target);
      if (a) w = a.rig.headWorld();
      const p = state.props.find((x) => x.id === target);
      if (p) w = p.group.getWorldPosition(new THREE.Vector3()).add(new THREE.Vector3(0, 0.3 * (p.spec.scale ?? 1), 0));
    }
    return w && group ? group.worldToLocal(w) : w;
  };
}

function frame(i) {
  const t = i / state.fps;
  const pal = paletteAt(t);
  state.scene.background.copy(pal.bg);
  state.scene.fog.color.copy(pal.bg);
  state.set.apply(pal, t);
  state.lights.apply(pal, state.set.lights);
  state.propMats.apply(pal);
  // place actors first (camera shots follow them), then the camera, then pose them (look-at needs the camera)
  const motions = state.actors.map((a) => actorMotion(a, t));
  state.actors.forEach((a, k) => {
    const m = motions[k];
    a.rig.group.position.copy(m.pos);
    const mv = clamp(m.speed / 0.35);
    const toCam = Math.atan2(state.camera.position.x - m.pos.x, state.camera.position.z - m.pos.z);
    const rest = typeof a.spec.facing === "number" ? a.spec.facing : a.spec.facing === "camera" ? toCam : 0;
    const moving = mv > 0 ? Math.atan2(m.vel.x, m.vel.z) : rest;
    let d = moving - rest;
    d = Math.atan2(Math.sin(d), Math.cos(d));
    a.rig.group.rotation.y = rest + d * ease("inOutSine", mv);
  });
  placeCamera(t);
  const resolve = resolver(t);
  state.actors.forEach((a, k) => a.rig.update(a.spec, t, { speed: motions[k].speed, dist: motions[k].dist, resolve, ink: a.spec.color ? null : pal.ink }));
  state.props.forEach((p, k) => {
    const hold = p.spec.hold;
    let hand = null;
    if (hold && t >= (hold.t ?? 0) && t <= (hold.until ?? Infinity)) {
      const a = state.actors.find((x) => x.id === (hold.actor ?? state.actors[0]?.id));
      if (a?.rig.hands) hand = a.rig.group.localToWorld(a.rig.hands[hold.hand ?? "R"].clone());
    }
    animateProp(p, t, k + 1, pal, hand);
  });
  state.elements.forEach((el, k) => animateElement(el, t, k + 1, pal));
  if (state.bokeh) {
    const target = state.actors[0]?.rig.headWorld() ?? new THREE.Vector3(0, 1.5, 0);
    state.bokeh.uniforms.focus.value = state.camera.position.distanceTo(target);
  }
  const u = state.finish.uniforms;
  u.uFrame.value = i; u.uSat.value = pal.sat; u.uContrast.value = pal.contrast; u.uWarm.value = pal.warm;
  transitions(t, pal);
  state.composer.render();
  return state.renderer.domElement.toDataURL("image/png");
}

/** What this build supports, checked against catalog.json (shared with the Python planner). */
function liveCatalog() {
  return { styles: Object.keys(STYLES), moods: Object.keys(MOODS), props: Object.keys(PROPS), gestures: GESTURES, hats: HATS,
    clips: CLIPS, expressions: Object.keys(EXPRESSIONS), shots: [...Object.keys(SHOTS), "two_shot", "over_shoulder"],
    transitions: ["none", "fade", "iris", "wipe"] };
}

window.vss = { load, frame, catalog: liveCatalog, fileCatalog: catalog, get ready() { return true; } };
