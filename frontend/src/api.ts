export type ServerTool = { accepts: string[]; min_files: number; max_files: number };
export type ToolList = { tools: Record<string, ServerTool>; limits: { file_mb: number; total_mb: number; files: number } };
export type JobStatus = { status: "queued" | "running" | "done" | "failed"; error: string | null; name?: string; ext?: string };

async function json<T>(r: Response): Promise<T> {
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail ?? "Something went wrong");
  return body as T;
}

export const getTools = () => fetch("/api/tools").then((r) => json<ToolList>(r));

export function createJob(tool: string, files: File[], options: object = {}) {
  const form = new FormData();
  form.append("tool", tool);
  form.append("options", JSON.stringify(options));
  files.forEach((f) => form.append("files", f));
  return fetch("/api/jobs", { method: "POST", body: form }).then((r) => json<{ id: string }>(r));
}

export const getFormats = () => fetch("/api/formats").then((r) => json<Record<string, string[]>>(r));

export const getJob = (id: string) => fetch(`/api/jobs/${id}`).then((r) => json<JobStatus>(r));
export const deleteJob = (id: string) => fetch(`/api/jobs/${id}`, { method: "DELETE" });
export function downloadUrl(id: string, deleteAfter: boolean, name?: string) {
  const q = new URLSearchParams();
  if (deleteAfter) q.set("delete", "true");
  if (name) q.set("name", name);
  return `/api/jobs/${id}/download${q.size ? `?${q}` : ""}`;
}

/** Fetch the result for an in-page preview; never deletes it. */
export const fetchResult = (id: string) => fetch(downloadUrl(id, false)).then((r) => {
  if (!r.ok) throw new Error("Could not load the preview");
  return r.blob();
});
