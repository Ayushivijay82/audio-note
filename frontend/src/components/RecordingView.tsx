"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ProgressBar, StatusBadge } from "@/components/StatusBadge";
import {
  ACTIVE_STATUSES,
  deleteRecording,
  formatBytes,
  formatDuration,
  getRecording,
  retryRecording,
  type RecordingDetail,
} from "@/lib/api";

const POLL_MS = 2000;

export function RecordingView({ id }: { id: string }) {
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [rec, setRec] = useState<RecordingDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  // Bumped after a retry so the polling effect restarts.
  const [pollKey, setPollKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const data = await getRecording(id);
        if (cancelled) return;
        setRec(data);
        setLoadError(null);
        if (ACTIVE_STATUSES.includes(data.status)) timer = setTimeout(poll, POLL_MS);
      } catch (e) {
        if (cancelled) return;
        setLoadError(e instanceof Error ? e.message : "Could not load this recording.");
        timer = setTimeout(poll, POLL_MS * 2); // keep trying; the server may be restarting
      }
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id, pollKey]);

  const retry = useCallback(async () => {
    setRetrying(true);
    setRetryError(null);
    try {
      await retryRecording(id);
      setPollKey((k) => k + 1);
    } catch (e) {
      setRetryError(e instanceof Error ? e.message : "Retry failed.");
    } finally {
      setRetrying(false);
    }
  }, [id]);

  async function remove() {
    if (!confirm("Delete this recording, its transcript and summary? This cannot be undone.")) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteRecording(id);
      router.push("/");
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Delete failed.");
      setDeleting(false);
    }
  }

  if (!rec) {
    return loadError ? (
      <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-red-800">{loadError}</p>
    ) : (
      <p className="text-zinc-500">Loading…</p>
    );
  }

  const active = ACTIVE_STATUSES.includes(rec.status);

  return (
    <div className="space-y-6">
      <div>
        <Link href="/" className="text-sm text-violet-700 hover:underline">
          ← All uploads
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold break-all">{rec.filename}</h1>
          <StatusBadge status={rec.status} />
          {!["processing", "transcribing", "summarizing"].includes(rec.status) && (
            <button
              onClick={remove}
              disabled={deleting}
              className="ml-auto rounded border border-red-300 px-3 py-1 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50"
            >
              {deleting ? "Deleting…" : "Delete"}
            </button>
          )}
        </div>
        {deleteError && <p className="mt-2 text-sm text-red-700">{deleteError}</p>}
        <p className="mt-1 text-sm text-zinc-500">
          {new Date(rec.created_at).toLocaleString()} · {formatDuration(rec.duration_s)} ·{" "}
          {formatBytes(rec.size_bytes)} · {rec.language_code}
        </p>
      </div>

      {loadError && (
        <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Lost contact with the server ({loadError}). Still trying…
        </p>
      )}

      {active && (
        <div className="rounded-lg border border-zinc-200 bg-white p-5">
          <ProgressBar value={rec.progress} label={rec.stage_message ?? rec.status} />
          {rec.chunks_total > 0 && (
            <p className="mt-2 text-xs text-zinc-500">
              Long audio is split into {rec.chunks_total} chunks of ~25 s for Gnani ASR; {rec.chunks_done} done.
              You can leave this page: processing continues on the server.
            </p>
          )}
        </div>
      )}

      {rec.status === "failed" && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-5">
          <p className="font-medium text-red-900">Processing failed</p>
          <p className="mt-1 text-sm text-red-800">{rec.error_message}</p>
          <button
            onClick={retry}
            disabled={retrying}
            className="mt-3 rounded bg-red-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-800 disabled:opacity-50"
          >
            {retrying ? "Retrying…" : "Retry"}
          </button>
          {retryError && <p className="mt-2 text-sm text-red-800">{retryError}</p>}
        </div>
      )}

      {/* Only once polling stops: every poll returns a freshly signed URL, which would reset the player. */}
      {!active && rec.audio_url && <audio controls src={rec.audio_url} className="w-full" />}

      {rec.status === "completed" && (
        <>
          <section className="rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="text-lg font-semibold">Summary</h2>
            {rec.summary ? (
              <div className="mt-2 whitespace-pre-wrap text-zinc-800">{rec.summary}</div>
            ) : (
              <div className="mt-2 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <p>Summary unavailable: {rec.summary_error}</p>
                <button
                  onClick={retry}
                  disabled={retrying}
                  className="mt-2 rounded bg-amber-700 px-3 py-1 text-white hover:bg-amber-800 disabled:opacity-50"
                >
                  {retrying ? "Retrying…" : "Retry summary"}
                </button>
                {retryError && <p className="mt-2">{retryError}</p>}
              </div>
            )}
          </section>

          <section className="rounded-lg border border-zinc-200 bg-white p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Transcript</h2>
              {rec.transcript && (
                <button
                  onClick={() => navigator.clipboard.writeText(rec.transcript ?? "")}
                  className="text-sm text-violet-700 hover:underline"
                >
                  Copy
                </button>
              )}
            </div>
            <p className="mt-2 whitespace-pre-wrap leading-relaxed text-zinc-800">
              {rec.transcript || "No speech was detected."}
            </p>
          </section>
        </>
      )}
    </div>
  );
}
