import { useEffect, useState } from "react";
import { NicheForm } from "../components/NicheForm";
import { RunStageButton } from "../components/Pipeline";
import { ErrorBox, Note, Section } from "../components/ui";
import { api } from "../lib/api";
import { useProject, useProjectFile } from "../lib/useProject";

export default function Niche() {
  const { slug, snap, refresh } = useProject();
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!snap) return <div className="muted">Loading…</div>;
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="h1">1 · Niche setup</h1><RunStageButton stage="niche" />
      </div>
      <Section title="Brief">
        <NicheForm key={snap.project.slug} initial={snap.project.data} submitLabel="Save niche" onSubmit={async (d) => {
          setErr(null);
          try { await api.put(`/projects/${slug}`, d); await refresh(); setMsg("Saved. Run the pipeline or the Niche stage to use it."); }
          catch (e: any) { setErr(e.message); }
        }} />
        {msg && <p className="mt-2 text-sm text-ink-2">✓ {msg}</p>}
        {err && <ErrorBox>{err}</ErrorBox>}
      </Section>
      <VoiceProfiles />
    </div>
  );
}

function VoiceProfiles() {
  const { slug } = useProject();
  return (
    <Section title="Voice profiles (config/voice/*.md, read by every yt-* and ig-* skill)">
      <Note>These replace the packs' ~/.claude/youtube/voice.md and ~/.claude/instagram/voice.md. A draft from your own videos appears below after the Niche stage runs with transcripts.</Note>
      <div className="mt-3 grid gap-4 lg:grid-cols-2">
        {(["youtube", "instagram"] as const).map((p) => <VoiceEditor key={p} platform={p} slug={slug!} />)}
      </div>
    </Section>
  );
}

function VoiceEditor({ platform, slug }: { platform: "youtube" | "instagram"; slug: string }) {
  const [md, setMd] = useState("");
  const [saved, setSaved] = useState("");
  const [draft] = useProjectFile<string>(`research/voice-draft-${platform}.md`);
  const load = () => api.get<{ markdown: string }>(`/voice/${platform}`).then((r) => setMd(r.markdown));
  useEffect(() => { load(); }, [platform]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="card-2">
      <div className="mb-2 flex items-center justify-between"><span className="h2">{platform}.md</span>
        <span className="flex gap-2">
          {draft && <button className="btn" onClick={async () => { await api.post(`/projects/${slug}/voice/apply`, { platform }); await load(); setSaved("draft applied (old file backed up)"); }}>Apply draft</button>}
          <button className="btn" onClick={async () => { await api.put(`/voice/${platform}`, { markdown: md }); setSaved("saved"); }}>Save</button>
        </span></div>
      <textarea className="input h-64 font-mono text-xs" value={md} onChange={(e) => setMd(e.target.value)} />
      {saved && <p className="mt-1 text-xs text-ink-3">✓ {saved}</p>}
      {draft && <details className="mt-2"><summary className="cursor-pointer text-xs font-semibold">Draft from your videos</summary><pre className="code mt-1 max-h-48 overflow-auto">{draft}</pre></details>}
    </div>
  );
}
