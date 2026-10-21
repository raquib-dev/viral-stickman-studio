import { RunStageButton } from "../components/Pipeline";
import { CopyBlock, CopyButton, Empty, FixtureBadge, Note, Section } from "../components/ui";
import { useProjectFile } from "../lib/useProject";

export default function Package() {
  const [p] = useProjectFile<any>("package/package.json");
  const [blocks] = useProjectFile<string>("package/copy-blocks.md");
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
          </Section>
          <div className="grid gap-4 lg:grid-cols-2">
            <CopyBlock title="YouTube description (yt-seo, humanized)" text={p.description + (p.chapter_lines.length ? "\n\n" + p.chapter_lines.join("\n") : "")} />
            <CopyBlock title={`Instagram caption (ig-caption: ${p.ig_caption_lint.verdict})`} text={p.ig_caption} />
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
          {blocks && <CopyBlock title="All copy blocks (package/copy-blocks.md)" text={blocks} />}
        </>
      )}
    </div>
  );
}
