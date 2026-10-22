import { useState } from "react";
import type { ProjectData } from "../lib/api";

export const STYLES = [
  ["1", "Style 1 · Classic Minimalist (light/dark)"], ["2A", "Style 2A · Modern Studio Tech"], ["2B", "Style 2B · Cinematic Story"],
  ["3", "Style 3 · Prehistoric Dark Comedy"], ["4", "Style 4 · Cozy Storytelling"], ["5", "Style 5 · Historical Cartoon"],
];
const PLATFORMS = [["youtube_long", "YouTube long-form"], ["shorts", "YouTube Shorts"], ["reels", "Instagram Reels"]];

export const SAMPLE: ProjectData = {
  name: "Money mind", niche: "personal finance psychology", subtopics: ["saving", "spending", "money habits"],
  platforms: ["shorts", "reels"], style: "1", theme: "dark", ratio: "9:16", duration: 60,
  competitors: { youtube: [], instagram: [] }, voice_pref: "male", voice_transcripts: { youtube: [], instagram: [] },
};

const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

export function NicheForm({ initial, submitLabel, onSubmit, busy }: {
  initial: ProjectData; submitLabel: string; onSubmit: (d: ProjectData) => void; busy?: boolean;
}) {
  const [d, setD] = useState<ProjectData>(initial);
  const set = (k: keyof ProjectData, v: any) => setD((x) => ({ ...x, [k]: v }));
  const togglePlat = (p: string) => set("platforms", d.platforms.includes(p) ? d.platforms.filter((x) => x !== p) : [...d.platforms, p]);
  const trs = d.voice_transcripts ?? { youtube: [], instagram: [] };
  return (
    <form className="grid gap-4" onSubmit={(e) => { e.preventDefault(); onSubmit(d); }} data-testid="niche-form">
      <div className="grid gap-4 md:grid-cols-2">
        <div><label className="label">Project name</label><input className="input" required value={d.name} onChange={(e) => set("name", e.target.value)} data-testid="f-name" /></div>
        <div><label className="label">Niche</label><input className="input" required value={d.niche} onChange={(e) => set("niche", e.target.value)} data-testid="f-niche" placeholder="e.g. personal finance psychology" /></div>
        <div className="md:col-span-2"><label className="label">Sub-topics (comma separated)</label>
          <input className="input" value={d.subtopics.join(", ")} onChange={(e) => set("subtopics", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} /></div>
        <div className="md:col-span-2"><label className="label">Base topic (optional): describe what this video should be about</label>
          <textarea className="input min-h-[64px]" value={d.topic_brief ?? ""} onChange={(e) => set("topic_brief", e.target.value)} data-testid="f-brief"
            placeholder="e.g. AI agents that 'fix' a failing test by deleting it; or this week's usage-limit complaints" />
          <p className="mt-1 text-xs text-ink-3">The AI news research searches for this, and every topic it suggests is about it. Leave empty to research what is happening across AI tools.</p></div>
      </div>
      <div className="grid gap-4 md:grid-cols-4">
        <div className="md:col-span-2"><label className="label">Video format</label>
          <select className="input" value={d.format ?? "narrated"} onChange={(e) => set("format", e.target.value)} data-testid="f-format">
            <option value="narrated">Narrated stickman explainer (one narrator)</option>
            <option value="dialogue">Dialogue short (a person and a mascot talk, 3D, cut per line)</option></select></div>
        {d.format === "dialogue" && <>
          <div><label className="label">Person's name (character a)</label>
            <input className="input" value={d.cast?.a?.name ?? "Mia"} onChange={(e) => set("cast", { ...d.cast, a: { ...d.cast?.a, name: e.target.value } })} data-testid="f-cast-a" /></div>
          <div><label className="label">Mascot's name (character b)</label>
            <input className="input" value={d.cast?.b?.name ?? "Claude"} onChange={(e) => set("cast", { ...d.cast, b: { ...d.cast?.b, name: e.target.value } })} data-testid="f-cast-b" /></div>
          <p className="text-xs text-ink-3 md:col-span-4">Looks, voices and roles are on the Render page (Cast). Dialogue shorts render with Settings → Render → <b>local-threejs</b>.</p>
        </>}
      </div>
      <div className="grid gap-4 md:grid-cols-4">
        <div className="md:col-span-2"><span className="label">Target platforms</span>
          <div className="flex flex-wrap gap-3">{PLATFORMS.map(([id, l]) => (
            <label key={id} className="flex items-center gap-1.5 text-sm"><input type="checkbox" checked={d.platforms.includes(id)} onChange={() => togglePlat(id)} />{l}</label>))}
          </div></div>
        <div><label className="label">Aspect ratio</label>
          <select className="input" value={d.ratio} onChange={(e) => set("ratio", e.target.value)}><option value="9:16">9:16 vertical</option><option value="16:9">16:9 horizontal</option></select></div>
        <div><label className="label">Duration (10 s steps)</label>
          <input className="input" type="number" min={10} max={600} step={10} value={d.duration} onChange={(e) => set("duration", Number(e.target.value))} /></div>
        <div className="md:col-span-2"><label className="label">Default style</label>
          <select className="input" value={d.style} onChange={(e) => set("style", e.target.value)}>{STYLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
        <div><label className="label">Theme (Style 1)</label>
          <select className="input" value={d.theme} onChange={(e) => set("theme", e.target.value)} disabled={d.style !== "1"}><option value="dark">dark</option><option value="light">light</option></select></div>
        <div><label className="label">Narrator</label>
          <select className="input" value={d.voice_pref} onChange={(e) => set("voice_pref", e.target.value)}><option value="male">male (tested profile)</option><option value="female">female (illustrative profile)</option></select></div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div><label className="label">Competitor YouTube channels (one per line: @handle or URL)</label>
          <textarea className="input h-24" value={d.competitors.youtube.join("\n")} onChange={(e) => set("competitors", { ...d.competitors, youtube: lines(e.target.value) })} /></div>
        <div><label className="label">Competitor Instagram accounts (one per line)</label>
          <textarea className="input h-24" value={d.competitors.instagram.join("\n")} onChange={(e) => set("competitors", { ...d.competitors, instagram: lines(e.target.value) })} /></div>
      </div>
      <details className="card-2">
        <summary className="cursor-pointer text-sm font-semibold">Build my voice.md from three of my own videos (optional)</summary>
        <p className="mb-2 mt-1 text-xs text-ink-3">Paste transcripts of your own videos/reels, separated by a line with three dashes (---). The Niche stage drafts a voice.md for each platform; you review and apply it.</p>
        <div className="grid gap-4 md:grid-cols-2">
          {(["youtube", "instagram"] as const).map((p) => (
            <div key={p}><label className="label">{p} transcripts</label>
              <textarea className="input h-32" value={(trs[p] ?? []).join("\n---\n")}
                onChange={(e) => set("voice_transcripts", { ...trs, [p]: e.target.value.split(/\n---\n/).map((x) => x.trim()).filter(Boolean) })} /></div>
          ))}
        </div>
      </details>
      <div><button className="btn-primary" disabled={busy} data-testid="niche-submit">{submitLabel}</button></div>
    </form>
  );
}
