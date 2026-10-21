import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { NicheForm, SAMPLE } from "../components/NicheForm";
import { ErrorBox, Note, Section, StatusChip } from "../components/ui";
import { api, Snapshot } from "../lib/api";

export default function Home() {
  const [projects, setProjects] = useState<{ slug: string; name: string; pipeline: string | null; created_at: number }[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  useEffect(() => { api.get<typeof projects>("/projects").then(setProjects).catch((e) => setErr(e.message)); }, []);
  return (
    <div className="grid gap-5">
      <div>
        <h1 className="h1">Viral Stickman Studio</h1>
        <p className="mt-1 text-ink-2">Niche → viral discovery → why it worked → topic → hook → script → director → Omni Flash render → package → learn.
          Nothing is ever published; every output ends as files and copy blocks.</p>
      </div>
      {projects.length > 0 && (
        <Section title="Your projects">
          <ul className="divide-y divide-line">
            {projects.map((p) => (
              <li key={p.slug} className="flex items-center justify-between py-2">
                <Link className="font-medium text-ink hover:underline" to={`/p/${p.slug}/niche`}>{p.name}</Link>
                <span className="flex items-center gap-2 text-xs text-ink-3"><StatusChip status={p.pipeline ?? "idle"} small />{new Date(p.created_at * 1000).toLocaleDateString()}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
      <Section title="New project (niche setup)">
        <Note>Pre-filled with the sample niche used by the end-to-end dry run. Change anything.</Note>
        <div className="mt-3">
          <NicheForm initial={SAMPLE} submitLabel="Create project" busy={busy} onSubmit={async (d) => {
            setBusy(true); setErr(null);
            try { const s = await api.post<Snapshot>("/projects", d); nav(`/p/${s.project.slug}/niche`); }
            catch (e: any) { setErr(e.message); } finally { setBusy(false); }
          }} />
        </div>
        {err && <div className="mt-2"><ErrorBox>{err}</ErrorBox></div>}
      </Section>
    </div>
  );
}
