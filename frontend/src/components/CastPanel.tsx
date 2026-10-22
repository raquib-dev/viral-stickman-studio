import { useEffect, useState } from "react";
import { api, fileUrl } from "../lib/api";
import { useProject } from "../lib/useProject";
import { Section } from "./ui";

/** Dialogue shorts: the two characters. Names, roles (they steer the writing), voices, and looks; a real still
 *  render shows them at the desk. Saved on the project; changing a look or voice re-renders the clips it affects. */
export function CastPanel() {
  const { slug, snap, refresh } = useProject();
  const [opts, setOpts] = useState<any>(null);
  const [cast, setCast] = useState<any>(null);
  const [img, setImg] = useState<{ image: string; at: number } | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get<any>("/dialogue/cast-defaults").then(setOpts).catch((e) => setMsg(e.message)); }, []);
  useEffect(() => {
    if (!opts) return;
    const mine = snap?.project.data.cast ?? {};
    const merge = (d: any, m: any) => ({ ...d, ...m, appearance: { ...d.appearance, ...(m?.appearance ?? {}) } });
    setCast({ a: merge(opts.cast.a, mine.a), b: merge(opts.cast.b, mine.b) });
  }, [opts, snap?.project.data.cast]);
  if (!opts || !cast) return null;
  const set = (s: "a" | "b", k: string, v: any) => setCast((c: any) => ({ ...c, [s]: { ...c[s], [k]: v } }));
  const look = (s: "a" | "b", k: string, v: any) => setCast((c: any) => ({ ...c, [s]: { ...c[s], appearance: { ...c[s].appearance, [k]: v } } }));
  const save = async () => {
    setMsg(null);
    try { await api.put(`/projects/${slug}`, { cast }); await refresh(); setMsg("Saved."); } catch (e: any) { setMsg(e.message); }
  };
  const preview = async () => {
    setBusy(true); setMsg(null);
    try { await api.put(`/projects/${slug}`, { cast }); const r = await api.post<any>(`/projects/${slug}/cast/preview`); setImg({ image: r.image, at: r.updated_at }); }
    catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  };
  const a = cast.a, b = cast.b, ap = a.appearance, bp = b.appearance;
  const color = (s: "a" | "b", k: string, label: string) => (
    <label className="text-sm">{label}<input className="input h-9 p-1" type="color" value={(s === "a" ? ap : bp)[k] ?? "#000000"} onChange={(e) => look(s, k, e.target.value)} /></label>);
  const sel = (value: string, onChange: (v: string) => void, list: string[]) => (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>{list.map((x) => <option key={x}>{x}</option>)}</select>);
  return (
    <Section title="Cast (dialogue short)" right={<span className="flex gap-2">
      <button className="btn" onClick={preview} disabled={busy} data-testid="cast-preview">{busy ? "Rendering…" : "Preview cast"}</button>
      <button className="btn-primary" onClick={save} data-testid="cast-save">Save cast</button></span>}>
      <div className="grid gap-4 md:grid-cols-[1fr_1fr_220px]" data-testid="cast-panel">
        <div className="grid content-start gap-2">
          <b className="text-sm">Character a: the person</b>
          <label className="text-sm">Name<input className="input" value={a.name} onChange={(e) => set("a", "name", e.target.value)} /></label>
          <label className="text-sm">Role (steers the writing)<input className="input" value={a.role} onChange={(e) => set("a", "role", e.target.value)} /></label>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-sm">Voice{sel(a.voice, (v) => set("a", "voice", v), opts.voices)}</label>
            <label className="text-sm">Hair{sel(ap.hair_style, (v) => look("a", "hair_style", v), opts.hair_styles)}</label>
            <label className="text-sm">Glasses{sel(ap.glasses, (v) => look("a", "glasses", v), opts.glasses)}</label>
            <label className="text-sm">Face variant<input className="input" type="number" min={0} max={99} value={ap.variant ?? 0} onChange={(e) => look("a", "variant", Number(e.target.value))} title="0 = the base face; any other number nudges eye spacing, jaw, head shape slightly (same person, a little different)" /></label>
          </div>
          <div className="grid grid-cols-4 gap-2">{color("a", "skin", "Skin")}{color("a", "hair", "Hair")}{color("a", "top", "Jacket")}{color("a", "shirt", "Shirt")}</div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!ap.headphones} onChange={(e) => look("a", "headphones", e.target.checked)} />Headphones</label>
        </div>
        <div className="grid content-start gap-2">
          <b className="text-sm">Character b: the mascot</b>
          <label className="text-sm">Name<input className="input" value={b.name} onChange={(e) => set("b", "name", e.target.value)} /></label>
          <label className="text-sm">Role (steers the writing)<input className="input" value={b.role} onChange={(e) => set("b", "role", e.target.value)} /></label>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-sm">Voice{sel(b.voice, (v) => set("b", "voice", v), opts.voices)}</label>
            <label className="text-sm">Shape{sel(bp.shape, (v) => look("b", "shape", v), opts.mascot_shapes)}</label>
          </div>
          <div className="grid grid-cols-4 gap-2">{color("b", "color", "Colour")}</div>
          <p className="text-xs text-ink-3">The "mascot" voice is set per engine in Settings → Voice (Kokoro defaults to am_puck); Settings → Dialogue → mascot pitch lifts it. Use your own mascot design for a channel: a well-known brand's logo or colours belong to that brand.</p>
        </div>
        <div>{img ? <img className="w-full rounded-lg bg-black" src={fileUrl(slug!, img.image, img.at)} alt="cast preview" data-testid="cast-image" />
          : <div className="flex aspect-[9/16] items-center justify-center rounded-lg border border-line text-xs text-ink-3">Preview cast renders them at the desk</div>}</div>
      </div>
      {msg && <p className="mt-2 text-xs">{msg}</p>}
    </Section>
  );
}
