import { useEffect, useState } from "react";
import { GatePanel } from "../components/GatePanel";
import { RunStageButton } from "../components/Pipeline";
import { Empty, ErrorBox, Note, Section, StatusChip, fmtDur, fmtUsd } from "../components/ui";
import { api, fileUrl, getFile } from "../lib/api";
import { useNow, useProject, useProjectFile } from "../lib/useProject";

export default function Render() {
  const { slug, snap, version, clipTick } = useProject();
  const [est] = useProjectFile<any>("clips/estimate.json");
  const [loud] = useProjectFile<any>("final/loudness.json");
  const [settings, setSettings] = useState<any>(null);
  const [clips, setClips] = useState<any[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const n = Math.floor((snap?.project.data.duration ?? 60) / 10);
  useEffect(() => { api.get("/settings").then(setSettings).catch(() => {}); }, [version]);
  useEffect(() => {
    if (!slug) return;
    Promise.all(Array.from({ length: n }, (_, k) =>
      getFile<any>(slug, `clips/clip-${String(k + 1).padStart(2, "0")}.json`).catch(() => null)))
      .then(setClips);
  }, [slug, version, clipTick, n]);
  const gate = snap?.gates.find((g) => g.name === "render_cost");
  const row = snap?.stages.find((s) => s.stage === "render");
  const doneCount = clips.filter((c) => c?.status === "done").length;
  const attemptsUsed = clips.reduce((a, c) => a + (c?.history?.length ?? 0), 0);
  const failedAttempts = clips.reduce((a, c) => a + (c?.history?.filter((h: any) => !h.ok).length ?? 0), 0);
  const r = settings?.render;
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="h1">7 · Render</h1>
        <span className="flex gap-2"><RunStageButton stage="render" primary /><RunStageButton stage="stitch" /></span>
      </div>
      <Section title="Cost">
        <div className="grid gap-3 md:grid-cols-4" data-testid="cost-meter">
          <Stat label="Backend" value={settings?.dry_run ? "mock (dry run)" : r?.backend} />
          <Stat label="Resolution" value={r?.resolution} />
          <Stat label="Estimate (with retry allowance)" value={est ? `${fmtUsd(est.base_usd)} – ${fmtUsd(est.max_usd)}` : "—"} />
          <Stat label="Spent / budget cap" value={`${fmtUsd(snap?.render_spend_usd)} / ${fmtUsd(r?.budget_cap_usd)}`} />
        </div>
        {est && <p className="mt-2 text-xs text-ink-3">{est.clips?.length} clip(s) × {est.seconds_per_clip}s × {fmtUsd(est.rate_per_second)}/s. Rates live in config/pricing.json (sources: docs/research/platform-signals-2026.md). The cap is checked before every clip; rendering stops at the cap.</p>}
        <div className="mt-3"><GatePanel name="render_cost" title="Confirm the render cost">
          {gate?.payload?.data?.estimate && <p className="text-sm">Approve spending up to <b>{fmtUsd(gate.payload.data.estimate.max_usd)}</b> on {gate.payload.data.clips.length} clip(s) with {gate.payload.data.estimate.backend} at {gate.payload.data.estimate.resolution}. Cap: {fmtUsd(gate.payload.data.cap)}.</p>}
        </GatePanel></div>
        {settings?.dry_run && <div className="mt-2"><Note>Dry run is on: the mock backend writes free placeholder clips. Turn it off in Settings for a real render.</Note></div>}
      </Section>
      {r?.backend === "local-threejs" && <ScenePlans n={n} />}
      <Section title="Clips" right={<span className="text-xs text-ink-3" data-testid="clip-summary">{doneCount}/{n} done · {attemptsUsed} attempt(s), {failedAttempts} failed{row?.status === "running" && row.message ? ` · ${row.message}` : ""}</span>}>
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-3" data-testid="clip-grid">
          {Array.from({ length: n }, (_, k) => (
            <ClipCard key={k} k={k} c={clips[k]} onErr={setErr} />
          ))}
        </div>
        {err && <ErrorBox>{err}</ErrorBox>}
      </Section>
      <Section title="Final video (stitched, captions burned in, loudness-normalised)">
        {loud ? (
          <div className="grid gap-4 md:grid-cols-[minmax(0,360px)_1fr]">
            <video className="w-full rounded-lg bg-black" style={{ aspectRatio: snap?.project.data.ratio === "9:16" ? "9 / 16" : "16 / 9" }}
              src={`${fileUrl(slug!, "final/final.mp4")}?v=${version}`} poster={`${fileUrl(slug!, "final/poster.png")}?v=${version}`}
              controls preload="none" data-testid="final-video" />
            <div className="text-sm">
              <dl className="grid grid-cols-[140px_1fr] gap-y-1">
                <dt className="text-ink-3">Duration</dt><dd>{loud.duration.toFixed(1)} s</dd>
                <dt className="text-ink-3">Size</dt><dd>{loud.width}×{loud.height}</dd>
                <dt className="text-ink-3">Loudness</dt><dd>{loud.after_i != null ? <>{loud.after_i.toFixed(1)} LUFS (target {loud.target_i}), true peak {loud.after_tp.toFixed(1)} dBTP</> : loud.skipped ?? "not measured"}</dd>
                <dt className="text-ink-3">Caption timing</dt><dd>{loud.caption_timing}</dd>
                <dt className="text-ink-3">Safe zone</dt><dd>{loud.safe_zone_violations.length ? loud.safe_zone_violations.join("; ") : "✓ all text inside the safe zone"}</dd>
              </dl>
              <div className="mt-3 flex gap-2"><a className="btn" href={fileUrl(slug!, "final/final.mp4")} download>⬇ final.mp4</a><a className="btn" href={fileUrl(slug!, "final/final.srt")} download>⬇ final.srt</a></div>
            </div>
          </div>
        ) : <Empty>Not stitched yet.</Empty>}
      </Section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: any }) {
  return <div className="card-2"><div className="label">{label}</div><div className="text-base font-semibold text-ink">{value ?? "—"}</div></div>;
}

