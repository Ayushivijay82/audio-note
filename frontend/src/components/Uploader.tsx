"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { ProgressBar } from "@/components/StatusBadge";
import { formatBytes, uploadFile } from "@/lib/api";

const LANGUAGES = [
  ["en-IN", "English (India)"],
  ["hi-IN", "Hindi"],
  ["bn-IN", "Bengali"],
  ["gu-IN", "Gujarati"],
  ["kn-IN", "Kannada"],
  ["ml-IN", "Malayalam"],
  ["mr-IN", "Marathi"],
  ["pa-IN", "Punjabi"],
  ["ta-IN", "Tamil"],
  ["te-IN", "Telugu"],
];

const ACCEPT = ".wav,.mp3,.m4a,.aac,.ogg,.oga,.opus,.flac,.webm,.mp4,.amr,audio/*";

export function Uploader() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState("en-IN");
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const uploading = progress !== null;

  function pick(f: File | undefined) {
    if (!f) return;
    setError(null);
    setFile(f);
  }

  async function start() {
    if (!file) return;
    setError(null);
    setProgress(0);
    try {
      const id = await uploadFile(file, language, (f) => setProgress(Math.round(f * 100)));
      router.push(`/recordings/${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed.");
      setProgress(null);
    }
  }

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5">
      <div
        onClick={() => !uploading && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!uploading) pick(e.dataTransfer.files[0]);
        }}
        className={`cursor-pointer rounded-md border-2 border-dashed p-8 text-center transition ${
          dragging ? "border-violet-500 bg-violet-50" : "border-zinc-300 hover:border-zinc-400"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => pick(e.target.files?.[0])}
        />
        {file ? (
          <p>
            <span className="font-medium">{file.name}</span>{" "}
            <span className="text-zinc-500">({formatBytes(file.size)})</span>
          </p>
        ) : (
          <p className="text-zinc-600">Drop an audio file here, or click to choose one</p>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <label className="text-sm text-zinc-700">
          Language{" "}
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            disabled={uploading}
            className="ml-1 rounded border border-zinc-300 px-2 py-1"
          >
            {LANGUAGES.map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <button
          onClick={start}
          disabled={!file || uploading}
          className="rounded bg-violet-600 px-4 py-1.5 font-medium text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {uploading ? "Uploading…" : error ? "Retry upload" : "Upload & transcribe"}
        </button>
      </div>

      {uploading && (
        <div className="mt-4">
          <ProgressBar value={progress} label={progress < 100 ? "Uploading to storage" : "Finishing upload"} />
        </div>
      )}
      {error && (
        <p className="mt-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>
      )}
    </div>
  );
}
