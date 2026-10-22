import { useEffect, useState } from "react";
import { Bars } from "../components/charts";
import { GatePanel } from "../components/GatePanel";
import { RunStageButton } from "../components/Pipeline";
import { Empty, FixtureBadge, Note, Section, SyntheticBadge } from "../components/ui";
import { api } from "../lib/api";
import { useProject, useProjectFile } from "../lib/useProject";

const COMP: Record<string, string> = { outlier_evidence: "Outlier evidence", gap: "Gap (demand vs supply)", stickman_fit: "Stick-figure fit", niche_fit: "Niche fit", news: "Live news (real posts)" };
const KIND_COLOR: Record<string, string> = { problem: "var(--critical)", outage: "var(--serious)", update: "var(--good)", discussion: "var(--ink-3)" };

function Kind({ kind }: { kind: string }) {
  return <span className="chip !py-0 text-[10px]" style={{ color: KIND_COLOR[kind] ?? undefined }}>{kind}</span>;
}

/** Describe a topic in your own words: the live research searches for it, then the topic finder suggests topics about it. */
function ResearchBox() {
  const { slug, snap } = useProject();
  const [brief, setBrief] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const saved = snap?.project.data.topic_brief ?? "";
  useEffect(() => { setBrief(saved); }, [saved]);
  const busy = snap?.stages.some((s) => ["news", "topics"].includes(s.stage) && ["running", "queued"].includes(s.status)) || snap?.pipeline?.status === "running";
  const run = async () => {
    setMsg(null);
    try { await api.post(`/projects/${slug}/research`, { brief }); setMsg(brief.trim() ? "Searching live sources for it, then finding topics… (see Activity)" : "Researching what is happening across AI tools… (see Activity)"); }
    catch (e: any) { setMsg(e.message); }
  };
  return (
    <Section title="Research a topic (optional)">
      <div className="grid gap-2" data-testid="research-box">
        <textarea className="input min-h-[64px]" value={brief} onChange={(e) => setBrief(e.target.value)} data-testid="brief-input"
          placeholder="Describe what you want a video about, e.g. 'AI that says it fixed the bug but didn't', 'this week's Claude usage limits', 'Gemini vs ChatGPT for homework'. Empty = what is happening across AI tools right now." />
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn-primary" disabled={busy} onClick={run} data-testid="research-run">🔎 Research this</button>
          <span className="text-xs text-ink-3">Searches Hacker News, Reddit, GitHub issues and status pages / blogs (public, no login), then suggests topics grounded in what it finds.</span>
        </div>
        {msg && <p className="text-xs text-ink-2">{msg}</p>}
      </div>
    </Section>
  );
}

function NewsPanel() {
  const [news] = useProjectFile<any>("research/news.json");
  const [open, setOpen] = useState(false);
  if (!news) return null;
  if (news.off) return <Note>Live research is off (Settings → Research).</Note>;
  const items: any[] = news.items ?? [];
  const failed = Object.entries(news.sources ?? {}).filter(([, v]: any) => !v.ok);
  return (
    <Section title={`Live AI news: ${items.length} items, last ${news.days} days${news.brief ? ` · about “${news.brief}”` : ""}`}
      right={<span className="flex items-center gap-2">{news.synthetic && <SyntheticBadge />}<RunStageButton stage="news" label="Refresh news" /></span>}>
      {failed.length > 0 && <p className="mb-2 text-xs text-ink-3">Did not answer: {failed.map(([k, v]: any) => `${k} (${v.error})`).join(" · ")}</p>}
      {items.length === 0 ? <Empty>Nothing found. Try other words, or a longer look-back in Settings → Research.</Empty> : (
        <ul className="grid gap-1.5 text-sm" data-testid="news-list">
          {(open ? items : items.slice(0, 8)).map((it) => (
            <li key={it.id} className="flex flex-wrap items-baseline gap-2">
              <Kind kind={it.kind} />
              <a className="text-ink underline-offset-2 hover:underline" href={it.discussion_url || it.url} target="_blank" rel="noreferrer">{it.title}</a>
              <span className="text-xs text-ink-3">{it.where} · {String(it.date).slice(0, 10)}{it.engagement ? ` · ${it.engagement} reactions` : ""}{it.comments ? ` · ${it.comments} comments` : ""}{it.tools?.length ? ` · ${it.tools.join(", ")}` : ""}</span>
            </li>))}
        </ul>)}
      {items.length > 8 && <button className="btn mt-2" onClick={() => setOpen(!open)}>{open ? "Show fewer" : `Show all ${items.length}`}</button>}
    </Section>
  );
}

