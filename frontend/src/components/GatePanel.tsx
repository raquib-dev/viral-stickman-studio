import { useEffect, useState } from "react";
import { api, Gate } from "../lib/api";
import { useProject } from "../lib/useProject";
import { ErrorBox, StatusChip } from "./ui";

/**
 * Every GATE is a visible approve / edit / reject control. `choices` lets the page render its own
 * option picker (topic cards, hook cards); `onEdit` opens the page's editor (Phase A text).
 */
export function GatePanel({ name, title, children, choice, setChoice, editHint }: {
  name: string; title: string; children?: React.ReactNode; choice?: string | null; setChoice?: (c: string) => void;
  editHint?: string;
}) {
  const { slug, snap, refresh } = useProject();
  const gate: Gate | undefined = snap?.gates.find((g) => g.name === name);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const opts = gate?.payload?.options ?? null;
  const [local, setLocal] = useState<string | null>(null);
  const pagePicks = Boolean(setChoice);
  const current = pagePicks ? choice : local;
  const pick = setChoice ?? setLocal;
  useEffect(() => {
    if (gate && current == null) pick((gate.choice as string) ?? gate.payload?.default_choice ?? null as any);
  }, [gate?.payload_hash]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!gate) return null;
  const decide = async (action: "approve" | "reject") => {
    setBusy(true); setErr(null);
    try { await api.post(`/projects/${slug}/gates/${name}`, { action, choice: action === "approve" ? current ?? gate.payload.default_choice : null, note }); await refresh(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const pending = gate.status === "pending";
  return (
    <div id={`gate-${name}`} className="rounded-xl border-2 p-4" style={{ borderColor: pending ? "var(--serious)" : "var(--line)" }} data-testid={`gate-${name}`}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-xs font-bold uppercase tracking-wider text-ink-3">Gate</span>
        <h3 className="h2">{title}</h3>
        <StatusChip status={gate.status} />
        {gate.decided_by && !pending && <span className="text-xs text-ink-3">by {gate.decided_by}{gate.note ? `: ${gate.note}` : ""}</span>}
      </div>
      {children}
      {opts && !pagePicks && (
        <select className="input mt-2 max-w-xl" value={current ?? ""} onChange={(e) => pick(e.target.value)}>
          {opts.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
        </select>
      )}
      {pending && (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <div className="min-w-[240px] flex-1">
            <label className="label">Note (optional; required for a useful reject)</label>
            <input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. make clip 2 calmer" />
          </div>
          <button className="btn-primary" disabled={busy} onClick={() => decide("approve")} data-testid={`approve-${name}`}>✓ Approve{opts && current ? " selection" : ""}</button>
          <button className="btn-danger" disabled={busy} onClick={() => decide("reject")} data-testid={`reject-${name}`}>✕ Reject</button>
        </div>
      )}
      {pending && editHint && <p className="mt-2 text-xs text-ink-3">✎ {editHint}</p>}
      {err && <div className="mt-2"><ErrorBox>{err}</ErrorBox></div>}
    </div>
  );
}
