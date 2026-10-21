import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useProject } from "../lib/useProject";
import { PipelineBar } from "./Pipeline";

const NAV = [
  ["niche", "Niche", "1"], ["discover", "Discover", "2"], ["patterns", "Patterns", "3"], ["topics", "Topics", "4"],
  ["studio", "Studio", "5-6"], ["render", "Render", "7"], ["package", "Package", "8"], ["learn", "Learn", "9"],
] as const;

export function useTheme(): [boolean, () => void] {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  const toggle = () => {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    try { localStorage.setItem("vss-theme", next ? "dark" : "light"); } catch { /* private mode */ }
    setDark(next);
  };
  return [dark, toggle];
}

export function Layout({ children }: { children: React.ReactNode }) {
  const { slug, snap, connected } = useProject();
  const [dark, toggle] = useTheme();
  const [projects, setProjects] = useState<{ slug: string; name: string }[]>([]);
  const [dry, setDry] = useState<boolean | null>(null);
  const nav = useNavigate();
  useEffect(() => {
    api.get<{ slug: string; name: string }[]>("/projects").then(setProjects).catch(() => {});
    api.get<{ dry_run: boolean }>("/health").then((h) => setDry(h.dry_run)).catch(() => {});
  }, [slug]);
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r border-line bg-surface-2 p-3">
        <Link to="/" className="mb-4 flex items-center gap-2 px-1">
          <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden><circle cx="16" cy="7" r="5" fill="none" stroke="var(--accent)" strokeWidth="2.5" />
            <path d="M16 12v10M16 15l-7 5M16 15l7 5M16 22l-6 8M16 22l6 8" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" /></svg>
          <span className="text-sm font-bold leading-tight text-ink">Viral Stickman<br />Studio</span>
        </Link>
        <label className="label px-1">Project</label>
        <select className="input mb-3" value={slug ?? ""} data-testid="project-select"
          onChange={(e) => (e.target.value ? nav(`/p/${e.target.value}/niche`) : nav("/"))}>
          <option value="">— choose or create —</option>
          {projects.map((p) => <option key={p.slug} value={p.slug}>{p.name}</option>)}
        </select>
        {slug && (
          <nav className="flex flex-col gap-0.5" aria-label="Pipeline screens">
            {NAV.map(([path, label, n]) => (
              <NavLink key={path} to={`/p/${slug}/${path}`} data-testid={`nav-${path}`}
                className={({ isActive }) => `flex items-center justify-between rounded-lg px-2 py-1.5 text-sm ${isActive ? "bg-surface font-semibold text-ink shadow-sm" : "text-ink-2 hover:bg-surface-3"}`}>
                <span>{label}</span><span className="text-[11px] text-ink-3">{n}</span>
              </NavLink>
            ))}
          </nav>
        )}
        <div className="mt-auto flex flex-col gap-2 pt-3 text-xs">
          <NavLink to="/settings" className={({ isActive }) => `rounded-lg px-2 py-1.5 text-sm ${isActive ? "bg-surface font-semibold" : "text-ink-2 hover:bg-surface-3"}`} data-testid="nav-settings">⚙ Settings</NavLink>
          {dry !== null && (
            <span className="chip justify-center" title={dry ? "Dry run: fixture agent + mock render, $0" : "Live: real Claude calls and real renders"}>
              <span aria-hidden style={{ color: dry ? "var(--good)" : "var(--serious)" }}>{dry ? "●" : "▲"}</span>{dry ? "Dry run ($0)" : "LIVE (costs money)"}
            </span>
          )}
          <button className="btn justify-center" onClick={toggle} data-testid="theme-toggle" aria-label="Toggle dark mode">{dark ? "☀ Light" : "☾ Dark"}</button>
          {slug && <span className="text-center text-ink-3">{connected ? "● live updates" : "○ reconnecting…"}</span>}
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col">
        {slug && snap && <PipelineBar />}
        <div className="mx-auto w-full max-w-6xl flex-1 p-5">{children}</div>
        {slug && <LogDrawer />}
      </main>
    </div>
  );
}

function LogDrawer() {
  const { logs, meta } = useProject();
  const [open, setOpen] = useState(false);
  const [stage, setStage] = useState("all");
  const shown = useMemo(() => logs.filter((l) => stage === "all" || l.stage === stage).slice(-300), [logs, stage]);
  const last = logs[logs.length - 1];
  const color = (lvl: string) => lvl === "error" ? "var(--critical)" : lvl === "warn" ? "var(--serious)" : lvl === "gate" ? "var(--accent)" : "var(--text-muted)";
  return (
    <div className="sticky bottom-0 border-t border-line bg-surface">
      <button className="flex w-full items-center gap-2 px-4 py-1.5 text-left text-xs text-ink-2 hover:bg-surface-2" onClick={() => setOpen(!open)} data-testid="log-toggle">
        <span>{open ? "▾" : "▸"} Live log ({logs.length})</span>
        {!open && last && <span className="truncate text-ink-3">[{last.stage}] {last.text}</span>}
      </button>
      {open && (
        <div className="border-t border-line">
          <div className="flex items-center gap-2 px-4 py-1.5">
            <select className="input !w-48 !py-1 text-xs" value={stage} onChange={(e) => setStage(e.target.value)}>
              <option value="all">all stages</option>
              {meta?.all.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="h-56 overflow-auto px-4 pb-2 font-mono text-[11px] leading-5" data-testid="log-lines">
            {shown.map((l) => (
              <div key={l.id} className="whitespace-pre-wrap">
                <span className="text-ink-3">{new Date(l.ts * 1000).toLocaleTimeString()} </span>
                <span className="text-ink-3">[{l.stage}] </span>
                <span style={{ color: color(l.level) }}>{l.level !== "info" ? `${l.level}: ` : ""}</span>
                <span className="text-ink">{l.text}</span>
              </div>
            ))}
            {!shown.length && <div className="text-ink-3">No log lines yet. Run the pipeline or a stage.</div>}
          </div>
        </div>
      )}
    </div>
  );
}