export default function Topics() {
  const { snap } = useProject();
  const [data] = useProjectFile<any>("research/topics.json");
  const [choice, setChoice] = useState<string | null>(null);
  const gate = snap?.gates.find((g) => g.name === "topic");
  const pending = gate?.status === "pending";
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="h1">4 · Topic finder</h1>
        <span className="flex items-center gap-2">{data?.synthetic_evidence && <SyntheticBadge />}<RunStageButton stage="topics" /></span>
      </div>
      <ResearchBox />
      <NewsPanel />
      {data && <Note>score = {Object.entries({ ...(data.weights ?? {}), ...(data.news_items ? { news: data.weights?.news ?? 0.3 } : {}) }).map(([k, w]) => `${w} × ${COMP[k] ?? k}`).join(" + ")} (weights in Settings).{data.brief ? ` Topics are about: “${data.brief}”.` : ""}</Note>}
      <GatePanel name="topic" title="Pick the topic" choice={choice} setChoice={setChoice}>
        <p className="text-sm text-ink-2">{pending ? "Click a topic card, then approve. The pipeline continues to Hooks." : "Approved topics feed the Hooks stage."}</p>
      </GatePanel>
      {!data ? <Empty>No topics yet. Run Topics, or describe a topic above and press Research this.</Empty> : (
        <div className="grid gap-3" data-testid="topic-board">
          {data.topics.map((t: any) => {
            const selected = (choice ?? gate?.choice ?? gate?.payload?.default_choice) === t.id;
            return (
              <button key={t.id} type="button" disabled={!pending} onClick={() => setChoice(t.id)} data-testid={`topic-${t.id}`}
                className={`card text-left ${selected ? "ring-2 ring-accent" : ""} ${pending ? "cursor-pointer hover:bg-surface-2" : "cursor-default"}`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="text-xs text-ink-3">#{t.rank} · score {t.score.toFixed(2)} {selected && "· ✓ selected"}</div>
                    <div className="text-base font-semibold text-ink">{t.title}</div>
                    <div className="text-sm text-ink-2">{t.angle}</div>
                    {t.story && <div className="mt-1 text-sm"><b>What really happened:</b> {t.story}</div>}
                  </div>
                  {String(t.demand_note ?? "").startsWith("dry-run") && <FixtureBadge />}
                </div>
                <div className="mt-3 grid gap-4 md:grid-cols-2">
                  <Bars items={Object.entries(t.components).map(([k, v]) => ({ label: COMP[k] ?? k, value: v as number }))} />
                  <div className="text-xs text-ink-2">
                    {t.sources?.length > 0 && <><div className="label">Real posts it grows from</div>
                      <ul className="mb-2 space-y-0.5">{t.sources.map((s: any) => (
                        <li key={s.id}><Kind kind={s.kind} /> <a className="underline-offset-2 hover:underline" href={s.discussion_url || s.url} target="_blank" rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}>{s.title}</a> · {s.where} · {String(s.date).slice(0, 10)}{s.synthetic ? " (synthetic)" : ""}</li>))}</ul></>}
                    <div className="label">Evidence</div>
                    {t.evidence.length ? <ul className="space-y-0.5">{t.evidence.map((e: any, i: number) => (
                      <li key={i}>{e.multiple?.toFixed(1)}× · {e.title}{e.synthetic ? " (synthetic)" : ""}</li>))}</ul> : <span className="muted">no related outliers found</span>}
                    <div className="mt-1"><b>Stick-figure fit:</b> {t.stickman_reason}</div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
