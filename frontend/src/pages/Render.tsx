import { useEffect, useState } from "react";
import { GatePanel } from "../components/GatePanel";
import { RunStageButton } from "../components/Pipeline";
import { Empty, ErrorBox, Note, Section, StatusChip, fmtUsd } from "../components/ui";
import { api, fileUrl, getFile } from "../lib/api";
import { useProject, useProjectFile } from "../lib/useProject";

export default function Render() {
  const { slug, snap, version } = useProject();
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
  }, [slug, version, n]);
  const gate = snap?.gates.find((g) => g.name === "render_cost");
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
      <Section title="Clips">
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-3" data-testid="clip-grid">
          {Array.from({ length: n }, (_, k) => {
            const c = clips[k];
            const name = `clips/clip-${String(k + 1).padStart(2, "0")}.mp4`;
            return (
              <div key={k} className="card-2" data-testid={`clip-${k + 1}`}>
                <div className="mb-2 flex items-center justify-between text-xs">
                  <b>Clip {k + 1}</b>
                  <StatusChip status={c ? (c.status === "done" ? "succeeded" : c.status === "rendering" ? "running" : c.status) : "not_run"} small />
                </div>
                {c?.status === "done" ? (
                  <video className="w-full rounded-lg bg-black" style={{ aspectRatio: snap?.project.data.ratio === "9:16" ? "9 / 16" : "16 / 9", maxHeight: 360 }}
                    src={`${fileUrl(slug!, name)}?v=${c.prompt_hash}-${c.attempts}-${version}`}
                    poster={`${fileUrl(slug!, name.replace(".mp4", ".last.png"))}?v=${c.prompt_hash}-${c.attempts}-${version}`} controls preload="none" />
                ) : <Empty>{c?.error ?? "not rendered yet"}</Empty>}
                {c?.ratio_ok === false && <p className="mt-1 text-xs" style={{ color: "var(--serious)" }} data-testid={`ratio-warn-${k + 1}`}>⚠ came back {c.width}×{c.height}, not {snap?.project.data.ratio}. Stitch crops it to fill the frame; regenerate it for proper framing.</p>}
                {c && <p className="mt-1 text-[11px] text-ink-3">poster = last frame (the next clip starts from it) · {c.backend} · {fmtUsd(c.cost_usd)} · {c.attempts ?? 0} attempt(s) · {c.continuity}{c.meta?.placeholder ? " · placeholder" : ""}</p>}
                <button className="btn mt-2 w-full justify-center" disabled={snap?.pipeline?.status === "running"} data-testid={`regen-${k + 1}`}
                  onClick={async () => { setErr(null); try { await api.post(`/projects/${slug}/clips/${k + 1}/regenerate`); } catch (e: any) { setErr(e.message); } }}>↻ Regenerate this clip only</button>
              </div>
            );
          })}
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
