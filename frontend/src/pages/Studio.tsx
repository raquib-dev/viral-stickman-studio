import { useEffect, useState } from "react";
import { BeatTimeline, Bars } from "../components/charts";
import { GatePanel } from "../components/GatePanel";
import { RunStageButton } from "../components/Pipeline";
import { ScriptGaps } from "../components/ScriptGaps";
import { CopyButton, Empty, ErrorBox, FixtureBadge, Note, Section } from "../components/ui";
import { api } from "../lib/api";
import { useProject, useProjectFile } from "../lib/useProject";

export default function Studio() {
  return (
    <div className="grid gap-5">
      <h1 className="h1">5-6 · Studio</h1>
      <Hooks />
      <Script />
      <PhaseA />
      <PhaseB />
    </div>
  );
}

function Hooks() {
  const { snap } = useProject();
  const [data] = useProjectFile<any>("script/hooks.json");
  const [choice, setChoice] = useState<string | null>(null);
  const gate = snap?.gates.find((g) => g.name === "hook");
  const pending = gate?.status === "pending";
  return (
    <Section title="Hooks" right={<RunStageButton stage="hooks" />} id="hooks">
      {!data ? <Empty>No hooks yet (needs an approved topic).</Empty> : (
        <>
          <p className="mb-3 text-sm text-ink-2">Topic: <b>{data.topic.title}</b>. Ranked by the <b>{data.panel === "ig" ? "ig-reel" : data.panel === "yt" ? "yt-script" : "mean of both"}</b> hookscore panel; hooks over 3 s or with an ig dealbreaker rank lower. {data.note}</p>
          <GatePanel name="hook" title="Pick a hook" choice={choice} setChoice={setChoice} />
          <div className="mt-3 grid gap-3 lg:grid-cols-2" data-testid="hook-cards">
            {data.hooks.map((h: any) => {
              const selected = (choice ?? gate?.choice ?? gate?.payload?.default_choice) === h.id;
              return (
                <button key={h.id} type="button" disabled={!pending} onClick={() => setChoice(h.id)} data-testid={`hook-${h.id}`}
                  className={`card text-left ${selected ? "ring-2 ring-accent" : ""} ${pending ? "hover:bg-surface-2" : "cursor-default"}`}>
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-xs text-ink-3">#{h.rank} · score {h.rank_score} · ~{h.seconds}s {selected && "· ✓ selected"}</span>
                    {h._fixture !== false && h.why === "dry-run fixture" && <FixtureBadge />}
                  </div>
                  <dl className="mt-1 grid grid-cols-[56px_1fr] gap-x-2 gap-y-1 text-sm">
                    <dt className="label !mb-0">Say</dt><dd className="font-semibold text-ink">“{h.say}”</dd>
                    <dt className="label !mb-0">Write</dt><dd>{h.write}</dd>
                    <dt className="label !mb-0">Show</dt><dd className="text-ink-2">{h.show}</dd>
                    <dt className="label !mb-0">Align</dt><dd className="text-ink-2">{h.align}</dd>
                  </dl>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    <div><div className="label">yt-script panel · {h.yt?.verdict}</div>
                      <Bars max={100} format={(v) => v.toFixed(0)} items={Object.entries(h.yt?.properties ?? {}).map(([k, v]) => ({ label: k.toLowerCase(), value: v as number }))} />
                      <div className="mt-1 text-[11px] text-ink-3">{h.formula_yt}</div></div>
                    <div><div className="label">ig-reel panel · {h.ig?.score} {h.ig?.verdict}</div>
                      <Bars max={100} format={(v) => v.toFixed(0)} items={Object.entries(h.ig?.checks ?? {}).map(([k, v]: any) => ({ label: k.toLowerCase(), value: v.score, hint: v.detail }))} />
                      <div className="mt-1 text-[11px] text-ink-3">{h.formula_ig}</div></div>
                  </div>
                  {h.flags.length > 0 && <ul className="mt-2 space-y-0.5 text-xs">{h.flags.map((f: string) => <li key={f}><span style={{ color: "var(--serious)" }}>▲</span> {f}</li>)}</ul>}
                </button>
              );
            })}
          </div>
        </>
      )}
    </Section>
  );
}

