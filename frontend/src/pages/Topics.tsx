import { useState } from "react";
import { Bars } from "../components/charts";
import { GatePanel } from "../components/GatePanel";
import { RunStageButton } from "../components/Pipeline";
import { Empty, FixtureBadge, Note, SyntheticBadge } from "../components/ui";
import { useProject, useProjectFile } from "../lib/useProject";

const COMP: Record<string, string> = { outlier_evidence: "Outlier evidence", gap: "Gap (demand vs supply)", stickman_fit: "Stick-figure fit", niche_fit: "Niche fit" };

export default function Topics() {
  const { snap } = useProject();
  const [data] = useProjectFile<any>("research/topics.json");
  const [choice, setChoice] = useState<string | null>(null);
  const gate = snap?.gates.find((g) => g.name === "topic");
  const pending = gate?.status === "pending";
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="h1">4 · Topic finder</h1>
        <span className="flex items-center gap-2">{data?.synthetic_evidence && <SyntheticBadge />}<RunStageButton stage="topics" /></span>
      </div>
      {data && <Note>score = {Object.entries(data.weights ?? {}).map(([k, w]) => `${w} × ${COMP[k] ?? k}`).join(" + ")} (weights in Settings).</Note>}
      <GatePanel name="topic" title="Pick the topic" choice={choice} setChoice={setChoice}>
        <p className="text-sm text-ink-2">{pending ? "Click a topic card, then approve. The pipeline continues to Hooks." : "Approved topics feed the Hooks stage."}</p>
      </GatePanel>
      {!data ? <Empty>No topics yet. Run Topics (needs Patterns).</Empty> : (
        <div className="grid gap-3" data-testid="topic-board">
          {data.topics.map((t: any) => {
            const selected = (choice ?? gate?.choice ?? gate?.payload?.default_choice) === t.id;
            return (
              <button key={t.id} type="button" disabled={!pending} onClick={() => setChoice(t.id)} data-testid={`topic-${t.id}`}
                className={`card text-left ${selected ? "ring-2 ring-accent" : ""} ${pending ? "cursor-pointer hover:bg-surface-2" : "cursor-default"}`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="text-xs text-ink-3">#{t.rank} · score {t.score.toFixed(2)} {selected && "· ✓ selected"}</div>
                    <div className="text-base font-semibold text-ink">{t.title}</div>
                    <div className="text-sm text-ink-2">{t.angle}</div>
                  </div>
                  {String(t.demand_note ?? "").startsWith("dry-run") && <FixtureBadge />}
                </div>
                <div className="mt-3 grid gap-4 md:grid-cols-2">
                  <Bars items={Object.entries(t.components).map(([k, v]) => ({ label: COMP[k] ?? k, value: v as number }))} />
                  <div className="text-xs text-ink-2">
                    <div className="label">Evidence</div>
                    {t.evidence.length ? <ul className="space-y-0.5">{t.evidence.map((e: any, i: number) => (
                      <li key={i}>{e.multiple?.toFixed(1)}× · {e.title}{e.synthetic ? " (synthetic)" : ""}</li>))}</ul> : <span className="muted">no related outliers found</span>}
                    <div className="mt-1"><b>Stick-figure fit:</b> {t.stickman_reason}</div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
