"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { ACTIVE_STATUSES, formatDuration, listRecordings, type RecordingSummary } from "@/lib/api";

export function RecordingList() {
  const [rows, setRows] = useState<RecordingSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function load() {
      try {
        const data = await listRecordings();
        if (cancelled) return;
        setRows(data);
        setError(null);
        // Keep refreshing only while something is still in progress.
        if (data.some((r) => ACTIVE_STATUSES.includes(r.status))) timer = setTimeout(load, 4000);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Could not load uploads.");
        timer = setTimeout(load, 5000);
      }
    }

    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  if (error && !rows) return <p className="text-sm text-red-700">{error} Retrying…</p>;
  if (!rows) return <p className="text-sm text-zinc-500">Loading…</p>;
  if (rows.length === 0) return <p className="text-sm text-zinc-500">No uploads yet.</p>;

  return (
    <ul className="divide-y divide-zinc-200 rounded-lg border border-zinc-200 bg-white">
      {rows.map((r) => (
        <li key={r.id}>
          <Link href={`/recordings/${r.id}`} className="flex items-center gap-4 px-4 py-3 hover:bg-zinc-50">
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{r.filename}</p>
              <p className="text-xs text-zinc-500">
                {new Date(r.created_at).toLocaleString()} · {formatDuration(r.duration_s)}
              </p>
            </div>
            {ACTIVE_STATUSES.includes(r.status) && r.status !== "uploading" && (
              <span className="text-xs text-zinc-500">{r.progress}%</span>
            )}
            <StatusBadge status={r.status} />
          </Link>
        </li>
      ))}
    </ul>
  );
}