function DialogueScript({ s }: { s: any }) {
  const names = s.cast ?? { a: "a", b: "b" };
  const marks = (i: number) => [i + 1 === s.turn && "turn", i + 1 === s.button && "button",
    s.callback && (i === s.callback[0] || i === s.callback[1]) && "callback"].filter(Boolean) as string[];
  return (
    <Section title="Dialogue script (two characters, a cut per line)" right={<RunStageButton stage="script" />} id="script">
      <div className="grid gap-4" data-testid="dialogue-script">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <b>{s.title}</b>{s._fixture && <FixtureBadge />}
          <span className="chip">{s.lines.length} lines · {s.clips.length} clips</span>
        </div>
        {s.flags.length === 0
          ? <Note>✓ The format's rules hold: short lines, ping-pong, pause beats, in-story numbers, a callback, a turn in the second half, an ending that loops, a lowercase title ending in a question, and it fits {s.clips.length} clips of 10 s.</Note>
          : <div className="rounded-lg border px-3 py-2 text-sm" style={{ borderColor: "var(--serious)" }} data-testid="script-flags">
            <b>Flags</b> (re-run Script to fix):<ul className="mt-1 list-disc pl-5">{s.flags.map((f: string) => <li key={f}>{f}</li>)}</ul></div>}
        <ScriptGaps />
        {s.punch_up?.applied && <div className="rounded-lg border border-line px-3 py-2 text-sm" data-testid="punch-up">
          <b>Punch-up pass</b> (joke-engineering): {Object.keys(s.punch_up.before ?? {}).length} line(s) sharpened
          {s.punch_up.notes?.length > 0 && <ul className="mt-1 list-disc pl-5 text-xs text-ink-2">{s.punch_up.notes.map((n: any) =>
            <li key={n.line}>line {n.line} · {n.state}: {n.change}{s.punch_up.before?.[n.line - 1] ? <span className="text-ink-3"> (was “{s.punch_up.before[n.line - 1]}”)</span> : null}</li>)}</ul>}
        </div>}
        {s.clips.map((c: any) => (
          <div key={c.index} className="card-2">
            <div className="text-xs text-ink-3">Clip {c.index + 1} · {c.index * 10}-{c.index * 10 + 10}s</div>
            <div className="mt-1 grid gap-0.5">{c.lines.map((ln: any) => (
              <div key={ln.i} className="flex flex-wrap items-baseline gap-2 text-sm">
                <span className="w-20 shrink-0 font-semibold" style={{ color: ln.speaker === "a" ? "var(--accent)" : "var(--good)" }}>{names[ln.speaker]}</span>
                <span className="text-ink">{String(ln.text).split(/(\[[^\]]+\])/).map((part: string, j: number) =>
                  part.startsWith("[") ? <span key={j} className="text-xs italic text-ink-3">{part} </span> : <span key={j}>{part}</span>)}</span>
                {ln.timing && ln.timing !== "normal" && <span className="chip !py-0 text-[10px]" title={ln.timing === "beat" ? "a sharp look before answering" : "answers straight back"}>{ln.timing}</span>}
                {marks(ln.i).map((m) => <span key={m} className="chip !py-0 text-[10px]">{m}</span>)}
              </div>))}</div>
          </div>))}
        {s.claims_to_source?.length > 0 && <Note tone="warn"><b>Check before publishing:</b><ul className="list-disc pl-5">{s.claims_to_source.map((c: string) => <li key={c}>{c}</li>)}</ul></Note>}
      </div>
    </Section>
  );
}

