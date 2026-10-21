import { useEffect, useState } from "react";
import { ErrorBox, Note, Section } from "../components/ui";
import { api } from "../lib/api";

const GATE_TITLES: Record<string, string> = { topic: "Pick the topic", hook: "Pick the hook", phase_a: "Approve Phase A", render_cost: "Confirm render cost" };

export default function Settings() {
  const [s, setS] = useState<any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api.get("/settings").then(setS).catch((e) => setErr(e.message)); }, []);
  if (!s) return err ? <ErrorBox>{err}</ErrorBox> : <div className="muted">Loading…</div>;
  const set = (path: string[], v: any) => setS((prev: any) => {
    const next = structuredClone(prev); let o = next;
    for (const k of path.slice(0, -1)) o = o[k];
    o[path[path.length - 1]] = v; return next;
  });
  const save = async () => {
    setErr(null); setMsg(null);
    try { setS(await api.put("/settings", s)); setMsg("Saved."); } catch (e: any) { setErr(e.message); }
  };
  return (
    <div className="grid gap-5" data-testid="settings">
      <h1 className="h1">Settings</h1>
      <Section title="Mode">
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={s.dry_run} onChange={(e) => set(["dry_run"], e.target.checked)} data-testid="dry-run" />
          Dry run: fixture agent + mock render + synthetic discovery. $0, no keys needed.</label>
        {!s.dry_run && <div className="mt-2"><Note tone="warn">Live mode: writing uses {s.agent.provider === "local" ? "your local LLM ($0)" : s.agent.provider === "hybrid" ? "Claude for direction and your local LLM for the rest" : "Claude (your ANTHROPIC_API_KEY or Claude login)"}; video uses {s.render.backend}{s.render.backend.startsWith("local-") ? " on this machine ($0)" : ""}. Discovery uses the YouTube Data API when its key is set. Paid renders still stop at the cost gate and the budget cap.</Note></div>}
      </Section>
      <Section title="API keys (read from .env; never shown, logged or stored)">
        <ul className="grid gap-1 text-sm" data-testid="keys">{Object.entries(s.keys).map(([k, v]) => (
          <li key={k}><span aria-hidden style={{ color: v ? "var(--good)" : "var(--text-muted)" }}>{v ? "✓" : "○"}</span> {k.toUpperCase()} {v ? "is set" : "not set"}</li>))}</ul>
        <p className="mt-2 text-xs text-ink-3">Edit .env in the project folder, then reload this page. See README → "API keys".</p>
      </Section>
      <Section title="Gates: pause for you, or decide automatically">
        <div className="grid gap-2 md:grid-cols-2">{Object.keys(s.gates).map((g) => (
          <label key={g} className="flex items-center justify-between gap-2 text-sm">{GATE_TITLES[g] ?? g}
            <select className="input !w-40" value={s.gates[g]} onChange={(e) => set(["gates", g], e.target.value)} data-testid={`gate-mode-${g}`}>
              <option value="pause">pause for me</option><option value="auto">auto</option></select></label>))}</div>
        <p className="mt-2 text-xs text-ink-3">Auto picks the top-ranked topic and the top hook that fits in 3 s, and approves Phase A as written. The render-cost gate only auto-approves when the estimate is within your budget cap.</p>
      </Section>
      <Section title="Render">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="text-sm">Backend<select className="input" value={s.render.backend} onChange={(e) => set(["render", "backend"], e.target.value)}>
            <optgroup label="API (paid)"><option value="omni-fal">omni-fal (fal.ai, FAL_KEY)</option><option value="omni-gemini">omni-gemini (Gemini API, GEMINI_API_KEY)</option></optgroup>
            <optgroup label="Local ($0, your machine)"><option value="local-threejs">local-threejs (3D low-poly stickman, three.js)</option><option value="local-stickman">local-stickman (built-in animator, any PC)</option><option value="local-comfyui">local-comfyui (Wan/LTX on your GPU)</option></optgroup>
            <optgroup label="Test"><option value="mock">mock (free placeholders)</option></optgroup></select></label>
          <label className="text-sm">Resolution<select className="input" value={s.render.resolution} onChange={(e) => set(["render", "resolution"], e.target.value)}>
            {["360p", "720p", "1080p", "4k"].map((r) => <option key={r}>{r}</option>)}</select></label>
          <label className="text-sm">Continuity<select className="input" value={s.render.continuity} onChange={(e) => set(["render", "continuity"], e.target.value)}>
            <option value="first_frame">first frame from previous clip</option><option value="extend">extend previous (Gemini, ≤40 s)</option><option value="none">none</option></select></label>
          <label className="text-sm">Budget cap per video (USD)<input className="input" type="number" min={0} step={0.5} value={s.render.budget_cap_usd} onChange={(e) => set(["render", "budget_cap_usd"], Number(e.target.value))} data-testid="budget-cap" /></label>
          <label className="text-sm">Max retries per clip<input className="input" type="number" min={0} max={5} value={s.render.max_retries} onChange={(e) => set(["render", "max_retries"], Number(e.target.value))} /></label>
          <label className="text-sm">Speaking rate (wpm, beats.py)<input className="input" type="number" min={100} max={220} value={s.speaking_wpm} onChange={(e) => set(["speaking_wpm"], Number(e.target.value))} /></label>
        </div>
        {s.render.backend === "local-threejs" && (
          <div className="mt-3 grid gap-3 rounded-lg border border-line p-3 md:grid-cols-3" data-testid="threejs-settings">
            <label className="text-sm">Quality<select className="input" value={s.render.threejs.quality} onChange={(e) => set(["render", "threejs", "quality"], e.target.value)}>
              <option value="high">high (glow + depth of field)</option><option value="medium">medium (glow only)</option><option value="draft">draft (fastest)</option></select></label>
            <label className="text-sm">Frame rate<select className="input" value={s.render.threejs.fps} onChange={(e) => set(["render", "threejs", "fps"], Number(e.target.value))}>
              {[24, 30, 60].map((f) => <option key={f} value={f}>{f} fps</option>)}</select></label>
            <label className="text-sm">Browser<select className="input" value={s.render.threejs.browser_channel} onChange={(e) => set(["render", "threejs", "browser_channel"], e.target.value)}>
              <option value="">auto (Edge on Windows)</option><option value="msedge">Microsoft Edge</option><option value="chrome">Google Chrome</option></select></label>
            <p className="text-xs text-ink-3 md:col-span-3">Each clip's scene comes from <code>projects/&lt;slug&gt;/scenes/clip-NN.json</code> if you put one there (see <code>renderer/scenes/demo.json</code>), otherwise from the beat and voiceover by keyword. The voice is made first so the mouth follows it. Renders on your GPU through the browser: seconds per clip.</p>
          </div>
        )}
        {s.render.backend === "local-comfyui" && (
          <div className="mt-3 grid gap-3 rounded-lg border border-line p-3 md:grid-cols-3" data-testid="comfyui-settings">
            <label className="text-sm">ComfyUI URL<input className="input" value={s.render.comfyui.url} onChange={(e) => set(["render", "comfyui", "url"], e.target.value)} /></label>
            <label className="text-sm md:col-span-2">Text-to-video workflow (API-format JSON)<input className="input" value={s.render.comfyui.t2v_workflow} onChange={(e) => set(["render", "comfyui", "t2v_workflow"], e.target.value)} /></label>
            <label className="text-sm md:col-span-3">Image-to-video workflow (optional; used for first-frame continuity, needs {"{{IMAGE}}"})<input className="input" value={s.render.comfyui.i2v_workflow} placeholder="leave empty to generate every clip from text" onChange={(e) => set(["render", "comfyui", "i2v_workflow"], e.target.value)} /></label>
            <label className="text-sm">Generation size (long × short side)<span className="flex gap-1"><input className="input" type="number" step={16} value={s.render.comfyui.gen_long_side} onChange={(e) => set(["render", "comfyui", "gen_long_side"], Number(e.target.value))} /><input className="input" type="number" step={16} value={s.render.comfyui.gen_short_side} onChange={(e) => set(["render", "comfyui", "gen_short_side"], Number(e.target.value))} /></span></label>
            <label className="text-sm">Frames / fps<span className="flex gap-1"><input className="input" type="number" value={s.render.comfyui.frames} onChange={(e) => set(["render", "comfyui", "frames"], Number(e.target.value))} /><input className="input" type="number" value={s.render.comfyui.fps} onChange={(e) => set(["render", "comfyui", "fps"], Number(e.target.value))} /></span></label>
            <label className="text-sm">Timeout per clip (s)<input className="input" type="number" value={s.render.comfyui.timeout_s} onChange={(e) => set(["render", "comfyui", "timeout_s"], Number(e.target.value))} /></label>
            <label className="text-sm">Steps / CFG / shift<span className="flex gap-1">
              <input className="input" type="number" min={10} max={60} value={s.render.comfyui.steps} onChange={(e) => set(["render", "comfyui", "steps"], Number(e.target.value))} title="sampling steps: more = cleaner, slower" />
              <input className="input" type="number" min={1} max={12} step={0.5} value={s.render.comfyui.cfg} onChange={(e) => set(["render", "comfyui", "cfg"], Number(e.target.value))} title="CFG: how strictly it follows the prompt" />
              <input className="input" type="number" min={1} max={15} step={0.5} value={s.render.comfyui.shift} onChange={(e) => set(["render", "comfyui", "shift"], Number(e.target.value))} title="shift: 8 for Wan 1.3B" /></span></label>
            <label className="text-sm">Motion fill (5 s generated → 10 s clip)<select className="input" value={s.render.comfyui.fill} onChange={(e) => set(["render", "comfyui", "fill"], e.target.value)} data-testid="comfy-fill">
              <option value="smooth">smooth slow motion (interpolated, +~30 s CPU per clip)</option><option value="slow">plain slow motion (choppy, fastest)</option></select></label>
            <label className="text-sm md:col-span-3">Negative prompt (what the model should avoid)<textarea className="input min-h-[64px]" value={s.render.comfyui.negative} onChange={(e) => set(["render", "comfyui", "negative"], e.target.value)} /></label>
            <p className="text-xs text-ink-3 md:col-span-3">Wan 2.1 1.3B is trained at 832×480, 81 frames, 16 fps: keep those for the best image. Frames must be 4n+1 (81, 65, 49, 33); fewer frames = shorter, smoother-looking motion once stretched, and less VRAM. Out-of-memory errors show on the clip card. Image-to-video needs a model this card cannot hold (Wan I2V is 14B), so leave it empty: each clip starts from its prompt.</p>
          </div>
        )}
        <p className="mt-2 text-xs text-ink-3">1080p/4K on the Gemini API are upscaled and their price is not verified; the estimate refuses them until you add a rate to config/pricing.json.</p>
      </Section>
      <Section title="Writing model (research, scripts, direction)">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="text-sm">Provider<select className="input" value={s.agent.provider} onChange={(e) => set(["agent", "provider"], e.target.value)} data-testid="agent-provider">
            <option value="claude">Claude API (best quality)</option><option value="hybrid">Hybrid: Claude directs, local writes the rest</option><option value="local">Local LLM only ($0)</option></select></label>
          <label className="text-sm">Attempts per task (invalid answers are retried)<input className="input" type="number" min={1} max={6} value={s.agent.max_attempts} onChange={(e) => set(["agent", "max_attempts"], Number(e.target.value))} /></label>
        </div>
        {s.agent.provider !== "claude" && (
          <div className="mt-3 grid gap-3 rounded-lg border border-line p-3 md:grid-cols-3" data-testid="local-llm-settings">
            <label className="text-sm">Server URL (OpenAI-compatible)<input className="input" value={s.agent.local.base_url} onChange={(e) => set(["agent", "local", "base_url"], e.target.value)} /></label>
            <label className="text-sm">Model<input className="input" value={s.agent.local.model} onChange={(e) => set(["agent", "local", "model"], e.target.value)} /></label>
            <label className="text-sm">Temperature<input className="input" type="number" min={0} max={1.5} step={0.1} value={s.agent.local.temperature} onChange={(e) => set(["agent", "local", "temperature"], Number(e.target.value))} /></label>
            <label className="text-sm">Max output tokens<input className="input" type="number" value={s.agent.local.max_tokens} onChange={(e) => set(["agent", "local", "max_tokens"], Number(e.target.value))} /></label>
            <label className="text-sm">Timeout per call (s)<input className="input" type="number" value={s.agent.local.timeout_s} onChange={(e) => set(["agent", "local", "timeout_s"], Number(e.target.value))} /></label>
            <label className="text-sm">Context tokens (Ollama)<select className="input" value={s.agent.local.num_ctx} onChange={(e) => set(["agent", "local", "num_ctx"], Number(e.target.value))} data-testid="num-ctx">
              {[4096, 8192, 12288, 16384, 32768].map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!s.agent.local.think} onChange={(e) => set(["agent", "local", "think"], e.target.checked)} />
              Let the model think first (qwen3: better, about 2-3× slower)</label>
            <p className="text-xs text-ink-3 md:col-span-3">Ollama: <code>http://localhost:11434/v1</code>, model <code>qwen3:8b</code> (≈5 GB, fits 8 GB VRAM) or <code>qwen3:14b</code> (≈9 GB: part runs on the CPU, slower; needs 16 GB+ RAM). LM Studio: <code>http://localhost:1234/v1</code>. Local models are weaker than Claude at long direction prompts; hybrid keeps Claude for Phase A/B only.</p>
          </div>
        )}
      </Section>
      <Section title="Voice and captions (local)">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="text-sm">Voiceover for local video<select className="input" value={s.voice.tts} onChange={(e) => set(["voice", "tts"], e.target.value)} data-testid="tts-engine">
            <option value="auto">auto (Kokoro, then Piper)</option><option value="kokoro">Kokoro-82M</option><option value="piper">Piper</option><option value="none">none (silent clips)</option></select></label>
          <label className="text-sm">Kokoro voice (male / female)<span className="flex gap-1"><input className="input" value={s.voice.kokoro_voice_male} onChange={(e) => set(["voice", "kokoro_voice_male"], e.target.value)} /><input className="input" value={s.voice.kokoro_voice_female} onChange={(e) => set(["voice", "kokoro_voice_female"], e.target.value)} /></span></label>
          <label className="text-sm">Piper voice model (.onnx path)<input className="input" value={s.voice.piper_model} onChange={(e) => set(["voice", "piper_model"], e.target.value)} /></label>
          <label className="text-sm">Caption timing model (faster-whisper)<select className="input" value={s.captions.whisper_model} onChange={(e) => set(["captions", "whisper_model"], e.target.value)}>
            {["base.en", "small.en", "medium.en", "large-v3-turbo"].map((m) => <option key={m}>{m}</option>)}</select></label>
          <label className="text-sm">Whisper device<select className="input" value={s.captions.whisper_device} onChange={(e) => set(["captions", "whisper_device"], e.target.value)}>
            <option value="auto">auto (GPU if available)</option><option value="cuda">GPU (cuda)</option><option value="cpu">CPU</option></select></label>
          <label className="text-sm">Max voice speed-up to fit a clip<input className="input" type="number" min={1} max={1.6} step={0.05} value={s.voice.max_speedup} onChange={(e) => set(["voice", "max_speedup"], Number(e.target.value))} /></label>
        </div>
      </Section>
      <LocalServices />
      <Section title="Models (Claude Agent SDK)">
        <div className="grid gap-3 md:grid-cols-3">{Object.keys(s.models).map((k) => (
          <label key={k} className="text-sm">{k}<input className="input" value={s.models[k]} onChange={(e) => set(["models", k], e.target.value)} /></label>))}
          <label className="text-sm">Agent budget per stage (USD)<input className="input" type="number" min={0} step={0.5} value={s.agent_budget_per_stage_usd} onChange={(e) => set(["agent_budget_per_stage_usd"], Number(e.target.value))} /></label>
        </div>
      </Section>
      <Section title="Topic score weights">
        <div className="grid gap-3 md:grid-cols-4">{Object.keys(s.topic_weights).map((k) => (
          <label key={k} className="text-sm">{k.replace("_", " ")}<input className="input" type="number" min={0} max={1} step={0.05} value={s.topic_weights[k]} onChange={(e) => set(["topic_weights", k], Number(e.target.value))} /></label>))}</div>
      </Section>
      <div className="flex items-center gap-3"><button className="btn-primary" onClick={save} data-testid="save-settings">Save settings</button>{msg && <span className="text-sm">✓ {msg}</span>}</div>
      {err && <ErrorBox>{err}</ErrorBox>}
    </div>
  );
}

