import { useEffect, useMemo, useState } from "react";
import { RunStageButton } from "../components/Pipeline";
import { Empty, ErrorBox, FixtureBadge, Note, Section, SyntheticBadge } from "../components/ui";
import { api } from "../lib/api";
import { useProject, useProjectFile } from "../lib/useProject";

interface SwipeRow { id: number; platform: string; account: string; title: string; hook: string; url: string; views: number;
  baseline: number; multiple: number; formula: string; synthetic: boolean; duration: number | null }

export default function Discover() {
  const { slug, version } = useProject();
  const [disc] = useProjectFile<any>("research/discovery.json");
  const [rows, setRows] = useState<SwipeRow[]>([]);
  const [platform, setPlatform] = useState("all");
  const [minMult, setMinMult] = useState(1.5);
  const [q, setQ] = useState("");
  useEffect(() => { if (slug) api.get<SwipeRow[]>(`/projects/${slug}/swipe`).then(setRows).catch(() => {}); }, [slug, version]);
  const shown = useMemo(() => rows.filter((r) => (platform === "all" || r.platform === platform) && (r.multiple ?? 0) >= minMult &&
    (!q || `${r.title} ${r.hook} ${r.account} ${r.formula}`.toLowerCase().includes(q.toLowerCase()))), [rows, platform, minMult, q]);
  const synthetic = rows.some((r) => r.synthetic);
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="h1">2 · Viral discovery</h1>
        <span className="flex items-center gap-2">{synthetic && <SyntheticBadge />}<RunStageButton stage="discover" /></span>
      </div>
      <Note>Ranked by <b>multiple over each channel's own median</b> (yt-viral/swipe.py, ig-viral/swipe.py), not raw views. Formula labels are a judgement about the words, not a claim about why a video worked.</Note>
      <Section title={`Swipe library (${shown.length} of ${rows.length})`} right={
        <div className="flex flex-wrap items-center gap-2">
          <select className="input !w-36" value={platform} onChange={(e) => setPlatform(e.target.value)} aria-label="Platform filter">
            <option value="all">all platforms</option><option value="youtube">YouTube</option><option value="instagram">Instagram</option></select>
          <label className="flex items-center gap-1 text-xs text-ink-2">min ×<input className="input !w-16" type="number" step={0.5} min={0} value={minMult} onChange={(e) => setMinMult(Number(e.target.value))} /></label>
          <input className="input !w-48" placeholder="search…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>}>
        {rows.length === 0 ? <Empty>No discovery yet. Run the pipeline, or paste rows below and run Discover.</Empty> : (
          <div className="max-h-[480px] overflow-auto">
            <table className="table" data-testid="outlier-table">
              <thead><tr><th>×</th><th>Platform</th><th>Account</th><th>Title / hook</th><th>Views</th><th>Baseline</th><th>Formula</th></tr></thead>
              <tbody>{shown.map((r) => (
                <tr key={r.id}>
                  <td className="font-semibold tabular-nums">{r.multiple?.toFixed(1)}×{r.multiple >= 3 ? " ★" : ""}</td>
                  <td>{r.platform}</td><td className="text-ink-2">{r.account}</td>
                  <td className="max-w-md">{r.url && r.url.startsWith("http") ? <a className="hover:underline" href={r.url} target="_blank" rel="noreferrer">{r.title || r.hook}</a> : (r.title || r.hook)}</td>
                  <td className="tabular-nums">{r.views?.toLocaleString()}</td><td className="tabular-nums text-ink-2">{r.baseline?.toLocaleString()}</td>
                  <td className="text-ink-2">{r.formula}</td>
                </tr>))}</tbody>
            </table>
            <p className="mt-2 text-[11px] text-ink-3">★ = 3× or more over the account's own median (ig-viral's signal threshold).</p>
          </div>
        )}
      </Section>
      {disc && (
        <div className="grid gap-4 lg:grid-cols-2">
          {(["youtube", "instagram"] as const).map((p) => disc.reads?.[p] && (
            <Section key={p} title={`What the ${p === "youtube" ? "yt-viral" : "ig-viral"} skill reads from it`} right={disc.reads[p]._fixture ? <FixtureBadge /> : undefined}>
              <p className="text-sm"><b>Shared structure:</b> {disc.reads[p].shared_structure}</p>
              <p className="mt-1 text-sm"><b>Makeable this week:</b> {disc.reads[p].makeable}</p>
              <p className="mt-1 text-sm text-ink-2"><b>Confidence:</b> {disc.reads[p].confidence}</p>
            </Section>))}
        </div>
      )}
      {disc && (
        <Section title={`Transcripts pulled (${disc.transcripts?.length ?? 0})`}>
          {disc.youtube?.skipped_thin_channels?.length > 0 && <Note tone="warn">Skipped channels with under 4 videos (a median needs at least 4): {disc.youtube.skipped_thin_channels.map((c: any) => c[0]).join(", ")}</Note>}
          <ul className="mt-2 text-sm">{(disc.transcripts ?? []).map((t: any) => <li key={t.id}>{t.id} · {t.multiple?.toFixed(1)}× · {t.title}</li>)}</ul>
        </Section>
      )}
      <PasteForms />
    </div>
  );
}

