import { useState } from "react";
import { RunStageButton } from "../components/Pipeline";
import { Empty, ErrorBox, FixtureBadge, Note, Section } from "../components/ui";
import { api } from "../lib/api";
import { useProject, useProjectFile } from "../lib/useProject";

export default function Learn() {
  const { slug } = useProject();
  const [report] = useProjectFile<any>("research/learn/report.json");
  const [learned] = useProjectFile<any[]>("research/learned.json");
  const [ig, setIg] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="h1">9 · Learn loop</h1><RunStageButton stage="learn" primary label="Run Learn" />
      </div>
      <Note>After you publish (always by hand), bring the numbers back here. Findings shift the niche pattern profile, so the next video's beats are placed using your own results.</Note>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="YouTube Studio retention CSV">
          <p className="mb-2 text-xs text-ink-3">Studio → the video → Analytics → Engagement → audience-retention chart → download → "Audience retention".</p>
          <input type="file" accept=".csv,text/csv" data-testid="retention-upload" onChange={async (e) => {
            const f = e.target.files?.[0]; if (!f) return;
            const fd = new FormData(); fd.append("file", f);
            setErr(null);
            try { await api.upload(`/projects/${slug}/learn/retention`, fd); setMsg(`uploaded ${f.name}`); } catch (er: any) { setErr(er.message); }
          }} />
        </Section>
        <Section title="Instagram insights (paste)">
          <textarea className="input h-28" value={ig} onChange={(e) => setIg(e.target.value)} placeholder="views, reach, non-follower %, hold at 3 s, avg watch time, sends, saves, follows…" />
          <button className="btn mt-2" onClick={async () => { setErr(null); try { await api.post(`/projects/${slug}/learn/ig`, { text: ig }); setMsg("insights saved"); } catch (e: any) { setErr(e.message); } }}>Save insights</button>
        </Section>
      </div>
      {msg && <p className="text-sm text-ink-2">✓ {msg}. Now run Learn.</p>}
      {err && <ErrorBox>{err}</ErrorBox>}
      <Section title="Findings" right={report?.read?._fixture ? <FixtureBadge /> : undefined}>
        {!report ? <Empty>No learn report yet.</Empty> : (
          <div className="grid gap-3 text-sm">
            {report.retention && <p><b>retention.py:</b> hook leak {report.retention.hook_leak}% · {report.retention.cliffs.length} cliff(s) · slide {report.retention.slide_per_unit}%/unit</p>}
            <p><b>Biggest leak:</b> {report.read.biggest_leak}</p><p><b>One change:</b> {report.read.change}</p>
            {report.read.ig_findings.length > 0 && <ul className="list-disc pl-5">{report.read.ig_findings.map((f: string) => <li key={f}>{f}</li>)}</ul>}
            <div><div className="label">Profile adjustments (applied to the next video)</div>
              {(learned ?? []).length ? <table className="table"><thead><tr><th>Beat</th><th>Shift</th><th>Reason</th><th>From</th></tr></thead>
                <tbody>{learned!.map((a, i) => <tr key={i}><td>{a.type}</td><td>{a.shift_pct > 0 ? "+" : ""}{a.shift_pct}%</td><td>{a.reason}</td><td className="text-ink-2">{a.from_video}</td></tr>)}</tbody></table>
                : <span className="muted">none</span>}</div>
            <p className="text-xs text-ink-3">One video is one data point; treat shifts as hypotheses to test, not rules.</p>
          </div>
        )}
      </Section>
    </div>
  );
}
