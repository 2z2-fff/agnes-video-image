import api from "./index";

// ─── Types ─────────────────────────────────────────

export type HistoryKind = "image" | "video";

/** One persisted generation (backend `uploads/history.json`). */
export interface HistoryRecord {
  id: string;
  kind: HistoryKind;
  created_at: number;
  status: string;
  local_url: string | null;
  remote_url: string | null;
  error: string | null;
  prompt?: string;
  mode?: string;
  ui_mode?: string;
  model?: string;
  size?: string;
  ratio?: string;
  seconds?: number;
  aspect_ratio?: string;
  task_id?: string;
  progress?: number;
}

// ─── API functions ────────────────────────────────

/** Newest generations, optionally filtered by kind. */
export async function listHistory(limit = 50, kind?: HistoryKind): Promise<HistoryRecord[]> {
  const resp = await api.get<{ items: HistoryRecord[]; count: number }>("/history", {
    params: { limit, ...(kind ? { kind } : {}) },
  });
  return resp.data.items;
}

/** Find a video record by Agnes task id (used to resume an in-flight task). */
export async function findByTask(taskId: string): Promise<HistoryRecord | null> {
  try {
    const resp = await api.get<HistoryRecord>(`/history/by-task/${taskId}`);
    return resp.data;
  } catch {
    return null;
  }
}

export async function deleteHistory(recordId: string): Promise<void> {
  await api.delete(`/history/${recordId}`);
}