function LocalServices() {
  const [st, setSt] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const check = async () => { setBusy(true); try { setSt(await api.get("/local/status")); } catch (e: any) { setSt({ error: e.message }); } finally { setBusy(false); } };
  useEffect(() => { check(); }, []);
  const Row = ({ ok, name, children, fix }: { ok: boolean | undefined; name: string; children?: React.ReactNode; fix?: React.ReactNode }) => (
    <li className="grid grid-cols-[20px_150px_1fr] items-start gap-2 text-sm">
      <span aria-hidden style={{ color: ok ? "var(--good)" : "var(--serious)" }}>{ok ? "✓" : "○"}</span><b>{name}</b>
      <span className="text-ink-2">{children}{!ok && fix && <span className="block text-xs text-ink-3">{fix}</span>}</span>
    </li>
  );
  return (
    <Section title="Local services" right={<button className="btn !py-0.5" onClick={check} disabled={busy} data-testid="check-local">{busy ? "Checking…" : "↻ Check"}</button>}>
      {!st ? <div className="muted text-sm">Checking…</div> : st.error ? <ErrorBox>{st.error}</ErrorBox> : (
        <ul className="grid gap-2" data-testid="local-status">
          <Row ok={st.gpu?.ok} name="GPU" fix="Install the NVIDIA driver; RTX 50-series needs PyTorch built for CUDA 12.8+ (cu128 wheels).">
            {st.gpu?.ok ? `${st.gpu.name} · ${st.gpu.vram_used_gb}/${st.gpu.vram_total_gb} GB used · driver ${st.gpu.driver}` : st.gpu?.error}</Row>
          <Row ok={st.llm?.ok && st.llm?.model_present} name="Local LLM" fix={st.llm?.ok ? <>Model missing: <code>ollama pull {st.llm.model}</code></> : <>Install Ollama, then <code>ollama pull {st.llm?.model}</code> (server at {st.llm?.url}).</>}>
            {st.llm?.ok ? `${st.llm.url} · ${st.llm.models.length} model(s)${st.llm.model_present ? ` · ${st.llm.model} ready` : ""}` : `not reachable at ${st.llm?.url}`}</Row>
          <Row ok={st.comfyui?.ok && !st.comfyui?.missing_models?.length} name="ComfyUI" fix="Only needed for the local-comfyui backend. Start ComfyUI (run_nvidia_gpu.bat) with the three Wan 2.1 1.3B files in its models folders: README → ComfyUI on Windows.">
            {st.comfyui?.ok ? `${st.comfyui.url} · ${st.comfyui.device ?? "device ?"} · ${st.comfyui.vram_free_gb} GB free` : `not reachable at ${st.comfyui?.url}`}
            {st.comfyui?.missing_models?.length > 0 && (
              <ul className="mt-1 grid gap-0.5 text-xs" data-testid="comfy-missing">{st.comfyui.missing_models.map((m: any) => (
                <li key={m.file}><span style={{ color: "var(--critical)" }}>✕ missing</span> <code>{m.file}</code> for {m.loader}
                  {m.available.length > 0 && <span className="text-ink-3"> (has: {m.available.join(", ")})</span>}</li>))}</ul>
            )}</Row>
          <Row ok={st.threejs?.ok} name="three.js renderer" fix={<>{st.threejs?.fix} (README → three.js renderer)</>}>
            {st.threejs?.ok ? "ready (Node + renderer build + browser driver)" : `missing: ${[!st.threejs?.node && "Node.js", !st.threejs?.deps && "renderer packages", !st.threejs?.built && "renderer build"].filter(Boolean).join(", ")}`}</Row>
          <Row ok={st.stickman?.ok} name="Stickman animator" fix={st.stickman?.error}>{st.stickman?.ok ? "ready (Pillow + ffmpeg)" : ""}</Row>
          <Row ok={st.tts?.kokoro || st.tts?.piper} name="Voiceover (TTS)" fix={<><code>pip install kokoro soundfile</code> (best) or <code>pip install piper-tts</code> + a voice .onnx</>}>
            {[st.tts?.kokoro && "Kokoro", st.tts?.piper && "Piper"].filter(Boolean).join(", ") || "no engine installed: local clips will be silent"}</Row>
          <Row ok={st.whisper?.installed} name="Caption timing" fix={<><code>pip install faster-whisper</code> (word-accurate captions)</>}>
            {st.whisper?.installed ? `faster-whisper on ${st.whisper.device}` : "estimated timing"}</Row>
        </ul>
      )}
    </Section>
  );
}
