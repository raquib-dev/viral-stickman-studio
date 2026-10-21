import { useState } from "react";
import { Tabs } from "./ui";

/* Charts follow the dataviz method: single-hue sequential ramp for magnitude (heatmap), identity by row
   label instead of colour (timelines), thin single-series bars with direct labels, a hover tooltip on every
   mark, and a table view for every chart. Text always uses ink tokens, never the series colour. */

export const BEAT_LABEL: Record<string, string> = {
  "hook-placement": "Hook", "stakes-line": "Stakes line", "rehook-cadence": "Re-hook", "pattern-interrupt-cadence": "Pattern interrupt",
  "callout-placement": "Callout", "deliberate-mistake-placement": "Deliberate mistake", "payoff-timing": "Payoff",
  "cta-placement": "CTA", "loop-ending": "Loop ending", "no-intro": "Intro (violation)", "end-screen-hold": "End-screen hold",
};
const lbl = (t: string) => BEAT_LABEL[t] ?? t;

function Tip({ x, y, children }: { x: number; y: number; children: React.ReactNode }) {
  return (
    <div className="pointer-events-none fixed z-50 max-w-xs rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs text-ink shadow-lg"
      style={{ left: x + 12, top: y + 12 }}>{children}</div>
  );
}

// ---- heatmap ---------------------------------------------------------------------------------

const STEPS = ["--seq-0", "--seq-1", "--seq-2", "--seq-3", "--seq-4", "--seq-5", "--seq-6"];
// 0 = neutral (no videos); otherwise 6 equal bins of the share of videos
const step = (v: number) => STEPS[v <= 0 ? 0 : Math.min(6, 1 + Math.floor(v * 6))];