function ClipCard({ k, c, onErr }: { k: number; c: any; onErr: (e: string | null) => void }) {
  const { slug, snap, version } = useProject();
  const now = useNow();
  const name = `clips/clip-${String(k + 1).padStart(2, "0")}.mp4`;
  const live = c && ["rendering", "retrying"].includes(c.status);
  const shown = c?.status === "done" ? c : c?.previous?.status === "done" ? c.previous : null;
  const ratio = snap?.project.data.ratio === "9:16" ? "9 / 16" : "16 / 9";
  const history: any[] = c?.history ?? [];
  return (
    <div className="card-2" data-testid={`clip-${k + 1}`} data-status={c?.status ?? "not_run"}>
      <div className="mb-2 flex items-center justify-between gap-2 text-xs">
        <b>Clip {k + 1}</b>
        <span className="flex items-center gap-1">
          {c?.max_attempts > 1 && c?.attempt > 0 && <span className="text-ink-3" title="attempt / max attempts">try {c.attempt}/{c.max_attempts}</span>}
          <StatusChip status={c ? (c.status === "done" ? "succeeded" : c.status) : "not_run"} small />
        </span>
      </div>
      {live && (
        <div className="mb-2 rounded-lg border border-line p-2 text-xs" data-testid={`clip-live-${k + 1}`}>
          <div className="flex justify-between"><span className="font-semibold">{c.status === "retrying" ? "Retrying" : "Rendering"} · {c.backend}</span>
            <span className="tabular-nums text-ink-3">{fmtDur(now - (c.attempt_started_at ?? now))}</span></div>
          <div className="mt-1 h-1 overflow-hidden rounded bg-surface-3"><div className="h-full w-1/3 animate-pulse rounded bg-accent" /></div>
          <div className="mt-1 line-clamp-2 text-ink-2" title={c.step}>{c.step}</div>
        </div>
      )}
      {c?.status === "queued" && <div className="mb-2 text-xs text-ink-3">Queued: waiting for the clips before it.</div>}
      {shown ? (
        <>
          <video className="w-full rounded-lg bg-black" style={{ aspectRatio: ratio, maxHeight: 360 }}
            src={`${fileUrl(slug!, name)}?v=${shown.prompt_hash}-${shown.attempts}-${version}`}
            poster={`${fileUrl(slug!, name.replace(".mp4", ".last.png"))}?v=${shown.prompt_hash}-${shown.attempts}-${version}`} controls preload="none" />
          {shown !== c && <p className="mt-1 text-[11px]" style={{ color: "var(--serious)" }}>{c?.status === "failed" ? "Regenerate failed: showing the last good render." : "Showing the previous render until the new one is done."}</p>}
        </>
      ) : !live && <Empty>{c?.status === "failed" ? "No video yet." : "not rendered yet"}</Empty>}
      {c?.status === "failed" && <div className="mt-2"><ErrorBox>{c.error ?? c.last_error}</ErrorBox></div>}
      {c?.ratio_ok === false && <p className="mt-1 text-xs" style={{ color: "var(--serious)" }} data-testid={`ratio-warn-${k + 1}`}>⚠ came back {c.width}×{c.height}, not {snap?.project.data.ratio}. Stitch crops it to fill the frame; regenerate it for proper framing.</p>}
      {shown && <p className="mt-1 text-[11px] text-ink-3">{shown.backend} · {fmtUsd(shown.cost_usd)} · {shown.attempts ?? 0} attempt(s){shown.render_seconds ? ` · ${fmtDur(shown.render_seconds)}` : ""} · {shown.continuity}
        {shown.meta?.voice !== undefined ? ` · ${shown.meta.voice ? "voice ✓" : "no voice"}` : ""}{shown.meta?.placeholder ? " · placeholder" : ""}</p>}
      {history.length > 0 && (
        <details className="mt-1 text-[11px]" open={c?.status === "failed" || history.some((h) => !h.ok) && live}>
          <summary className="cursor-pointer text-ink-3">Attempts ({history.length}{history.some((h) => !h.ok) ? `, ${history.filter((h) => !h.ok).length} failed` : ""})</summary>
          <ol className="mt-1 grid gap-1">{history.map((h, i) => (
            <li key={i} className="rounded border border-line px-1.5 py-1">
              <span style={{ color: h.ok ? "var(--good)" : "var(--critical)" }}>{h.ok ? "✓" : "✕"}</span> try {h.attempt} · {fmtDur(h.seconds)}
              {!h.ok && <div className="text-ink-2">{h.error}{h.retryable === false ? " (not retryable)" : ""}</div>}
            </li>))}</ol>
        </details>
      )}
      <button className="btn mt-2 w-full justify-center" data-testid={`regen-${k + 1}`}
        disabled={snap?.pipeline?.status === "running" || ["running", "queued"].includes(snap?.stages.find((s) => s.stage === "render")?.status ?? "")}
        title="Disabled while a render is running"
        onClick={async () => { onErr(null); try { await api.post(`/projects/${slug}/clips/${k + 1}/regenerate`); } catch (e: any) { onErr(e.message); } }}>
        {c?.status === "failed" ? "↻ Retry this clip" : "↻ Regenerate this clip only"}</button>
    </div>
  );
}

