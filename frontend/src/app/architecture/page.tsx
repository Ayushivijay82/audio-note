import type { Metadata } from "next";

export const metadata: Metadata = { title: "Architecture · Audio Notes" };

const GITHUB_URL = process.env.NEXT_PUBLIC_GITHUB_URL ?? "https://github.com/Ayushivijay82/audio-note";

function H2({ children }: { children: React.ReactNode }) {
  return <h2 className="mt-8 text-xl font-semibold text-violet-800">{children}</h2>;
}

export default function ArchitecturePage() {
  return (
    <article className="max-w-3xl leading-relaxed text-zinc-800 [&_p]:mt-3 [&_li]:mt-1 [&_code]:rounded [&_code]:bg-zinc-100 [&_code]:px-1 [&_code]:text-sm">
      <h1 className="text-2xl font-semibold">How it works</h1>
      <p>
        Source code:{" "}
        <a href={GITHUB_URL} className="text-violet-700 underline">
          {GITHUB_URL}
        </a>
      </p>

      <H2>Components</H2>
      <ul className="list-disc pl-6">
        <li><b>Frontend</b>: Next.js on Vercel. Pages for upload and history, a recording detail page, and this page.</li>
        <li><b>API</b>: FastAPI on Railway. Short, synchronous requests only.</li>
        <li><b>Worker</b>: a separate Python process on Railway (<code>python -m app.worker</code>) that does all slow work.</li>
        <li><b>Postgres</b> (Railway): recordings, their chunks, status and progress. It is also the job queue.</li>
        <li><b>Storage bucket</b>: Supabase Storage, through its S3-compatible API. It holds the original audio files.</li>
        <li><b>Gnani ASR</b> for speech-to-text, and <b>Google Gemini</b> for the summary.</li>
      </ul>

      <pre className="mt-4 overflow-x-auto rounded-lg border border-zinc-200 bg-white p-4 text-xs leading-5">{`Browser ──1. POST /api/uploads──────────► API ── insert row (status=uploading)
   │      ◄── presigned PUT URL ──────────┘
   ├──2. PUT file ─────────────────────► bucket   (direct, with % progress)
   ├──3. POST /api/uploads/{id}/complete ► API ── checks bucket has object, status=queued
   └──4. GET /api/recordings/{id} every 2 s ◄── status, progress %, stage, errors

Worker loop: claim queued row (FOR UPDATE SKIP LOCKED)
   → download from bucket → ffprobe (validate) → ffmpeg: 16 kHz mono WAV, 25 s chunks
   → 3 chunks at a time → Gnani STT (retry 429/5xx/timeouts with backoff)
   → save each chunk's text + progress → join → Gemini summary → completed`}</pre>

      <H2>From upload to transcript</H2>
      <p>
        When you pick a file, the browser asks the API to create a recording. The API checks the
        extension, size and language, inserts a row with status <code>uploading</code>, and returns a
        presigned URL for a single object in the storage bucket. The browser PUTs the file straight to
        the bucket, so the audio never passes through our API or Vercel. That avoids their request
        size limits, and it lets the browser show real upload progress. The one limit is Supabase&apos;s
        free-plan cap of 50 MB per file, which the API checks up front. When the PUT finishes, the browser
        calls <code>/complete</code>. The API checks that the object really exists in the bucket and
        moves the row to <code>queued</code>.
      </p>
      <p>
        The worker polls Postgres for queued rows. It claims one with{" "}
        <code>SELECT … FOR UPDATE SKIP LOCKED</code>, so several workers could run without taking the
        same job. It then downloads the file, validates it, transcribes it chunk by chunk, joins the
        chunk transcripts in order, and asks Gemini for a summary. After every step it writes the
        status, a progress percentage and a human-readable stage message to the row. The detail page
        polls this every two seconds.
      </p>

      <H2>Where files live</H2>
      <p>
        Original uploads are stored in a private Supabase Storage bucket under <code>uploads/&lt;recording-id&gt;.&lt;ext&gt;</code>.
        The worker copies a file into a temporary directory only while it processes it, and the
        decoded WAV chunks are deleted when it finishes. Transcripts, summaries and per-chunk results
        are stored in Postgres. To play a recording back, the API gives the browser a presigned GET
        URL that expires after one hour. The bucket itself is private.
      </p>

      <H2>How long audio is handled</H2>
      <p>
        Gnani&apos;s REST STT endpoint is synchronous and accepts only a short clip per request. The
        docs say 60 seconds, but in testing the API rejected anything over 30 seconds with{" "}
        <code>MAX_AUDIO_DURATION_EXCEEDED</code>. The worker therefore uses ffmpeg to decode every
        upload to 16 kHz mono PCM WAV, whatever its original format, and cuts it into 25-second
        chunks. The 5-second gap below the limit leaves room for padding. PCM can be cut at any
        sample, so chunk boundaries are exact.
      </p>
      <p>
        Three chunks are sent to Gnani in parallel. Each chunk&apos;s transcript is saved to a{" "}
        <code>chunks</code> table as soon as it arrives, which gives the &quot;chunk 7 of 20&quot;
        progress. It also means that if one chunk fails, pressing Retry only re-sends the chunks
        that have no transcript yet. Gemini&apos;s context window is much larger than any transcript
        we produce, so the full transcript is summarised in a single request.
      </p>

      <H2>What runs synchronously vs in the background</H2>
      <ul className="list-disc pl-6">
        <li><b>Synchronous (API)</b>: validating the upload request, signing URLs, confirming the upload, reading status and results, and queuing retries. These all take milliseconds.</li>
        <li><b>Direct from the browser</b>: the upload itself, from the browser to the bucket.</li>
        <li><b>Background (worker)</b>: download, validation with ffprobe, decoding and chunking, Gnani calls, the Gemini call, and cleaning up abandoned uploads.</li>
      </ul>
      <p>
        I chose Postgres as the queue over Redis with Celery or RQ because the job state already
        lives in the database row. That means one fewer service to run, and the queue survives a
        restart. While the worker processes a row it keeps refreshing a <code>locked_at</code>{" "}
        heartbeat. If the worker crashes, the heartbeat goes stale after 15 minutes and the row is
        claimed again. A row that is interrupted three times is marked failed instead of looping
        forever.
      </p>

      <H2>Failure handling</H2>
      <ul className="list-disc pl-6">
        <li><b>Upload interrupted</b>: the browser reports it, and the row is marked failed with a clear message. Uploads that never finish are marked failed by the worker after 2 hours.</li>
        <li><b>Corrupted or non-audio file</b>: ffprobe rejects it, and the user sees &quot;could not be read as audio&quot;.</li>
        <li><b>Gnani 429/5xx, timeouts or network errors</b>: the worker retries up to 3 times with exponential backoff. If a chunk still fails, the recording fails with the chunk&apos;s timestamp and the reason, and a Retry button appears.</li>
        <li><b>Gnani 400/401</b>: not retried, because retrying wouldn&apos;t help. The user sees the message.</li>
        <li><b>Gemini failure</b>: Gemini models often return 503 &quot;high demand&quot;, so the worker retries with backoff and then falls back through a list of models. If all of them fail, the transcript is still shown, alongside a &quot;Retry summary&quot; button.</li>
        <li><b>API unreachable while polling</b>: a warning banner is shown and polling continues.</li>
      </ul>

      <H2>What I&apos;d do differently with more time</H2>
      <ul className="list-disc pl-6">
        <li>Split on silence instead of at fixed 25-second points, so words aren&apos;t cut in half at chunk boundaries. Alternatively, use Gnani&apos;s Batch API, which takes files up to 4 hours with diarization and segment timestamps.</li>
        <li>Push progress over Server-Sent Events instead of polling.</li>
        <li>Add user accounts, so each user sees only their own uploads. Right now the history is shared.</li>
        <li>Use Alembic migrations instead of <code>create_all</code>, and add tests that use a mocked Gnani.</li>
        <li>Show timestamps per chunk in the transcript, and allow clicking a timestamp to seek the audio.</li>
        <li>Use multipart uploads and a paid storage tier to go past the 50 MB file cap, add a cleanup job that deletes old files from the bucket, and add rate limiting on uploads.</li>
      </ul>
    </article>
  );
}