export function Heatmap({ rows, binPct }: { rows: { type: string; values: number[] }[]; binPct: number }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const [tip, setTip] = useState<{ x: number; y: number; text: React.ReactNode } | null>(null);
  const shown = rows.filter((r) => r.values.some((v) => v > 0));
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-xs text-ink-3">Share of outlier videos (weighted by outlier multiple) with this beat in each 5% slice of runtime</span>
        <Tabs tabs={[{ id: "chart", label: "Chart" }, { id: "table", label: "Table" }]} value={view} onChange={setView} />
      </div>
      {view === "chart" ? (
        <div className="overflow-x-auto" data-testid="heatmap">
          <div className="grid min-w-[640px] items-center gap-x-2 gap-y-[2px]" style={{ gridTemplateColumns: "130px 1fr" }}>
            {shown.map((r) => (
              <div key={r.type} className="contents">
                <div className="truncate text-xs text-ink-2">{lbl(r.type)}</div>
                <div className="grid gap-[2px]" style={{ gridTemplateColumns: `repeat(${r.values.length}, 1fr)` }}>
                  {r.values.map((v, i) => (
                    <div key={i} className="h-6 rounded-[3px]" style={{ background: `var(${step(v)})` }}
                      onMouseMove={(e) => setTip({ x: e.clientX, y: e.clientY, text: <><b>{lbl(r.type)}</b><br />{Math.round(i * binPct)}-{Math.round((i + 1) * binPct)}% of runtime<br />{Math.round(v * 100)}% of videos</> })}
                      onMouseLeave={() => setTip(null)} aria-label={`${lbl(r.type)} ${Math.round(i * binPct)}%: ${Math.round(v * 100)}%`} />
                  ))}
                </div>
              </div>
            ))}
            <div />
            <div className="flex justify-between pt-1 text-[11px] text-ink-3">
              {[0, 25, 50, 75, 100].map((t) => <span key={t}>{t}%</span>)}
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2 text-[11px] text-ink-3">
            <span>0%</span>
            {STEPS.map((s) => <span key={s} className="h-3 w-6 rounded-[2px]" style={{ background: `var(${s})` }} />)}
            <span>100% of videos</span>
          </div>
        </div>
      ) : (
        <div className="max-h-80 overflow-auto">
          <table className="table"><thead><tr><th>Beat</th>{shown[0]?.values.map((_, i) => <th key={i}>{Math.round(i * binPct)}%</th>)}</tr></thead>
            <tbody>{shown.map((r) => <tr key={r.type}><td>{lbl(r.type)}</td>{r.values.map((v, i) => <td key={i}>{Math.round(v * 100)}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}
      {tip && <Tip x={tip.x} y={tip.y}>{tip.text}</Tip>}
    </div>
  );
}

// ---- beat timeline ---------------------------------------------------------------------------

export interface BeatMark { type: string; pct: number; t: number; quote?: string; ok?: boolean; method?: string; source?: string; note?: string }

export function BeatTimeline({ marks, duration, clips }: { marks: BeatMark[]; duration: number; clips?: number }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const [tip, setTip] = useState<{ x: number; y: number; m: BeatMark } | null>(null);
  const types = Array.from(new Set(marks.map((m) => m.type)));
  return (
    <div>
      <div className="mb-2 flex justify-end"><Tabs tabs={[{ id: "chart", label: "Timeline" }, { id: "table", label: "Table" }]} value={view} onChange={setView} /></div>
      {view === "chart" ? (
        <div className="overflow-x-auto" data-testid="beat-timeline">
          <div className="relative grid min-w-[560px] gap-y-1" style={{ gridTemplateColumns: "130px 1fr" }}>
            {types.map((t) => (
              <div key={t} className="contents">
                <div className="truncate text-xs text-ink-2">{lbl(t)}</div>
                <div className="relative h-6 rounded border border-line bg-surface-2">
                  {clips && Array.from({ length: clips - 1 }, (_, k) => (
                    <div key={k} className="absolute top-0 h-full border-l border-dashed border-line" style={{ left: `${((k + 1) / clips) * 100}%` }} />
                  ))}
                  {marks.filter((m) => m.type === t).map((m, i) => (
                    <button key={i} className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full"
                      style={{ left: `${Math.min(100, Math.max(0, m.pct))}%`, background: m.ok === false ? "var(--surface-1)" : "var(--series-1)",
                        border: m.ok === false ? "2px solid var(--critical)" : "2px solid var(--surface-1)", boxShadow: "0 0 0 1px var(--series-1)" }}
                      onMouseMove={(e) => setTip({ x: e.clientX, y: e.clientY, m })} onMouseLeave={() => setTip(null)}
                      aria-label={`${lbl(m.type)} at ${m.t.toFixed(1)}s${m.ok === false ? " (rule violated)" : ""}`} />
                  ))}
                </div>
              </div>
            ))}
            <div />
            <div className="flex justify-between text-[11px] text-ink-3">
              {[0, 0.25, 0.5, 0.75, 1].map((f) => <span key={f}>{(f * duration).toFixed(0)}s · {f * 100}%</span>)}
            </div>
          </div>
          <p className="mt-2 text-[11px] text-ink-3">● beat · <span style={{ color: "var(--critical)" }}>○</span> beat that breaks a blueprint rule{clips ? " · dashed lines = 10 s clip boundaries" : ""}</p>
        </div>
      ) : (
        <table className="table"><thead><tr><th>Beat</th><th>Time</th><th>%</th><th>Quote / note</th><th>Method</th></tr></thead>
          <tbody>{[...marks].sort((a, b) => a.t - b.t).map((m, i) => (
            <tr key={i}><td>{lbl(m.type)}{m.ok === false ? " ✕" : ""}</td><td>{m.t.toFixed(1)}s</td><td>{m.pct.toFixed(0)}%</td>
              <td className="max-w-md">{m.quote ?? m.note ?? ""}</td><td>{m.method ?? m.source ?? ""}</td></tr>))}</tbody>
        </table>
      )}
      {tip && <Tip x={tip.x} y={tip.y}><b>{lbl(tip.m.type)}</b> at {tip.m.t.toFixed(1)}s ({tip.m.pct.toFixed(0)}%)
        {tip.m.quote && <><br />“{tip.m.quote}”</>}{tip.m.note && <><br /><i>{tip.m.note}</i></>}
        {(tip.m.method || tip.m.source) && <><br /><span className="text-ink-3">{tip.m.method ?? tip.m.source}</span></>}</Tip>}
    </div>
  );
}

// ---- labelled bars ---------------------------------------------------------------------------

export function Bars({ items, max = 1, format = (v) => v.toFixed(2) }: {
  items: { label: string; value: number; hint?: string }[]; max?: number; format?: (v: number) => string;
}) {
  return (
    <div className="space-y-1.5">
      {items.map((it) => (
        <div key={it.label} className="grid items-center gap-2" style={{ gridTemplateColumns: "120px 1fr 44px" }} title={it.hint}>
          <span className="truncate text-xs text-ink-2">{it.label}</span>
          <div className="h-2 rounded-full bg-surface-3">
            <div className="h-full rounded-full" style={{ width: `${Math.max(0, Math.min(1, it.value / max)) * 100}%`, background: "var(--series-1)" }} />
          </div>
          <span className="text-right text-xs tabular-nums text-ink">{format(it.value)}</span>
        </div>
      ))}
    </div>
  );
}