function Script() {
  const [s] = useProjectFile<any>("script/script.json");
  const [beats] = useProjectFile<any>("script/beats.json");
  const [human] = useProjectFile<any>("script/human.json");
  if (s?.mode === "dialogue") return <DialogueScript s={s} />;
  return (
    <Section title="Script (5-stage arc, beats placed by the niche profile)" right={<RunStageButton stage="script" />} id="script">
      {!s ? <Empty>No script yet (needs an approved hook).</Empty> : (
        <div className="grid gap-4">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <b>{s.title}</b>{s._fixture && <FixtureBadge />}
            <span className="chip">{beats?.total_words} words · ~{beats?.total_seconds?.toFixed(1)}s at {s.wpm} wpm</span>
            {human && <span className="chip">ig-human {human.detect_before?.human_score} → {human.detect_after?.human_score} ({human.detect_after?.verdict})</span>}
          </div>
          {s.flags.length === 0
            ? <Note>✓ beats.py and the app's checks raise no flags (hook within 3 s, no beat over 4 s, concrete every 3 beats, loop, length on target, one ask, ≤25 words per clip).</Note>
            : <div className="rounded-lg border px-3 py-2 text-sm" style={{ borderColor: "var(--serious)" }} data-testid="script-flags">
              <b>Flags to fix</b> (re-run Script, or edit the hook choice):<ul className="mt-1 list-disc pl-5">{s.flags.map((f: string) => <li key={f}>{f}</li>)}</ul></div>}
          <ScriptGaps />
          <div className="grid gap-2">
            {s.clips.map((c: any) => (
              <div key={c.index} className="card-2">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-3">
                  <span>Clip {c.index + 1} · {c.index * 10}-{c.index * 10 + 10}s · {c.stage}</span>
                  <span>{c.vo.split(/\s+/).length} words{c.beats?.length ? ` · planned: ${c.beats.join(", ")}` : ""}</span>
                </div>
                <p className="mt-1 text-sm text-ink">{c.vo}</p>
              </div>
            ))}
          </div>
          <div><div className="label">Planned beats (profile when n ≥ 5 videos, else blueprint defaults)</div>
            <BeatTimeline marks={s.plan} duration={s.duration} clips={s.clips.length} /></div>
          {beats && (
            <details><summary className="cursor-pointer text-sm font-semibold">beats.py beat sheet</summary>
              <table className="table mt-2"><thead><tr><th>#</th><th>Start</th><th>Dur</th><th>Label</th><th>Line</th></tr></thead>
                <tbody>{beats.beats.map((b: any) => <tr key={b.n}><td>{b.n}</td><td>{b.start.toFixed(1)}s</td><td>{b.dur.toFixed(1)}s</td><td>{b.label}</td><td>{b.text}{b.flags.length ? ` ▲ ${b.flags.join("; ")}` : ""}</td></tr>)}</tbody></table>
              <ul className="mt-2 list-disc pl-5 text-xs text-ink-2">{beats.notes.map((n: string) => <li key={n}>{n}</li>)}</ul>
            </details>
          )}
          {s.claims_to_source?.length > 0 && <Note tone="warn"><b>Claims to verify before publishing:</b><ul className="list-disc pl-5">{s.claims_to_source.map((c: string) => <li key={c}>{c}</li>)}</ul></Note>}
          {s.mistake && <Note>Deliberate mistake (intentional, visual only): {s.mistake.description}</Note>}
        </div>
      )}
    </Section>
  );
}

