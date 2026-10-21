import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useProject } from "../lib/useProject";
import { ErrorBox, ProgressBar, StatusChip, fmtUsd } from "./ui";

export const STAGE_PAGE: Record<string, string> = {
  niche: "niche", discover: "discover", patterns: "patterns", topics: "topics", hooks: "studio", script: "studio",
  direction_a: "studio", direction_b: "studio", render: "render", stitch: "render", package: "package", learn: "learn",
};
export const GATE_PAGE: Record<string, string> = { topic: "topics", hook: "studio", phase_a: "studio", render_cost: "render" };
const SHORT: Record<string, string> = {
  niche: "Niche", discover: "Discover", patterns: "Patterns", topics: "Topics", hooks: "Hooks", script: "Script",
  direction_a: "Phase A", direction_b: "Phase B", render: "Render", stitch: "Stitch", package: "Package", learn: "Learn",
};

/** The always-visible pipeline strip: one cell per stage with live status and progress, plus Run / Stop. */
export function PipelineBar() {
  const { slug, snap, meta } = useProject();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!slug || !snap) return null;
  const pl = snap.pipeline;
  const running = pl?.status === "running";
  const call = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr(null);
    try { await fn(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const stages = snap.stages.filter((s) => s.stage !== "learn");
  return (
    <div className="border-b border-line bg-surface px-4 py-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        {running ? (
          <button className="btn-danger" disabled={busy} onClick={() => call(() => api.post(`/projects/${slug}/pipeline/stop`))}>■ Stop pipeline</button>
        ) : (
          <>
            <button className="btn-primary" disabled={busy} data-testid="run-pipeline"
              onClick={() => call(() => api.post(`/projects/${slug}/pipeline/start`, {}))}>▶ Run pipeline</button>
            <button className="btn" disabled={busy} title="Re-run every stage from the start"
              onClick={() => call(() => api.post(`/projects/${slug}/pipeline/start`, { from_stage: "niche" }))}>↺ Run all from start</button>
          </>
        )}
        <span className="text-sm text-ink-2" data-testid="pipeline-status">
          <StatusChip status={pl?.status ?? "idle"} /> {pl?.message}
        </span>
        <span className="ml-auto text-xs text-ink-3">spent {fmtUsd(snap.spend_usd)} (render {fmtUsd(snap.render_spend_usd)})</span>
      </div>
      {err && <ErrorBox>{err}</ErrorBox>}
      <ol className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(${stages.length}, minmax(0, 1fr))` }}>
        {stages.map((s, i) => {
          const active = pl?.current_stage === s.stage && (running || pl?.status === "waiting_gate");
          return (
            <li key={s.stage}>
              <Link to={`/p/${slug}/${STAGE_PAGE[s.stage]}`} title={meta?.stages[s.stage]?.description ?? s.stage}
                className={`block rounded-lg border px-2 py-1.5 hover:bg-surface-2 ${active ? "border-accent" : "border-line"}`}
                data-testid={`stage-${s.stage}`} data-status={s.status}>
                <div className="flex items-center justify-between gap-1">
                  <span className="truncate text-xs font-semibold text-ink">{i + 1}. {SHORT[s.stage]}</span>
                </div>
                <div className="mt-1"><StatusChip status={active && pl?.status === "waiting_gate" ? "waiting_gate" : s.status} small /></div>
                <div className="mt-1.5"><ProgressBar value={s.status === "succeeded" ? 1 : s.progress ?? 0} label={s.message ?? ""} /></div>
              </Link>
            </li>
          );
        })}
      </ol>
      <GateBanner />
    </div>
  );
}

function GateBanner() {
  const { slug, snap, meta } = useProject();
  if (!snap || !slug) return null;
  const pending = snap.gates.filter((g) => g.status === "pending");
  if (!pending.length) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-sm" style={{ borderColor: "var(--serious)" }} data-testid="gate-banner">
      <span aria-hidden style={{ color: "var(--serious)" }}>⏸</span>
      <span className="font-semibold">Waiting for you:</span>
      {pending.map((g) => (
        <Link key={g.name} className="btn !py-0.5" to={`/p/${slug}/${GATE_PAGE[g.name]}#gate-${g.name}`}>
          {meta?.gates[g.name] ?? g.name} →
        </Link>
      ))}
    </div>
  );
}

/** Re-run a single stage (each stage is an independent job). */
export function RunStageButton({ stage, label, params, primary }: { stage: string; label?: string; params?: object; primary?: boolean }) {
  const { slug, snap } = useProject();
  const [err, setErr] = useState<string | null>(null);
  const row = snap?.stages.find((s) => s.stage === stage);
  const running = row?.status === "running" || row?.status === "queued" || snap?.pipeline?.status === "running";
  return (
    <span className="inline-flex items-center gap-2">
      <button className={primary ? "btn-primary" : "btn"} disabled={running}
        onClick={async () => { setErr(null); try { await api.post(`/projects/${slug}/stages/${stage}/run`, { params: params ?? {} }); } catch (e: any) { setErr(e.message); } }}>
        ↻ {label ?? `Run ${SHORT[stage]}`}
      </button>
      {row && <StatusChip status={row.status} small />}
      {err && <span className="text-xs" style={{ color: "var(--critical)" }}>{err}</span>}
    </span>
  );
}
