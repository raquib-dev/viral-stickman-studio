// Thin fetch wrapper. Every path is relative so the Vite proxy (dev) and FastAPI static (prod) both work.
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function req<T>(method: string, path: string, body?: unknown, isForm = false): Promise<T> {
  const init: RequestInit = { method, headers: isForm ? {} : { "content-type": "application/json" } };
  if (body !== undefined) init.body = isForm ? (body as FormData) : JSON.stringify(body);
  const r = await fetch(`/api${path}`, init);
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = j.detail ?? JSON.stringify(j); } catch { /* not json */ }
    throw new ApiError(r.status, msg);
  }
  return r.json() as Promise<T>;
}

export const api = {
  get: <T,>(p: string) => req<T>("GET", p),
  post: <T,>(p: string, b: unknown = {}) => req<T>("POST", p, b),
  put: <T,>(p: string, b: unknown) => req<T>("PUT", p, b),
  del: <T,>(p: string) => req<T>("DELETE", p),
  upload: <T,>(p: string, f: FormData) => req<T>("POST", p, f, true),
};

export const fileUrl = (slug: string, rel: string, bust?: number | string) =>
  `/api/projects/${slug}/files/${rel}${bust ? `?v=${bust}` : ""}`;

/** Read a file that may not exist yet (204 = not produced yet). */
export async function getFile<T>(slug: string, rel: string): Promise<T | null> {
  const r = await fetch(`/api/projects/${slug}/files/${rel}?optional=1`);
  if (r.status === 204) return null;
  if (!r.ok) throw new ApiError(r.status, r.statusText);
  const ct = r.headers.get("content-type") ?? "";
  return (ct.includes("json") ? r.json() : r.text()) as Promise<T>;
}

export type StageStatus = "not_run" | "queued" | "running" | "succeeded" | "failed" | "waiting_gate" | "cancelled" | "interrupted" | "stale" | "resumed";

export interface StageRow {
  stage: string; status: StageStatus; job_id: number | null; progress: number | null; message: string | null;
  cost_usd: number | null; finished_at: number | null; error: string | null; started_at: number | null; runs: number;
}
export interface Job {
  id: number; project: string; stage: string; status: string; created_at: number; started_at: number | null;
  finished_at: number | null; progress: number; message: string | null; cost_usd: number; error: string | null;
  params: Record<string, any>;
}
export interface Gate {
  name: string; status: "pending" | "approved" | "rejected"; payload_hash: string; choice: unknown; note: string | null;
  decided_by: string | null; opened_at: number | null; decided_at: number | null;
  payload: { data: any; options: { id: string; label: string }[] | null; default_choice: any };
}
export interface Pipeline {
  project: string; status: string; current_stage: string | null; from_stage: string | null; to_stage: string | null;
  waiting_gate: string | null; message: string | null; updated_at: number;
}
export interface ProjectData {
  name: string; niche: string; subtopics: string[]; platforms: string[]; style: string; theme: string; ratio: string;
  duration: number; competitors: { youtube: string[]; instagram: string[] }; voice_pref: string;
  voice_transcripts: { youtube: string[]; instagram: string[] }; [k: string]: any;
}
export interface Snapshot {
  project: { slug: string; name: string; created_at: number; data: ProjectData };
  stages: StageRow[]; pipeline: Pipeline | null; gates: Gate[]; spend_usd: number; render_spend_usd: number;
}
export interface LogLine { id: number; job_id: number; ts: number; level: string; text: string; stage?: string }
export interface StagesMeta {
  pipeline: string[]; all: string[]; gates: Record<string, string>;
  stages: Record<string, { title: string; lane: string; description: string; skills: string[]; tools: string[] }>;
}
