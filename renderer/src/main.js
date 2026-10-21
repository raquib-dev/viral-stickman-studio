// Renderer entry: window.vss.load(scene) builds a scene from a scene plan; window.vss.frame(i)
// renders frame i and returns it as a PNG data URL. render.mjs drives it from a headless browser.
import "@fontsource/inter/400.css";
import "@fontsource/inter/800.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import * as THREE from "three";
import * as SkeletonUtils from "three/addons/utils/SkeletonUtils.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { BokehPass } from "three/addons/postprocessing/BokehPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { CLIPS, EXPRESSIONS, Stickman, loadRig } from "./rig.js";
import { THEMES, animateElement, badge, buildRoom, codePanel } from "./world.js";
import { ease, lerp, noise1, segment } from "./util.js";

const FinishShader = {
  // vignette + film grain; grain is seeded by the frame number, so it is deterministic
  uniforms: { tDiffuse: { value: null }, uFrame: { value: 0 }, uVignette: { value: 0.35 }, uGrain: { value: 0.035 } },
  vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
  fragmentShader: `uniform sampler2D tDiffuse; uniform float uFrame, uVignette, uGrain; varying vec2 vUv;
    float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233)) + uFrame*0.618) * 43758.5453); }
    void main(){ vec4 c = texture2D(tDiffuse, vUv); vec2 d = vUv - 0.5;
      float v = smoothstep(0.8, 0.2, length(d * vec2(1.0, 0.8))); c.rgb *= mix(1.0 - uVignette, 1.0, v);
      c.rgb += (h(vUv * 1000.0) - 0.5) * uGrain; gl_FragColor = c; }`,
};

const state = { ready: false };

async function load(spec) {
  await document.fonts.ready;
  await Promise.all(["400 40px Inter", "800 96px Inter", "400 44px 'JetBrains Mono'", "500 40px 'JetBrains Mono'"].map((f) => document.fonts.load(f)));
  const W = spec.width ?? 720, H = spec.height ?? 1280;
  const theme = THEMES[spec.theme] ?? THEMES["warm-dark"];
  document.body.innerHTML = "";
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(1);
  renderer.setSize(W, H);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = spec.exposure ?? 1.0;
  document.body.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  buildRoom(scene, theme);
  const camera = new THREE.PerspectiveCamera(35, W / H, 0.05, 60);

  const gltf = await loadRig(spec.rig ?? "./models/stickman-rig.glb");
  const actors = (spec.actors ?? []).map((a, i) => {
    const s = new Stickman(gltf, { SkeletonUtils, color: a.color ?? theme.ink, seed: (spec.seed ?? 1) + i * 17 });
    const [x, y, z] = a.position ?? [0, 0, 0];
    s.group.position.set(x, y, z);
    s.group.rotation.y = a.facing ?? 0;
    scene.add(s.group);
    return { spec: a, rig: s };
  });
  const elements = [
    ...(spec.panels ?? []).map((p) => codePanel(p, theme)),
    ...(spec.badges ?? []).map((b) => badge(b, theme)),
  ];
  for (const el of elements) scene.add(el.group);

  const composer = new EffectComposer(renderer);
  composer.setPixelRatio(1);
  composer.setSize(W, H);
  composer.addPass(new RenderPass(scene, camera));
  const q = spec.quality ?? "high";
  const bl = spec.bloom ?? {};
  if (q !== "draft") composer.addPass(new UnrealBloomPass(new THREE.Vector2(W, H), bl.strength ?? 0.7, bl.radius ?? 0.45, bl.threshold ?? 0.85));
  let bokeh = null;
  if (q === "high" && spec.dof !== false) {
    bokeh = new BokehPass(scene, camera, { focus: 3.5, aperture: spec.dof?.aperture ?? 0.0012, maxblur: spec.dof?.maxblur ?? 0.006 });
    composer.addPass(bokeh);
  }
  composer.addPass(new OutputPass());
  const finish = new ShaderPass(FinishShader);
  composer.addPass(finish);

  const gl = renderer.getContext();
  const dbg = gl.getExtension("WEBGL_debug_renderer_info");
  Object.assign(state, {
    spec, renderer, scene, camera, composer, actors, elements, bokeh, finish, W, H,
    fps: spec.fps ?? 24, frames: Math.round((spec.duration ?? 10) * (spec.fps ?? 24)),
    gpu: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : "unknown",
  });
  return { frames: state.frames, fps: state.fps, width: W, height: H, gpu: state.gpu };
}

const v3 = (a) => new THREE.Vector3(a[0], a[1], a[2]);

function placeCamera(t) {
  const { spec, camera, actors } = state;
  const keys = spec.camera?.length ? spec.camera : [{ t: 0, pos: [0, 1.5, 4.2], look: [0, 1.3, 0], fov: 35 }];
  const sg = segment(keys, t);
  const k = ease(sg.b.ease ?? "inOutCubic", sg.k);
  const pos = v3(sg.a.pos).lerp(v3(sg.b.pos), k);
  const look = v3(sg.a.look).lerp(v3(sg.b.look), k);
  camera.fov = lerp(sg.a.fov ?? 35, sg.b.fov ?? sg.a.fov ?? 35, k);
  const shake = spec.handheld ?? 0.012;
  pos.x += noise1(t * 0.7, 3) * shake; pos.y += noise1(t * 0.6, 4) * shake;
  camera.position.copy(pos);
  camera.lookAt(look);
  camera.updateProjectionMatrix();
  if (state.bokeh) {
    const target = actors[0]?.rig.headWorld() ?? look;
    state.bokeh.uniforms.focus.value = camera.position.distanceTo(target);
  }
}

function frame(i) {
  const t = i / state.fps;
  for (const a of state.actors) a.rig.update(a.spec, t);
  state.elements.forEach((el, k) => animateElement(el, t, k + 1));
  placeCamera(t);
  state.finish.uniforms.uFrame.value = i;
  state.composer.render();
  return state.renderer.domElement.toDataURL("image/png");
}

function debug(t) {
  const r = state.actors[0].rig;
  r.update(state.actors[0].spec, t);
  const f = (v) => v.toArray().map((x) => +x.toFixed(3));
  const S = r.segs, J = r.joints;
  return { hipScale: r.hipScale, knL: f(J.knL.position), ulL: [f(S.ulL.position), +S.ulL.scale.y.toFixed(3)], llL: [f(S.llL.position), +S.llL.scale.y.toFixed(3)],
    hips: f(J.hips.position), foot: f(J.footL.position), raw: ["UpperLegL", "LowerLegL", "FootL", "Hips"].map((n) => [n, f(r._p(n))]) };
}

window.vss = { load, frame, debug, CLIPS, EXPRESSIONS: Object.keys(EXPRESSIONS), get ready() { return true; } };
