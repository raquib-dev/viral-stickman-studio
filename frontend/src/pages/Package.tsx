import { useState } from "react";
import { RunStageButton } from "../components/Pipeline";
import { CopyBlock, CopyButton, Empty, FixtureBadge, Note, Section } from "../components/ui";
import { api } from "../lib/api";
import { useProject, useProjectFile } from "../lib/useProject";

/** One copy block with its own Regenerate: a fresh version of just this piece (an optional note steers it). */
function RegenBlock({ title, text, part, children }: { title: string; text: string; part: string; children?: React.ReactNode }) {
  const { slug, snap } = useProject();
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const row = snap?.stages.find((s) => s.stage === "package_part");
  const busy = ["running", "queued"].includes(row?.status ?? "") || snap?.pipeline?.status === "running";
  const regen = async () => {
    setMsg(null);
    try { await api.post(`/projects/${slug}/stages/package_part/run`, { params: { part, note } }); setMsg("Writing a new one… (see Activity)"); }
    catch (e: any) { setMsg(e.message); }
  };
  return (
    <div className="card-2" data-testid={`block-${part}`}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="h2">{title}</span><CopyButton text={text} />
      </div>
      <pre className="code max-h-72 overflow-auto whitespace-pre-wrap">{text || "—"}</pre>
      {children}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input className="input flex-1 text-sm" placeholder="Optional: what to change (funnier, shorter, more for beginners…)" value={note}
          onChange={(e) => setNote(e.target.value)} data-testid={`note-${part}`} />
        <button className="btn" disabled={busy} onClick={regen} data-testid={`regen-${part}`}>↻ Regenerate</button>
      </div>
      {msg && <p className="mt-1 text-xs text-ink-3">{msg}</p>}
    </div>
  );
}

export default function Package() {
  const [p] = useProjectFile<any>("package/package.json");
  const [blocks] = useProjectFile<string>("package/copy-blocks.md");
  const best = p?.best ?? {};
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="h1">8 · Package</h1><RunStageButton stage="package" />
      </div>
      <Note>Nothing is posted anywhere. Copy these blocks and publish by hand.</Note>
      {!p ? <Empty>Not packaged yet.</Empty> : (
        <>
          <Section title="Title + thumbnail pairing (yt-package/title.py)" right={p._fixture ? <FixtureBadge /> : undefined}>
            <table className="table" data-testid="title-table"><thead><tr><th>Score</th><th>Title</th><th>Thumbnail text</th><th>Issues</th><th /></tr></thead>
              <tbody>{p.titles.map((t: any, i: number) => (
                <tr key={i}><td className="tabular-nums font-semibold">{t.score}</td><td>{t.title}</td><td>{t.thumb}</td>
                  <td className="text-xs text-ink-2">{t.issues.map((x: any) => `${x[0]}: ${x[1]}`).join(" · ") || "—"}</td>
                  <td><CopyButton text={t.title} /></td></tr>))}</tbody></table>
            <p className="mt-2 text-sm"><b>Thumbnail brief:</b> {p.thumbnail_brief}</p>
            {p.seconds != null && <p className="mt-1 text-xs text-ink-3">Video: {p.seconds} s, {p.ratio}{p.seconds < 60 ? " (a short: no timestamps)" : ""}</p>}
          </Section>
          <div className="grid gap-4 lg:grid-cols-2">
            <CopyBlock title="YouTube title" text={best.title ?? ""} />
            <CopyBlock title="Thumbnail / cover text" text={best.thumb ?? ""} />
            <RegenBlock title="YouTube description" part="description"
              text={p.description + (p.chapter_lines.length ? "\n\n" + p.chapter_lines.join("\n") : "")}>
              {p.description_checks?.length > 0 && <ul className="mt-2 list-disc pl-5 text-xs" style={{ color: "var(--warning, #b7791f)" }}>
                {p.description_checks.map((c: string) => <li key={c}>{c}</li>)}</ul>}
            </RegenBlock>
            <RegenBlock title="Pinned comment (post right after publishing, then pin it)" part="pinned_comment" text={p.pinned_comment ?? ""} />
            <RegenBlock title={`Cover image prompt (${p.ratio === "9:16" ? "9:16, 1080×1920" : "16:9, 1280×720"})`} part="cover_prompt" text={p.cover_prompt ?? ""} />
            <RegenBlock title={`Instagram caption (ig-caption: ${p.ig_caption_lint.verdict})`} part="ig_caption" text={p.ig_caption} />
            <CopyBlock title="Tags" text={p.tags.join(", ")} />
            <div className="card-2"><div className="h2 mb-2">Search queries this should win</div><ul className="list-disc pl-5 text-sm">{p.queries.map((q: string) => <li key={q}>{q}</li>)}</ul>
              <div className="h2 mb-1 mt-3">Chapters</div>
              <p className="text-sm text-ink-2">{p.chapters.valid ? p.chapter_lines.join(" · ") : p.chapters.note ?? "invalid (YouTube needs 00:00, ≥3 entries, ≥10 s each)"}</p></div>
          </div>
          <Section title="Caption lint (ig-caption/caption.py)">
            <table className="table"><tbody>{p.ig_caption_lint.checks.map((c: any) => <tr key={c.check}><td className="w-20 font-semibold">{c.status}</td><td className="w-40">{c.check}</td><td className="text-ink-2">{c.detail}</td></tr>)}</tbody></table>
            <p className="mt-2 text-xs text-ink-3">detect.py human score: description {p.description_detect.human_score} ({p.description_detect.verdict}), caption {p.ig_caption_detect.human_score} ({p.ig_caption_detect.verdict}). These are local heuristics, not GPTZero or similar.</p>
          </Section>
          {p.cutdowns?.length > 0 && <Section title="Cut-down suggestions (yt-shorts / ig-repurpose)">
            <ul className="text-sm">{p.cutdowns.map((c: any, i: number) => <li key={i}>{c.start}-{c.end}s · “{c.first_line}” · on screen: {c.on_screen}</li>)}</ul></Section>}
          <Section title="Before you publish">
            {p.claims_to_source.length > 0 && <><div className="label">Claims to verify</div><ul className="mb-3 list-disc pl-5 text-sm">{p.claims_to_source.map((c: string) => <li key={c}>{c}</li>)}</ul></>}
            <div className="label">Platform policy notes</div><ul className="list-disc pl-5 text-sm">{p.policy_notes.map((c: string) => <li key={c}>{c}</li>)}</ul>
          </Section>
          {blocks && <details className="card-2"><summary className="cursor-pointer text-sm font-semibold">All copy blocks in one file (package/copy-blocks.md)</summary>
            <div className="mt-2"><CopyBlock title="copy-blocks.md" text={blocks} /></div></details>}
        </>
      )}
    </div>
  );
}