const MOOD_COLOR: Record<string, string> = {
  neutral: "#9aa3b2", money: "#58d68d", success: "#ffcf3d", danger: "#ff4d4d", calm: "#7cc4ff", tech: "#4de1ff",
  mystery: "#b48cff", nostalgia: "#e8b46b", sad: "#8aa2b8", love: "#ff7aa8", nature: "#7ccf6b",
};

/** Phase 3: the AI-written 3D scene plan for each clip, what was repaired, and re-plan per clip. */
function ScenePlans({ n }: { n: number }) {
  const { slug, snap } = useProject();
  const [index] = useProjectFile<Record<string, any>>("scenes/index.json");
  const [err, setErr] = useState<string | null>(null);
  const row = snap?.stages.find((s) => s.stage === "scene_plan");
  const busy = row?.status === "running" || row?.status === "queued" || snap?.pipeline?.status === "running";
  const replan = async (k: number) => {
    setErr(null);
    try { await api.post(`/projects/${slug}/stages/scene_plan/run`, { params: { only: [k], force: true } }); } catch (e: any) { setErr(e.message); }
  };
  return (
    <Section title="3D scene plans" right={<RunStageButton stage="scene_plan" label="Plan all scenes" />}>
      <p className="mb-3 text-xs text-ink-3">Your writing model stages each clip as data for the 3D renderer (mood, gestures, props, panels, camera), using only names the renderer knows. Each plan is checked: unknown names fall back to safe ones, things are kept in frame, and numbers the voiceover doesn't say are removed. If a plan still fails, the keyword plan is used. Edit <code>scenes/clip-NN.json</code> by hand and it is kept (delete <code>_planned_by</code> from it to protect it).</p>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="scene-plans">
        {Array.from({ length: n }, (_, k) => {
          const p = index?.[String(k + 1)];
          return (
            <div key={k} className="card-2 text-xs" data-testid={`scene-plan-${k + 1}`}>
              <div className="mb-1 flex items-center justify-between gap-2">
                <b className="text-sm">Clip {k + 1}</b>
                {p ? <span className="chip !py-0" title="who wrote this plan">{p.planned_by === "ai" ? "✦ AI plan" : p.planned_by}</span> : <span className="text-ink-3">not planned</span>}
              </div>
              {p && (
                <dl className="grid grid-cols-[64px_1fr] gap-x-2 gap-y-0.5">
                  <dt className="text-ink-3">Style</dt><dd>{p.style}</dd>
                  <dt className="text-ink-3">Colour</dt><dd className="flex flex-wrap items-center gap-1">{p.moods.map((m: string, i: number) => (
                    <span key={i} className="inline-flex items-center gap-1">{i > 0 && "→"}<span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: MOOD_COLOR[m] ?? "#999" }} />{m}</span>))}</dd>
                  <dt className="text-ink-3">Gestures</dt><dd>{p.gestures.join(", ") || "—"}</dd>
                  <dt className="text-ink-3">Props</dt><dd>{p.props.join(", ") || "—"}{p.actors > 1 ? " · 2 characters" : ""}{p.panels ? ` · ${p.panels} panel(s)` : ""}{p.badges.length ? ` · badge “${p.badges.join("”, “")}”` : ""}</dd>
                  <dt className="text-ink-3">Camera</dt><dd>{p.shots.join(" → ")}</dd>
                </dl>
              )}
              {p?.notes && <p className="mt-1 italic text-ink-2">“{p.notes}”</p>}
              {p?.fixes?.length > 0 && (
                <details className="mt-1"><summary className="cursor-pointer" style={{ color: "var(--serious)" }}>{p.fixes.length} repair(s)</summary>
                  <ul className="mt-1 list-disc pl-4 text-ink-2">{p.fixes.map((f: string, i: number) => <li key={i}>{f}</li>)}</ul></details>
              )}
              <div className="mt-2 flex gap-2">
                <button className="btn !py-0.5 text-xs" disabled={busy} onClick={() => replan(k + 1)} data-testid={`replan-${k + 1}`}>↻ Re-plan</button>
                {p && <a className="btn !py-0.5 text-xs" href={fileUrl(slug!, p.file)} target="_blank" rel="noreferrer">View plan</a>}
              </div>
            </div>
          );
        })}
      </div>
      {err && <ErrorBox>{err}</ErrorBox>}
    </Section>
  );
}
