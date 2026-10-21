import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api, getFile, LogLine, Snapshot, StagesMeta } from "./api";

interface Ctx {
  slug: string | null;
  snap: Snapshot | null;
  meta: StagesMeta | null;
  logs: LogLine[];
  connected: boolean;
  refresh: () => Promise<void>;
  version: number; // bumps whenever a job finishes, so pages re-read their files
  error: string | null;
}

const ProjectCtx = createContext<Ctx>({ slug: null, snap: null, meta: null, logs: [], connected: false,
  refresh: async () => {}, version: 0, error: null });

export function ProjectProvider({ slug, children }: { slug: string | null; children: React.ReactNode }) {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [meta, setMeta] = useState<StagesMeta | null>(null);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [connected, setConnected] = useState(false);
  const [version, setVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    if (!slug) return;
    try { setSnap(await api.get<Snapshot>(`/projects/${slug}`)); setError(null); }
    catch (e: any) { setError(e.message); }
  }, [slug]);

  const soon = useCallback(() => {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(refresh, 150);
  }, [refresh]);

  useEffect(() => { api.get<StagesMeta>("/stages").then(setMeta).catch(() => {}); }, []);

  useEffect(() => {
    setSnap(null); setLogs([]);
    if (!slug) return;
    refresh();
    const es = new EventSource(`/api/projects/${slug}/events`);
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.addEventListener("snapshot", (e) => setSnap(JSON.parse((e as MessageEvent).data)));
    es.addEventListener("log", (e) => {
      const l = JSON.parse((e as MessageEvent).data) as LogLine;
      setLogs((prev) => (prev.length > 800 ? [...prev.slice(-600), l] : [...prev, l]));
    });
    const onChange = (e: Event) => {
      const d = JSON.parse((e as MessageEvent).data);
      if (d.type === "job" && ["succeeded", "failed", "waiting_gate", "cancelled"].includes(d.status)) setVersion((v) => v + 1);
      soon();
    };
    for (const t of ["job", "progress", "pipeline", "gate", "cost"]) es.addEventListener(t, onChange);
    return () => { es.close(); setConnected(false); };
  }, [slug, refresh, soon]);

  return <ProjectCtx.Provider value={{ slug, snap, meta, logs, connected, refresh, version, error }}>{children}</ProjectCtx.Provider>;
}

export const useProject = () => useContext(ProjectCtx);

/** Read a project file (JSON or text); re-reads when a job finishes. */
export function useProjectFile<T>(rel: string | null): [T | null, boolean, () => void] {
  const { slug, version } = useProject();
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!slug || !rel) { setData(null); return; }
    let live = true;
    setLoading(true);
    getFile<T>(slug, rel).then((d) => { if (live) setData(d); })
      .catch(() => live && setData(null)).finally(() => live && setLoading(false));
    return () => { live = false; };
  }, [slug, rel, version, tick]);
  return [data, loading, () => setTick((t) => t + 1)];
}
