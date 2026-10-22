import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ErrorBox, Note, Section } from "../components/ui";
import { api, fileUrl } from "../lib/api";
import { useProject } from "../lib/useProject";

// Phase 5: edit one clip's 3D scene plan. Every change is data (the same scene format the AI writes), checked
// by the server (unknown names, frame, numbers), previewed as a still, saved as yours (never overwritten by
// the planner), and re-rendered on request.

type Col = { key: string; label: string; type: "num" | "text" | "select"; options?: string[]; step?: number; w?: string };
const MOOD_COLOR: Record<string, string> = {
  neutral: "#9aa3b2", money: "#58d68d", success: "#ffcf3d", danger: "#ff4d4d", calm: "#7cc4ff", tech: "#4de1ff",
  mystery: "#b48cff", nostalgia: "#e8b46b", sad: "#8aa2b8", love: "#ff7aa8", nature: "#7ccf6b",
};
const PLACES: Record<string, any> = {
  "floor, right": { pos: [0.55, 0, 0.15] }, "floor, left": { pos: [-0.55, 0, 0.15] },
  "chest height, right": { pos: [0.55, 1.25, 0.1] }, "chest height, left": { pos: [-0.55, 1.25, 0.1] },
  "above the head": { pos: [0, 2.05, -0.3] }, "held in right hand": { hold: { actor: "hero", hand: "R" } },
  "held in left hand": { hold: { actor: "hero", hand: "L" } },
};
const placeOf = (p: any) => (p.hold ? `held in ${p.hold.hand === "L" ? "left" : "right"} hand`
  : Object.keys(PLACES).find((k) => JSON.stringify(PLACES[k].pos) === JSON.stringify(p.pos)) ?? "custom");

function Rows({ rows, cols, onChange, make, testid }: { rows: any[]; cols: Col[]; onChange: (r: any[]) => void; make: () => any; testid?: string }) {
  const set = (i: number, k: string, v: any) => onChange(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <div className="grid gap-1" data-testid={testid}>
      {rows.map((r, i) => (
        <div key={i} className="flex flex-wrap items-end gap-1">
          {cols.map((c) => (
            <label key={c.key} className="text-[11px] text-ink-3" style={{ width: c.w ?? (c.type === "num" ? "4.5rem" : "9rem") }}>{c.label}
              {c.type === "select" ? (
                <select className="input !py-1 text-xs" value={r[c.key] ?? ""} onChange={(e) => set(i, c.key, e.target.value || undefined)}>
                  {["", ...(c.options ?? [])].map((o) => <option key={o} value={o}>{o || "—"}</option>)}</select>
              ) : (
                <input className="input !py-1 text-xs" type={c.type === "num" ? "number" : "text"} step={c.step ?? 0.1} value={r[c.key] ?? ""}
                  onChange={(e) => set(i, c.key, c.type === "num" ? (e.target.value === "" ? undefined : Number(e.target.value)) : e.target.value)} />
              )}
            </label>
          ))}
          <button className="btn !px-2 !py-1 text-xs" title="remove" onClick={() => onChange(rows.filter((_, j) => j !== i))}>✕</button>
        </div>
      ))}
      <div><button className="btn !py-0.5 text-xs" onClick={() => onChange([...rows, make()])}>+ add</button></div>
    </div>
  );
}

