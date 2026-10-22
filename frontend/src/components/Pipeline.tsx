import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useNow, useProject } from "../lib/useProject";
import { ErrorBox, ProgressBar, StatusChip, fmtDur, fmtUsd } from "./ui";

export const STAGE_PAGE: Record<string, string> = {
  niche: "niche", news: "topics", discover: "discover", patterns: "patterns", topics: "topics", hooks: "studio", script: "studio",
  direction_a: "studio", direction_b: "studio", scene_plan: "render", render: "render", stitch: "render", package: "package", learn: "learn",
};
export const GATE_PAGE: Record<string, string> = { topic: "topics", hook: "studio", phase_a: "studio", render_cost: "render" };
const SHORT: Record<string, string> = {
  niche: "Niche", news: "AI news", discover: "Discover", patterns: "Patterns", topics: "Topics", hooks: "Hooks", script: "Script",
  direction_a: "Phase A", direction_b: "Phase B", scene_plan: "3D plan", render: "Render", stitch: "Stitch", package: "Package", learn: "Learn",
};

/** The always-visible pipeline strip: one cell per stage with live status and progress, plus Run / Stop. */
export function PipelineBar() {
  const { slug, snap, meta } = useProject();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const now = useNow();
  if (!slug || !snap) return null;
  const pl = snap.pipeline;
  const stuck = pl && ["failed", "stopped", "cancelled", "interrupted", "rejected"].includes(pl.status) ? pl.current_stage : null;
  const failedRow = snap.stages.find((s) => s.stage === stuck);
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
              title={stuck ? `Continue from ${SHORT[stuck]}: finished stages are kept` : "Run every stage that still needs to run"}
              onClick={() => call(() => api.post(`/projects/${slug}/pipeline/start`, {}))}>{stuck ? `▶ Resume from ${SHORT[stuck]}` : "▶ Run pipeline"}</button>
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
      {failedRow?.error && (
        <div className="mb-2 rounded-lg border px-3 py-2 text-xs" style={{ borderColor: "var(--critical)" }} data-testid="pipeline-error">
          <b style={{ color: "var(--critical)" }}>✕ {SHORT[failedRow.stage]} failed</b>
          {failedRow.runs > 1 && <span className="text-ink-3"> (run {failedRow.runs} times)</span>}: <span className="text-ink-2">{failedRow.error}</span>
          <Link className="ml-2 underline" to={`/p/${slug}/activity`}>details & logs →</Link>
        </div>
      )}
      <ol className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(${stages.length}, minmax(0, 1fr))` }}>
        {stages.map((s, i) => {
          const active = pl?.current_stage === s.stage && (running || pl?.status === "waiting_gate");
          const live = s.status === "running" && s.started_at;
          const took = s.started_at && s.finished_at ? s.finished_at - s.started_at : null;
          const tip = [meta?.stages[s.stage]?.description ?? s.stage, s.runs ? `runs: ${s.runs}` : "", s.error ? `last error: ${s.error}` : ""]
            .filter(Boolean).join("\n");
          return (
            <li key={s.stage}>
              <Link to={`/p/${slug}/${STAGE_PAGE[s.stage]}`} title={tip}
                className={`block rounded-lg border px-2 py-1.5 hover:bg-surface-2 ${active ? "border-accent" : "border-line"}`}
                data-testid={`stage-${s.stage}`} data-status={s.status}>
                <div className="flex items-center justify-between gap-1">
                  <span className="truncate text-xs font-semibold text-ink">{i + 1}. {SHORT[s.stage]}</span>
                  {s.runs > 1 && <span className="text-[10px] text-ink-3" title="times this stage has run">×{s.runs}</span>}
                </div>
                <div className="mt-1"><StatusChip status={active && pl?.status === "waiting_gate" ? "waiting_gate" : s.status} small /></div>
                <div className="mt-1.5"><ProgressBar value={s.status === "succeeded" ? 1 : s.progress ?? 0} label={s.message ?? ""} /></div>
                <div className="mt-1 truncate text-[10px] text-ink-3" title={s.message ?? ""}>
                  {live ? `${fmtDur(now - (s.started_at as number))} · ${s.message ?? ""}` : took != null ? `took ${fmtDur(took)}${s.cost_usd ? ` · ${fmtUsd(s.cost_usd)}` : ""}` : "\u00a0"}
                </div>
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
