import { useState } from "react";
import { api } from "../lib/api";
import { useProject, useProjectFile } from "../lib/useProject";

/** The {{...}} gaps still in the narration (found in the text itself, so older scripts show them too). */
export function scriptGaps(script: any): { name: string; clips: number[] }[] {
  const found = new Map<string, Set<number>>();
  for (const c of script?.clips ?? []) {
    for (const m of String(c.vo ?? "").matchAll(/\{\{\s*([^{}]+?)\s*\}\}/g)) {
      if (!found.has(m[1])) found.set(m[1], new Set());
      found.get(m[1])!.add((c.index ?? 0) + 1);
    }
  }
  return [...found].map(([name, clips]) => ({ name, clips: [...clips].sort((a, b) => a - b) }));
}

/** Fill in a figure only you know, or let the writing model rephrase those lines so they need none. */
export function ScriptGaps() {
  const { slug, snap } = useProject();
  const [script, , reload] = useProjectFile<any>("script/script.json");
  const [vals, setVals] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const gaps = scriptGaps(script);
  if (!gaps.length) return null;
  const rewriting = ["running", "queued"].includes(snap?.stages.find((s) => s.stage === "script_gaps")?.status ?? "");
  const fill = async () => {
    setMsg(null);
    try { await api.post(`/projects/${slug}/script/fill`, { values: vals }); setVals({}); reload(); } catch (e: any) { setMsg(e.message); }
  };
  const rewrite = async () => {
    setMsg(null);
    try { await api.post(`/projects/${slug}/stages/script_gaps/run`, { params: {} }); setMsg("Rewriting those lines… (see Activity)"); } catch (e: any) { setMsg(e.message); }
  };
  return (
    <div className="rounded-lg border px-3 py-2 text-sm" style={{ borderColor: "var(--serious)" }} data-testid="script-gaps">
      <b>The script needs a number only you know.</b> Type it below, or let the writing model rephrase those lines so
      they need no number. The app never makes one up, and a render stops until this is done (the voice would read
      the gap out).
      <div className="mt-2 grid gap-2 md:grid-cols-2">{gaps.map((g) => (
        <label key={g.name} className="text-sm">{`{{${g.name}}}`} <span className="text-ink-3">(clip {g.clips.join(", ")})</span>
          <input className="input" value={vals[g.name] ?? ""} placeholder="your real value, e.g. $40" onChange={(e) => setVals({ ...vals, [g.name]: e.target.value })} /></label>))}</div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button className="btn-primary" onClick={fill} disabled={!Object.values(vals).some((v) => v.trim())} data-testid="fill-gaps">Fill in</button>
        <span className="text-ink-3">or</span>
        <button className="btn" onClick={rewrite} disabled={rewriting} data-testid="rewrite-gaps">✦ Rewrite without the number</button>
        {msg && <span className="text-xs">{msg}</span>}
      </div>
      <p className="mt-1 text-xs text-ink-3">Settings → Script gaps → <b>rewrite automatically</b> does the rewrite by itself, so renders never stop here.</p>
    </div>);
}
