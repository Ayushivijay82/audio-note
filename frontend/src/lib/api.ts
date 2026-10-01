// Thin client for the FastAPI backend. NEXT_PUBLIC_API_URL is baked in at build time.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type Status =
  | "uploading"
  | "queued"
  | "processing"
  | "transcribing"
  | "summarizing"
  | "completed"
  | "failed";

export const ACTIVE_STATUSES: Status[] = ["uploading", "queued", "processing", "transcribing", "summarizing"];

export type RecordingSummary = {
  id: string;
  filename: string;
  status: Status;
  progress: number;
  stage_message: string | null;
  error_message: string | null;
  duration_s: number | null;
  size_bytes: number;
  language_code: string;
  created_at: string;
};

export type RecordingDetail = RecordingSummary & {
  transcript: string | null;
  summary: string | null;
  summary_error: string | null;
  chunks_total: number;
  chunks_done: number;
  audio_url: string | null;
};

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError("Cannot reach the server. Check your connection and try again.");
  }
  if (!res.ok) {
    // FastAPI puts the reason in `detail` (a string, or a list for validation errors).
    const body = await res.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : `Server error (${res.status})`;
    throw new ApiError(detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const listRecordings = () => request<RecordingSummary[]>("/api/recordings");
export const getRecording = (id: string) => request<RecordingDetail>(`/api/recordings/${id}`);
export const retryRecording = (id: string) =>
  request<RecordingSummary>(`/api/recordings/${id}/retry`, { method: "POST" });
export const deleteRecording = (id: string) => request<void>(`/api/recordings/${id}`, { method: "DELETE" });

type CreateUploadResponse = { recording_id: string; upload_url: string; content_type: string };

/**
 * Full upload: ask the API for a presigned URL, PUT the file straight to the
 * bucket (XHR, because fetch has no upload-progress events), then tell the API
 * it's done so the worker picks it up. Returns the recording id.
 */
export async function uploadFile(
  file: File,
  languageCode: string,
  onProgress: (fraction: number) => void,
): Promise<string> {
  const created = await request<CreateUploadResponse>("/api/uploads", {
    method: "POST",
    body: JSON.stringify({
      filename: file.name,
      content_type: file.type || "application/octet-stream",
      size_bytes: file.size,
      language_code: languageCode,
    }),
  });

  try {
    await putWithProgress(created.upload_url, file, created.content_type, onProgress);
  } catch (e) {
    await request(`/api/uploads/${created.recording_id}/abort`, { method: "POST" }).catch(() => {});
    throw e;
  }

  await request(`/api/uploads/${created.recording_id}/complete`, { method: "POST" });
  return created.recording_id;
}

function putWithProgress(url: string, file: File, contentType: string, onProgress: (f: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", contentType);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new ApiError(`Storage rejected the upload (HTTP ${xhr.status}).`));
    xhr.onerror = () => reject(new ApiError("The upload was interrupted. Check your connection and try again."));
    xhr.ontimeout = () => reject(new ApiError("The upload timed out."));
    xhr.send(file);
  });
}

export function formatDuration(seconds: number | null): string {
  if (seconds == null) return "—";
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
