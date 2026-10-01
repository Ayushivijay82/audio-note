import type { Status } from "@/lib/api";

const STYLES: Record<Status, string> = {
  uploading: "bg-sky-100 text-sky-800",
  queued: "bg-zinc-100 text-zinc-700",
  processing: "bg-amber-100 text-amber-800",
  transcribing: "bg-amber-100 text-amber-800",
  summarizing: "bg-violet-100 text-violet-800",
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
};

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STYLES[status]}`}>
      {status}
    </span>
  );
}

export function ProgressBar({ value, label }: { value: number; label?: string | null }) {
  return (
    <div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-200" role="progressbar" aria-valuenow={value}>
        <div className="h-full bg-violet-600 transition-all duration-500" style={{ width: `${value}%` }} />
      </div>
      {label && (
        <p className="mt-1 text-sm text-zinc-600">
          {label} · {value}%
        </p>
      )}
    </div>
  );
}