function Timeline({ scene, duration, talk, t, setT }: { scene: any; duration: number; talk: number[]; t: number; setT: (v: number) => void }) {
  const x = (v: number) => `${(Math.max(0, Math.min(duration, v)) / duration) * 100}%`;
  const moods: any[] = Array.isArray(scene.mood) ? scene.mood : [{ t: 0, mood: scene.mood ?? "neutral" }];
  const hero = scene.actors?.[0] ?? {};
  const lane = (label: string, children: React.ReactNode) => (
    <div className="grid grid-cols-[72px_1fr] items-center gap-2 text-[11px]"><span className="text-ink-3">{label}</span><div className="relative h-5 rounded bg-surface-3">{children}</div></div>
  );
  return (
    <div className="grid gap-1" data-testid="timeline">
      {lane("Voice", <div className="absolute inset-y-1 rounded" title="voiceover" style={{ left: x(talk[0]), width: `calc(${x(talk[1])} - ${x(talk[0])})`, background: "var(--accent)", opacity: 0.45 }} />)}
      {lane("Colour", moods.map((m, i) => {
        const end = moods[i + 1]?.t ?? duration;
        return <div key={i} className="absolute inset-y-0 rounded" title={m.mood} style={{ left: x(m.t), width: `calc(${x(end)} - ${x(m.t)})`, background: MOOD_COLOR[m.mood] ?? "#999", opacity: 0.75 }} />;
      }))}
      {lane("Gestures", (hero.gestures ?? []).map((g: any, i: number) => (
        <div key={i} className="absolute inset-y-0.5 truncate rounded bg-surface px-1 leading-4 shadow" title={g.gesture}
          style={{ left: x(g.t), width: `calc(${x(g.t + (g.dur ?? 1.8))} - ${x(g.t)})` }}>{g.gesture}</div>)))}
      {lane("Face", (hero.face ?? []).map((f: any, i: number) => <div key={i} className="absolute top-0 truncate px-0.5 leading-5" style={{ left: x(f.t) }}>│{f.expr}</div>))}
      {lane("Props", (scene.props ?? []).map((p: any, i: number) => <div key={i} className="absolute top-0 truncate leading-5" style={{ left: x(p.t_in ?? 0) }}>◆{String(p.type).replace("custom:", "✦")}</div>))}
      {lane("Camera", (scene.camera ?? []).map((k: any, i: number) => (
        <div key={i} className="absolute top-0 truncate leading-5" style={{ left: x(k.t) }}>▍{typeof k.shot === "string" ? k.shot : k.shot?.type ?? "custom"}</div>)))}
      <div className="grid grid-cols-[72px_1fr] items-center gap-2 text-[11px]"><span className="text-ink-3">Preview at</span>
        <input type="range" min={0} max={duration} step={0.1} value={t} onChange={(e) => setT(Number(e.target.value))} data-testid="preview-time" /></div>
    </div>
  );
}

