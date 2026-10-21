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
        {!s.dry_run && <div className="mt-2"><Note tone="warn">Live mode: stages call Claude (your ANTHROPIC_API_KEY or Claude login), the YouTube Data API, and the render backend. Paid renders still stop at the cost gate and the budget cap.</Note></div>}
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
            <option value="mock">mock (free placeholders)</option><option value="omni-fal">omni-fal (fal.ai, FAL_KEY)</option><option value="omni-gemini">omni-gemini (Gemini API, GEMINI_API_KEY)</option></select></label>
          <label className="text-sm">Resolution<select className="input" value={s.render.resolution} onChange={(e) => set(["render", "resolution"], e.target.value)}>
            {["360p", "720p", "1080p", "4k"].map((r) => <option key={r}>{r}</option>)}</select></label>
          <label className="text-sm">Continuity<select className="input" value={s.render.continuity} onChange={(e) => set(["render", "continuity"], e.target.value)}>
            <option value="first_frame">first frame from previous clip</option><option value="extend">extend previous (Gemini, ≤40 s)</option><option value="none">none</option></select></label>
          <label className="text-sm">Budget cap per video (USD)<input className="input" type="number" min={0} step={0.5} value={s.render.budget_cap_usd} onChange={(e) => set(["render", "budget_cap_usd"], Number(e.target.value))} data-testid="budget-cap" /></label>
          <label className="text-sm">Max retries per clip<input className="input" type="number" min={0} max={5} value={s.render.max_retries} onChange={(e) => set(["render", "max_retries"], Number(e.target.value))} /></label>
          <label className="text-sm">Speaking rate (wpm, beats.py)<input className="input" type="number" min={100} max={220} value={s.speaking_wpm} onChange={(e) => set(["speaking_wpm"], Number(e.target.value))} /></label>
        </div>
        <p className="mt-2 text-xs text-ink-3">1080p/4K on the Gemini API are upscaled and their price is not verified; the estimate refuses them until you add a rate to config/pricing.json.</p>
      </Section>
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