function PhaseA() {
  const { slug, snap, refresh } = useProject();
  const [a] = useProjectFile<any>("direction/phase-a.json");
  const [ann] = useProjectFile<any[]>("direction/phase-a.annotations.json");
  const [md, , reloadMd] = useProjectFile<string>("direction/phase-a.md");
  const [edit, setEdit] = useState(false);
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [rev, setRev] = useState("");
  useEffect(() => { if (md) setText(md); }, [md]);
  const gate = snap?.gates.find((g) => g.name === "phase_a");
  return (
    <Section title="Director Phase A (directing-stickman-videos)" right={<RunStageButton stage="direction_a" label="Re-run Phase A" />} id="phase-a">
      {!a ? <Empty>No Phase A yet.</Empty> : (
        <div className="grid gap-4">
          <div className="flex flex-wrap gap-2 text-sm">{a._fixture && <FixtureBadge />}
            <span className="chip">narrator: {a.voice_profile}</span>
            {a.palette?.map((p: any) => <span key={p.color} className="chip">{p.color} = {p.meaning}</span>)}
            {a.hook_card && <span className="chip">hook card: “{a.hook_card}”</span>}</div>
          {ann && <div><div className="label">Blueprint annotations on the timeline (re-hook here, pattern interrupt here…)</div>
            <BeatTimeline marks={ann.map((x) => ({ ...x, note: `${x.how_to_stage ?? ""}`.slice(0, 160) }))} duration={(a.rows?.length ?? 6) * 10} clips={a.rows?.length} /></div>}
          <div className="overflow-x-auto">
            <table className="table" data-testid="phase-a-table"><thead><tr><th>Time</th><th>Purpose</th><th>Stick-figure scene</th><th>Motion / camera / blueprint</th><th>VO</th><th>BGM / SFX</th></tr></thead>
              <tbody>{a.rows.map((r: any) => <tr key={r.clip}><td className="whitespace-nowrap">{r.time}</td><td>{r.purpose}</td><td>{r.scene}</td><td>{r.motion}</td><td>{r.vo}</td><td className="text-ink-2">{r.bgm}</td></tr>)}</tbody></table>
          </div>
          <GatePanel name="phase_a" title="Approve the director's Phase A" editHint="Edit the proposal text below before approving; the approval is tied to the exact text you approve.">
            <p className="text-sm text-ink-2">The skill's own rule: Phase B prompts are only written after you approve the current Phase A. Any change to ratio, duration or style re-opens this gate.</p>
          </GatePanel>
          {gate?.status === "rejected" && (
            <div className="card-2"><label className="label">Revision note for the director</label>
              <div className="flex gap-2"><input className="input" value={rev || gate.note || ""} onChange={(e) => setRev(e.target.value)} />
                <button className="btn-primary" onClick={async () => { await api.post(`/projects/${slug}/stages/direction_a/run`, { params: { revision_note: rev || gate.note } }); }}>Revise Phase A</button></div>
              <p className="mt-1 text-xs text-ink-3">Then run the pipeline again; it stops at this gate for your approval.</p></div>
          )}
          <div>
            <button className="btn" onClick={() => setEdit(!edit)}>{edit ? "Close editor" : "✎ Edit Phase A text"}</button>
            {edit && (
              <div className="mt-2">
                <textarea className="input h-72 font-mono text-xs" value={text} onChange={(e) => setText(e.target.value)} data-testid="phase-a-editor" />
                <button className="btn-primary mt-2" onClick={async () => {
                  setErr(null);
                  try { await api.put(`/projects/${slug}/phase-a`, { markdown: text }); reloadMd(); await refresh(); setEdit(false); }
                  catch (e: any) { setErr(e.message); }
                }}>Save edits</button>
                {err && <ErrorBox>{err}</ErrorBox>}
              </div>
            )}
          </div>
        </div>
      )}
    </Section>
  );
}

function PhaseB() {
  const [b] = useProjectFile<any>("direction/phase-b.json");
  return (
    <Section title="Phase B: Omni Flash prompts" right={<RunStageButton stage="direction_b" label="Re-run Phase B" />} id="phase-b">
      {!b ? <Empty>No prompts yet (needs Phase A approval).</Empty> : (
        <div className="grid gap-3">
          {b.checks?.length ? <ErrorBox>Checks failed: {b.checks.join("; ")}</ErrorBox>
            : <Note>✓ {b.prompts.length} prompts · the frozen character anchor and the complete voice block appear verbatim in every clip · no technical colour notation.</Note>}
          <details><summary className="cursor-pointer text-sm font-semibold">Frozen character anchor and voice block</summary>
            <pre className="code mt-2">{b.character_anchor}</pre><pre className="code mt-2">{b.voice_block}</pre></details>
          {b.prompts.map((p: any) => (
            <details key={p.clip} className="card-2" data-testid={`prompt-${p.clip}`}>
              <summary className="flex cursor-pointer items-center justify-between text-sm font-semibold">Clip {p.clip}<CopyButton text={p.text} /></summary>
              <pre className="code mt-2">{p.text}</pre>
            </details>
          ))}
          <p className="text-xs text-ink-2"><b>Stitching:</b> {b.stitching_guide} <b>Audio:</b> {b.audio_note}</p>
        </div>
      )}
    </Section>
  );
}