export default function SceneEditor() {
  const { slug, snap } = useProject();
  const [params] = useSearchParams();
  const n = Number(params.get("clip") ?? 1);
  const [scene, setScene] = useState<any>(null);
  const [meta, setMeta] = useState<any>(null);
  const [cat, setCat] = useState<any>(null);
  const [tab, setTab] = useState<"form" | "json">("form");
  const [json, setJson] = useState("");
  const [t, setT] = useState(2);
  const [preview, setPreview] = useState<any>(null);
  const [check, setCheck] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const duration = scene?.duration ?? 10;

  const load = async () => {
    setErr(null);
    try {
      const [s, c] = await Promise.all([api.get<any>(`/projects/${slug}/scenes/${n}`), api.get<any>(`/projects/${slug}/threejs/catalog`)]);
      setScene(s.scene); setMeta(s); setCat(c); setJson(JSON.stringify(s.scene, null, 2)); setT(Math.min(2.5, s.scene.duration ?? 10));
    } catch (e: any) { setErr(e.message); }
  };
  useEffect(() => { if (slug) load(); }, [slug, n]); // eslint-disable-line react-hooks/exhaustive-deps

  const update = (fn: (s: any) => void) => setScene((prev: any) => { const next = structuredClone(prev); fn(next); setJson(JSON.stringify(next, null, 2)); return next; });
  const hero = scene?.actors?.[0];
  const other = scene?.actors?.[1];
  const ids = useMemo(() => ["camera", ...(scene?.actors ?? []).map((a: any) => a.id), ...(scene?.props ?? []).map((p: any, i: number) => p.id ?? `p${i + 1}`)], [scene]);
  const propTypes = useMemo(() => [...(cat?.props ?? []), ...(cat?.assets ?? []).map((a: any) => `custom:${a.key}`)], [cat]);
  const clips = cat?.clips ?? [];

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label); setErr(null); setMsg(null);
    try { await fn(); } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };
  const current = () => (tab === "json" ? JSON.parse(json) : scene);
  const doCheck = () => run("check", async () => { const r = await api.post<any>(`/projects/${slug}/scenes/${n}/check`, { scene: current() }); setCheck(r); setMsg(r.errors.length ? null : `OK${r.fixes.length ? ` after ${r.fixes.length} repair(s)` : ": nothing to fix"}`); });
  const doPreview = () => run("preview", async () => setPreview(await api.post<any>(`/projects/${slug}/scenes/${n}/preview`, { scene: current(), t })));
  const doSave = (rerender: boolean) => run(rerender ? "render" : "save", async () => {
    const r = await api.put<any>(`/projects/${slug}/scenes/${n}`, { scene: current() });
    setScene(r.scene); setJson(JSON.stringify(r.scene, null, 2)); setCheck({ fixes: r.fixes, errors: [] });
    if (rerender) { await api.post(`/projects/${slug}/clips/${n}/regenerate`); setMsg("saved; re-rendering this clip (see the Render page)"); }
    else setMsg("saved as your edit: the AI planner will not overwrite it");
  });

  if (!scene) return err ? <ErrorBox>{err}</ErrorBox> : <div className="muted">Loading scene…</div>;
  const count = Math.floor((snap?.project.data.duration ?? 60) / 10);
  const moods = Array.isArray(scene.mood) ? scene.mood : [{ t: 0, mood: scene.mood ?? "neutral" }];
  return (
    <div className="grid gap-4" data-testid="scene-editor">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="h1">Scene editor · clip {n}</h1>
        <span className="flex flex-wrap gap-1">
          {Array.from({ length: count }, (_, k) => <Link key={k} className={`btn !py-0.5 text-xs ${k + 1 === n ? "ring-2 ring-accent" : ""}`} to={`/p/${slug}/scene?clip=${k + 1}`}>{k + 1}</Link>)}
          <Link className="btn !py-0.5 text-xs" to={`/p/${slug}/render`}>← Render</Link>
        </span>
      </div>
      <Note>“{meta?.vo}” · {meta?.source === "draft" ? "no plan yet: this is the keyword draft" : `plan by ${scene._planned_by ?? "you"}`}{scene._notes ? ` · “${scene._notes}”` : ""}</Note>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="grid gap-4">
          <Section title="Timeline"><Timeline scene={scene} duration={duration} talk={meta?.talk ?? [0.4, 6]} t={t} setT={setT} /></Section>
          <div className="flex gap-1">
            {(["form", "json"] as const).map((k) => <button key={k} className={`btn !py-0.5 text-xs ${tab === k ? "ring-2 ring-accent" : ""}`} onClick={() => { if (k === "form" && tab === "json") { try { setScene(JSON.parse(json)); } catch { setErr("the JSON does not parse"); return; } } setTab(k); }}>{k === "form" ? "Editor" : "JSON"}</button>)}
          </div>
          {tab === "json" ? (
            <textarea className="input min-h-[480px] font-mono text-xs" value={json} onChange={(e) => setJson(e.target.value)} data-testid="scene-json" />
          ) : (
            <>
              <Section title="Look">
                <div className="flex flex-wrap gap-2">
                  <label className="text-xs">Style<select className="input !py-1" value={scene.style} onChange={(e) => update((s) => { s.style = e.target.value; })}>{cat?.styles.map((x: string) => <option key={x}>{x}</option>)}</select></label>
                  <label className="text-xs">Theme<select className="input !py-1" value={scene.theme ?? "dark"} onChange={(e) => update((s) => { s.theme = e.target.value; })}><option>dark</option><option>light</option></select></label>
                  <label className="text-xs">Fade in<select className="input !py-1" value={scene.transition?.in ?? "none"} onChange={(e) => update((s) => { s.transition = { ...s.transition, in: e.target.value }; })}>{cat?.transitions.map((x: string) => <option key={x}>{x}</option>)}</select></label>
                  <label className="text-xs">Fade out<select className="input !py-1" value={scene.transition?.out ?? "none"} onChange={(e) => update((s) => { s.transition = { ...s.transition, out: e.target.value }; })}>{cat?.transitions.map((x: string) => <option key={x}>{x}</option>)}</select></label>
                </div>
                <div className="mt-2 text-xs font-semibold">Colour (mood) over time</div>
                <Rows testid="rows-mood" rows={moods} onChange={(r) => update((s) => { s.mood = r; })} make={() => ({ t: Math.round(t * 10) / 10, mood: "neutral" })}
                  cols={[{ key: "t", label: "at (s)", type: "num" }, { key: "mood", label: "mood", type: "select", options: cat?.moods }]} />
              </Section>
              {[hero, other].filter(Boolean).map((a: any, ai: number) => (
                <Section key={ai} title={ai === 0 ? "Main character" : "Second character"} right={ai === 1 ? <button className="btn !py-0.5 text-xs" onClick={() => update((s) => { s.actors = s.actors.slice(0, 1); })}>remove</button> : undefined}>
                  <div className="flex flex-wrap gap-2">
                    <label className="text-xs">Hat<select className="input !py-1" value={a.hat ?? "none"} onChange={(e) => update((s) => { s.actors[ai].hat = e.target.value; })}>{cat?.hats.map((x: string) => <option key={x}>{x}</option>)}</select></label>
                    <label className="flex items-end gap-1 text-xs"><input type="checkbox" checked={!!a.path?.length} onChange={(e) => update((s) => { if (e.target.checked) s.actors[ai].path = [{ t: 0, pos: [-1.6, 0, 0.3] }, { t: 1.7, pos: a.position ?? [0, 0, 0] }]; else delete s.actors[ai].path; })} />walks in</label>
                  </div>
                  <div className="mt-2 text-xs font-semibold">Gestures</div>
                  <Rows testid={`rows-gestures-${ai}`} rows={a.gestures ?? []} onChange={(r) => update((s) => { s.actors[ai].gestures = r; })} make={() => ({ t: Math.round(t * 10) / 10, gesture: "explain", dur: 1.8 })}
                    cols={[{ key: "t", label: "at (s)", type: "num" }, { key: "gesture", label: "gesture", type: "select", options: cat?.gestures },
                      { key: "side", label: "hand", type: "select", options: ["L", "R", "both"], w: "5rem" }, { key: "target", label: "toward", type: "select", options: ids, w: "7rem" },
                      { key: "dur", label: "for (s)", type: "num" }]} />
                  <div className="mt-2 text-xs font-semibold">Face</div>
                  <Rows rows={a.face ?? []} onChange={(r) => update((s) => { s.actors[ai].face = r; })} make={() => ({ t: Math.round(t * 10) / 10, expr: "happy" })}
                    cols={[{ key: "t", label: "at (s)", type: "num" }, { key: "expr", label: "expression", type: "select", options: cat?.expressions }]} />
                  <div className="mt-2 text-xs font-semibold">Body moves</div>
                  <Rows rows={a.anim ?? []} onChange={(r) => update((s) => { s.actors[ai].anim = r; })} make={() => ({ t: Math.round(t * 10) / 10, clip: "Idle" })}
                    cols={[{ key: "t", label: "at (s)", type: "num" }, { key: "clip", label: "move", type: "select", options: clips }]} />
                  <div className="mt-2 text-xs font-semibold">Looks at</div>
                  <Rows rows={a.look ?? []} onChange={(r) => update((s) => { s.actors[ai].look = r; })} make={() => ({ t: Math.round(t * 10) / 10, at: "camera" })}
                    cols={[{ key: "t", label: "at (s)", type: "num" }, { key: "at", label: "look at", type: "select", options: [...ids, "left", "right", "up", "down"] }]} />
                </Section>
              ))}
              {!other && <button className="btn w-fit text-xs" onClick={() => update((s) => {
                s.actors[0].position = [-0.42, 0, 0];
                s.actors.push({ id: "other", position: [0.45, 0, -0.1], facing: -0.7, anim: [{ t: 0, clip: "Idle" }], face: [{ t: 0, expr: "neutral" }] });
                s.camera = [{ t: 0, shot: { type: "two_shot", target: ["hero", "other"] } }];
              })}>+ Second character</button>}
              <Section title="Props">
                {(scene.props ?? []).map((p: any, i: number) => (
                  <div key={i} className="mb-1 flex flex-wrap items-end gap-1 text-[11px]">
                    <label className="w-40 text-ink-3">prop<select className="input !py-1 text-xs" value={p.type} onChange={(e) => update((s) => { s.props[i].type = e.target.value; })}>{propTypes.map((x: string) => <option key={x} value={x}>{x.startsWith("custom:") ? `✦ ${x.slice(7)}` : x}</option>)}</select></label>
                    <label className="w-44 text-ink-3">where<select className="input !py-1 text-xs" value={placeOf(p)} onChange={(e) => update((s) => { const pl = PLACES[e.target.value]; if (!pl) return; delete s.props[i].pos; delete s.props[i].hold; Object.assign(s.props[i], structuredClone(pl)); })}>{[...Object.keys(PLACES), "custom"].map((x) => <option key={x}>{x}</option>)}</select></label>
                    {p.pos && ["x", "y", "z"].map((ax, j) => <label key={ax} className="w-14 text-ink-3">{ax}<input className="input !py-1 text-xs" type="number" step={0.05} value={p.pos[j]} onChange={(e) => update((s) => { s.props[i].pos[j] = Number(e.target.value); })} /></label>)}
                    <label className="w-16 text-ink-3">at (s)<input className="input !py-1 text-xs" type="number" step={0.1} value={p.t_in ?? 0} onChange={(e) => update((s) => { s.props[i].t_in = Number(e.target.value); })} /></label>
                    <label className="w-20 text-ink-3">enters<select className="input !py-1 text-xs" value={p.enter ?? "pop"} onChange={(e) => update((s) => { s.props[i].enter = e.target.value; })}>{["pop", "drop", "grow", "spin", "none"].map((x) => <option key={x}>{x}</option>)}</select></label>
                    <label className="w-20 text-ink-3">then<select className="input !py-1 text-xs" value={p.idle ?? "bob"} onChange={(e) => update((s) => { s.props[i].idle = e.target.value; })}>{["bob", "spin", "pulse", "shake", "none"].map((x) => <option key={x}>{x}</option>)}</select></label>
                    <label className="w-14 text-ink-3">size<input className="input !py-1 text-xs" type="number" step={0.1} value={p.scale ?? 1} onChange={(e) => update((s) => { s.props[i].scale = Number(e.target.value); })} /></label>
                    <button className="btn !px-2 !py-1 text-xs" onClick={() => update((s) => { s.props.splice(i, 1); })}>✕</button>
                  </div>
                ))}
                <button className="btn !py-0.5 text-xs" onClick={() => update((s) => { s.props = [...(s.props ?? []), { id: `p${(s.props?.length ?? 0) + 1}`, type: "bulb", pos: [0.55, 1.25, 0.1], t_in: Math.round(t * 10) / 10, enter: "pop", idle: "bob" }]; })}>+ add prop</button>
                <p className="mt-1 text-[11px] text-ink-3">✦ = drawn by AI (Render page → Props drawn by AI to draw a new one).</p>
              </Section>
              <Section title="Text on screen">
                <div className="text-xs font-semibold">Badges (numbers must be said in the voiceover)</div>
                <Rows rows={scene.badges ?? []} onChange={(r) => update((s) => { s.badges = r; })} make={() => ({ text: "", t_in: Math.round(t * 10) / 10, pos: [0, 2.15, -0.4], size: 1 })}
                  cols={[{ key: "text", label: "text", type: "text", w: "16rem" }, { key: "t_in", label: "at (s)", type: "num" }, { key: "size", label: "size", type: "num" }]} />
                <div className="mt-2 text-xs font-semibold">Panels</div>
                {(scene.panels ?? []).map((p: any, i: number) => (
                  <div key={i} className="mb-1 flex flex-wrap items-start gap-1 text-[11px]">
                    <label className="w-24 text-ink-3">kind<select className="input !py-1 text-xs" value={p.kind ?? "note"} onChange={(e) => update((s) => { s.panels[i].kind = e.target.value; })}><option>note</option><option>code</option></select></label>
                    <label className="w-48 text-ink-3">title<input className="input !py-1 text-xs" value={p.title ?? ""} onChange={(e) => update((s) => { s.panels[i].title = e.target.value; })} /></label>
                    <label className="w-64 text-ink-3">lines<textarea className="input !py-1 text-xs" rows={3} value={(p.lines ?? []).join("\n")} onChange={(e) => update((s) => { s.panels[i].lines = e.target.value.split("\n").slice(0, 5); })} /></label>
                    <label className="w-16 text-ink-3">at (s)<input className="input !py-1 text-xs" type="number" step={0.1} value={p.t_in ?? 0} onChange={(e) => update((s) => { s.panels[i].t_in = Number(e.target.value); })} /></label>
                    <button className="btn !px-2 !py-1 text-xs" onClick={() => update((s) => { s.panels.splice(i, 1); })}>✕</button>
                  </div>
                ))}
                <button className="btn !py-0.5 text-xs" onClick={() => update((s) => { s.panels = [...(s.panels ?? []), { kind: "note", title: "", lines: [""], t_in: Math.round(t * 10) / 10, pos: [0, 2.2, -1], w: 1.4 }]; })}>+ add panel</button>
              </Section>
              <Section title="Camera">
                <Rows testid="rows-camera" rows={(scene.camera ?? []).map((k: any) => ({ t: k.t, type: typeof k.shot === "string" ? k.shot : k.shot?.type, target: Array.isArray(k.shot?.target) ? undefined : k.shot?.target, side: k.shot?.side, zoom: k.shot?.zoom, ease: k.ease }))}
                  onChange={(r) => update((s) => { s.camera = r.map((k: any) => ({ t: k.t ?? 0, shot: { type: k.type ?? "medium", ...(k.target ? { target: k.target } : {}), ...(k.side !== undefined ? { side: k.side } : {}), ...(k.zoom !== undefined ? { zoom: k.zoom } : {}) }, ...(k.ease ? { ease: k.ease } : {}) })); })}
                  make={() => ({ t: Math.round(t * 10) / 10, type: "medium", target: "hero" })}
                  cols={[{ key: "t", label: "at (s)", type: "num" }, { key: "type", label: "shot", type: "select", options: cat?.shots }, { key: "target", label: "on", type: "select", options: (scene.actors ?? []).map((a: any) => a.id), w: "6rem" },
                    { key: "side", label: "side", type: "num" }, { key: "zoom", label: "zoom", type: "num" }, { key: "ease", label: "ease", type: "select", options: ["inOutCubic", "inOutSine", "outCubic", "linear"], w: "7rem" }]} />
              </Section>
            </>
          )}
        </div>
        <div className="grid h-fit gap-3 lg:sticky lg:top-4">
          <Section title="Preview">
            {preview ? <img className="w-full rounded-lg bg-black" src={`${fileUrl(slug!, preview.image)}?v=${preview.at}`} alt="preview frame" data-testid="preview-image" />
              : <div className="grid aspect-[9/16] w-full place-items-center rounded-lg bg-surface-3 text-xs text-ink-3">no preview yet</div>}
            <div className="mt-2 grid gap-1">
              <button className="btn justify-center" disabled={!!busy} onClick={doPreview} data-testid="do-preview">{busy === "preview" ? "Rendering…" : `▶ Preview frame at ${t.toFixed(1)} s`}</button>
              <button className="btn justify-center" disabled={!!busy} onClick={doCheck} data-testid="do-check">✓ Check</button>
              <button className="btn-primary justify-center" disabled={!!busy} onClick={() => doSave(false)} data-testid="do-save">Save</button>
              <button className="btn justify-center" disabled={!!busy} onClick={() => doSave(true)} data-testid="do-save-render">Save &amp; re-render clip</button>
              <button className="btn justify-center text-xs" disabled={!!busy} onClick={load}>↺ Discard changes</button>
            </div>
            {msg && <p className="mt-2 text-xs" data-testid="editor-msg">✓ {msg}</p>}
            {check?.fixes?.length > 0 && <ul className="mt-2 list-disc pl-4 text-[11px]" style={{ color: "var(--serious)" }}>{check.fixes.map((f: string, i: number) => <li key={i}>{f}</li>)}</ul>}
            {check?.errors?.length > 0 && <ErrorBox>{check.errors.join("; ")}</ErrorBox>}
            {err && <ErrorBox>{err}</ErrorBox>}
          </Section>
        </div>
      </div>
    </div>
  );
}