function PasteForms() {
  const { slug } = useProject();
  const [ig, setIg] = useState("");
  const [yt, setYt] = useState("");
  const [tr, setTr] = useState({ url: "", title: "", text: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const parse = (txt: string, cols: string[]) => txt.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
    const cells = l.split(/\t|\s*\|\s*/);
    return Object.fromEntries(cols.map((c, i) => [c, ["views", "followers", "median", "length"].includes(c) ? Number(String(cells[i] ?? "").replace(/[^\d.]/g, "")) || null : (cells[i] ?? "").trim()]));
  });
  const run = async (fn: () => Promise<any>) => { setErr(null); setMsg(null); try { setMsg(JSON.stringify(await fn())); } catch (e: any) { setErr(e.message); } };
  return (
    <Section title="Add evidence by hand (public listings only; never a login)">
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <label className="label">Instagram reels: account | followers | median | views | hook | url | length s | cta</label>
          <textarea className="input h-28 font-mono text-xs" value={ig} onChange={(e) => setIg(e.target.value)} placeholder="@account | 48000 | 11000 | 412000 | nobody tells you … | https://instagram.com/reel/… | 28 | comment GUIDE" />
          <button className="btn mt-2" onClick={() => run(() => api.post(`/projects/${slug}/ig-rows`, { rows: parse(ig, ["account", "followers", "median", "views", "hook", "url", "length", "cta"]) }))}>Add reels</button>
          <p className="mt-1 text-[11px] text-ink-3">ig-viral's method: eyeball the median of an account's last 12 reels from its public profile. Without a median the ranking falls back to followers (weaker).</p>
        </div>
        <div>
          <label className="label">YouTube videos without an API key: channel | title | views | url | duration s</label>
          <textarea className="input h-28 font-mono text-xs" value={yt} onChange={(e) => setYt(e.target.value)} placeholder="Some Channel | Video title | 412000 | https://youtu.be/… | 58" />
          <button className="btn mt-2" onClick={() => run(() => api.post(`/projects/${slug}/yt-rows`, { rows: parse(yt, ["channel", "title", "views", "url", "duration"]) }))}>Add videos</button>
          <p className="mt-1 text-[11px] text-ink-3">Add at least 4 videos per channel so swipe.py can compute that channel's median.</p>
        </div>
        <div className="lg:col-span-2">
          <label className="label">Paste a transcript (SRT/VTT or plain timed text) for a video in the table</label>
          <div className="grid gap-2 md:grid-cols-2">
            <input className="input" placeholder="video URL (must match the row)" value={tr.url} onChange={(e) => setTr({ ...tr, url: e.target.value })} />
            <input className="input" placeholder="title (optional)" value={tr.title} onChange={(e) => setTr({ ...tr, title: e.target.value })} />
          </div>
          <textarea className="input mt-2 h-28 font-mono text-xs" value={tr.text} onChange={(e) => setTr({ ...tr, text: e.target.value })} />
          <button className="btn mt-2" onClick={() => run(() => api.post(`/projects/${slug}/transcripts`, tr))}>Save transcript</button>
        </div>
      </div>
      {msg && <p className="mt-2 text-xs text-ink-2">✓ {msg} · re-run Discover to rank them.</p>}
      {err && <ErrorBox>{err}</ErrorBox>}
    </Section>
  );
}
