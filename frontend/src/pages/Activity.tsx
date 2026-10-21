import { useEffect, useMemo, useRef, useState } from "react";
import { Empty, ErrorBox, Section, StatusChip, fmtDur, fmtUsd } from "../components/ui";
import { api, Job, LogLine } from "../lib/api";
import { useNow, useProject } from "../lib/useProject";

const LEVELS = ["all", "warn+", "error"] as const;

/** Every job this project has run: what it did, how long, what it cost, why it failed, and its full log. */
export default function Activity() {
  const { slug, snap, version, clipTick } = useProject();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [stage, setStage] = useState("all");
  const now = useNow();
  useEffect(() => {
    if (!slug) return;
    api.get<Job[]>(`/projects/${slug}/jobs`).then(setJobs).catch((e) => setErr(e.message));
  }, [slug, version, clipTick, snap]);
  const shown = useMemo(() => jobs.filter((j) => stage === "all" || j.stage === stage), [jobs, stage]);
  const stages = useMemo(() => Array.from(new Set(jobs.map((j) => j.stage))), [jobs]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const j of jobs) c[j.status] = (c[j.status] ?? 0) + 1;
    return c;
  }, [jobs]);
  const act = async (fn: () => Promise<unknown>) => { setErr(null); try { await fn(); } catch (e: any) { setErr(e.message); } };
  const selected = jobs.find((j) => j.id === sel) ?? null;
  return (
    <div className="grid gap-5" data-testid="activity">
      <h1 className="h1">Activity</h1>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {Object.entries(counts).map(([k, v]) => <span key={k} className="chip"><StatusChip status={k} small /> {v}</span>)}
        <span className="chip">total spent {fmtUsd(jobs.reduce((a, j) => a + (j.cost_usd || 0), 0))}</span>
        <select className="input ml-auto !w-44 !py-1 text-xs" value={stage} onChange={(e) => setStage(e.target.value)}>
          <option value="all">all stages</option>{stages.map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      {err && <ErrorBox>{err}</ErrorBox>}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <Section title={`Jobs (${shown.length})`}>
          {!shown.length ? <Empty>Nothing has run yet.</Empty> : (
            <ul className="grid gap-1.5" data-testid="job-list">
              {shown.map((j) => {
                const running = j.status === "running" || j.status === "queued";
                const dur = j.started_at ? (j.finished_at ?? now) - j.started_at : null;
                return (
                  <li key={j.id}>
                    <button type="button" onClick={() => setSel(j.id)} data-testid={`job-${j.id}`}
                      className={`w-full rounded-lg border px-3 py-2 text-left text-sm hover:bg-surface-2 ${sel === j.id ? "border-accent" : "border-line"}`}>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs text-ink-3">#{j.id}</span>
                        <b>{j.stage}</b>
                        {paramsLabel(j.params) && <span className="chip !py-0 text-[11px]">{paramsLabel(j.params)}</span>}
                        <StatusChip status={j.status} small />
                        <span className="ml-auto text-xs text-ink-3">{new Date((j.started_at ?? j.created_at) * 1000).toLocaleString()}</span>
                      </div>
                      <div className="mt-1 flex flex-wrap gap-3 text-xs text-ink-3">
                        <span>{running ? "running for" : "took"} {fmtDur(dur)}</span>
                        {j.cost_usd > 0 && <span>{fmtUsd(j.cost_usd)}</span>}
                        {running && j.message && <span className="text-ink-2">{Math.round((j.progress ?? 0) * 100)}% · {j.message}</span>}
                      </div>
                      {j.error && <div className="mt-1 line-clamp-2 text-xs" style={{ color: "var(--critical)" }}>{j.error}</div>}
                    </button>
                    {sel === j.id && (
                      <div className="mt-1 flex gap-2 px-1">
                        {running ? (
                          <button className="btn-danger !py-0.5 text-xs" onClick={() => act(() => api.post(`/jobs/${j.id}/cancel`))}>■ Cancel</button>
                        ) : (
                          <button className="btn !py-0.5 text-xs" data-testid={`retry-${j.id}`} disabled={snap?.pipeline?.status === "running"}
                            title="Run this stage again with the same settings" onClick={() => act(() => api.post(`/jobs/${j.id}/retry`))}>↻ Retry this job</button>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Section>
        <Section title={selected ? `Log · #${selected.id} ${selected.stage}` : "Log"}>
          {selected ? <JobLog job={selected} /> : <Empty>Pick a job to see everything it did.</Empty>}
        </Section>
      </div>
    </div>
  );
}

function paramsLabel(p: Record<string, any>): string {
  if (!p) return "";
  const bits: string[] = [];
  if (p.via === "pipeline") bits.push("pipeline");
  if (p.only?.length) bits.push(`clip ${p.only.join(", ")} only`);
  if (p.force && !p.only?.length) bits.push("forced");
  return bits.join(" · ");
}

function JobLog({ job }: { job: Job }) {
  const { logs: live } = useProject();
  const [lines, setLines] = useState<LogLine[]>([]);
  const [lvl, setLvl] = useState<(typeof LEVELS)[number]>("all");
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let on = true;
    api.get<Job & { logs: LogLine[] }>(`/jobs/${job.id}`).then((d) => on && setLines(d.logs)).catch(() => {});
    return () => { on = false; };
  }, [job.id, job.status]);
  const merged = useMemo(() => {
    const seen = new Set(lines.map((l) => l.id));
    return [...lines, ...live.filter((l) => l.job_id === job.id && !seen.has(l.id))];
  }, [lines, live, job.id]);
  const shown = merged.filter((l) => lvl === "all" || (lvl === "error" ? l.level === "error" : ["warn", "error"].includes(l.level)));
  useEffect(() => { box.current?.scrollTo(0, box.current.scrollHeight); }, [shown.length]);
  const color = (l: string) => l === "error" ? "var(--critical)" : l === "warn" ? "var(--serious)" : l === "gate" ? "var(--accent)" : "var(--text-muted)";
  const t0 = merged[0]?.ts ?? 0;
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-xs">
        {LEVELS.map((l) => <button key={l} className={`btn !py-0.5 ${lvl === l ? "ring-2 ring-accent" : ""}`} onClick={() => setLvl(l)}>{l}</button>)}
        <span className="ml-auto text-ink-3">{merged.length} lines · {merged.filter((l) => l.level === "warn").length} warnings</span>
      </div>
      <div ref={box} className="h-[28rem] overflow-auto rounded-lg bg-surface-2 p-2 font-mono text-[11px] leading-5" data-testid="job-log">
        {shown.map((l) => (
          <div key={l.id} className="whitespace-pre-wrap">
            <span className="text-ink-3">+{fmtDur(l.ts - t0).padStart(4)} </span>
            <span style={{ color: color(l.level) }}>{l.level !== "info" ? `${l.level}: ` : ""}</span>
            <span className="text-ink">{l.text}</span>
          </div>
        ))}
        {!shown.length && <div className="text-ink-3">No lines at this level.</div>}
      </div>
    </div>
  );
}
