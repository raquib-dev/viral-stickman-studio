import { useEffect, useState } from "react";
import { BeatTimeline, Heatmap } from "../components/charts";
import { RunStageButton } from "../components/Pipeline";
import { Empty, Note, Section, SyntheticBadge } from "../components/ui";
import { api } from "../lib/api";
import { useProject, useProjectFile } from "../lib/useProject";

export default function Patterns() {
  const { slug, version } = useProject();
  const [profile] = useProjectFile<any>("research/niche-profile.json");
  const [files, setFiles] = useState<string[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  useEffect(() => {
    if (!slug) return;
    api.get<{ name: string }[]>(`/projects/${slug}/ls/research/patterns`).then((r) => {
      const names = r.map((x) => x.name).filter((n) => n.endsWith(".json"));
      setFiles(names); setSel((s) => s ?? names[0] ?? null);
    }).catch(() => {});
  }, [slug, version]);
  const [video] = useProjectFile<any>(sel ? `research/patterns/${sel}` : null);
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="h1">3 · Why it worked</h1>
        <span className="flex items-center gap-2">{profile?.synthetic && <SyntheticBadge />}<RunStageButton stage="patterns" /></span>
      </div>
      <Note>Every beat is labelled against <code>virality-blueprint.json</code>. Labels are judgements about the words in a transcript, not proof that a technique caused a video's performance. "proxy" labels (pattern interrupts) come from pauses and openers, because cuts are not visible in words.</Note>
      {!profile ? <Empty>No profile yet. Run Discover, then Patterns.</Empty> : (
        <>
          <Section title={`Niche pattern profile (${profile.n_videos} outlier videos, weighted by ${profile.weighting})`}>
            <ul className="mb-4 list-disc pl-5 text-sm" data-testid="profile-summary">{profile.summary.map((s: string) => <li key={s}>{s}</li>)}</ul>
            <Heatmap rows={profile.heatmap.rows} binPct={profile.heatmap.bin_pct} />
            {profile.hook_formulas && (
              <div className="mt-4 grid gap-4 md:grid-cols-2 text-sm">
                {(["yt", "ig"] as const).map((k) => (
                  <div key={k}><div className="label">Hook formulas ({k === "yt" ? "yt-script, 21" : "ig-reel, 26"})</div>
                    <ul>{Object.entries(profile.hook_formulas[k] as Record<string, number>).sort((a, b) => b[1] - a[1]).map(([n, c]) => <li key={n}>{c}× {n}</li>)}</ul></div>
                ))}
              </div>
            )}
          </Section>
          <Section title="Per-video beat timeline" right={
            <select className="input !w-72" value={sel ?? ""} onChange={(e) => setSel(e.target.value)} aria-label="Video">
              {files.map((f) => <option key={f} value={f}>{f.replace(".json", "")}</option>)}
            </select>}>
            {video ? (
              <>
                <p className="mb-2 text-sm"><b>{video.title}</b> · {video.multiple?.toFixed(1)}× · {video.duration.toFixed(0)}s {video.synthetic && <SyntheticBadge />}</p>
                <div className="mb-3 grid gap-3 text-sm md:grid-cols-2">
                  <div className="card-2"><div className="label">Hook (first 3 s)</div>“{video.hook.text}”
                    <div className="mt-1 text-xs text-ink-2">yt hookscore {video.hook.yt?.verdict} · {video.hook.formula_yt}<br />ig hookscore {video.hook.ig?.score} {video.hook.ig?.verdict} · {video.hook.formula_ig}</div></div>
                </div>
                <BeatTimeline marks={video.labels} duration={video.duration} />
              </>
            ) : <Empty>Pick a video.</Empty>}
          </Section>
        </>
      )}
    </div>
  );
}
