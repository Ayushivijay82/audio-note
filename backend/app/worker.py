"""Background worker: turns a queued recording into a transcript and summary.

Run with:  python -m app.worker

The `recordings` table doubles as the job queue. A worker claims the oldest
queued row with SELECT ... FOR UPDATE SKIP LOCKED, so several workers can run
without grabbing the same recording. While working it keeps bumping
`locked_at`; if a worker dies, its row goes stale and is picked up again.
"""

import logging
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import or_, select, update

from app import audio, llm, storage
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.gnani import GnaniError, transcribe_chunk
from app.models import Chunk, Recording, Status

log = logging.getLogger("worker")

POLL_SECONDS = 2
STALE_AFTER = timedelta(minutes=15)         # no heartbeat for this long => worker died
ABANDONED_UPLOAD_AFTER = timedelta(hours=2)  # browser never called /complete
MAX_ATTEMPTS = 3
CHUNK_CONCURRENCY = 3                        # parallel Gnani requests per recording

IN_FLIGHT = (Status.processing, Status.transcribing, Status.summarizing)


def now() -> datetime:
    return datetime.now(timezone.utc)


def fmt_time(seconds: float) -> str:
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def claim_next() -> Recording | None:
    with SessionLocal() as s, s.begin():
        rec = s.scalars(
            select(Recording)
            .where(
                or_(
                    Recording.status == Status.queued,
                    Recording.status.in_(IN_FLIGHT) & (Recording.locked_at < now() - STALE_AFTER),
                )
            )
            .order_by(Recording.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if rec is None:
            return None
        rec.status = Status.processing
        rec.locked_at = now()
        rec.attempts += 1
        rec.stage_message = "Preparing audio"
        rec.error_message = None
        return rec


def set_state(rec_id, **fields) -> None:
    """Update a recording and refresh its heartbeat in one statement (callers may clear it with locked_at=None)."""
    fields.setdefault("locked_at", now())
    with SessionLocal() as s, s.begin():
        s.execute(update(Recording).where(Recording.id == rec_id).values(**fields))


def fail(rec_id, message: str) -> None:
    log.warning("recording %s failed: %s", rec_id, message)
    set_state(rec_id, status=Status.failed, error_message=message, stage_message=None, locked_at=None)


def process(rec: Recording) -> None:
    if rec.attempts > MAX_ATTEMPTS:
        fail(rec.id, "Processing was interrupted too many times. Press Retry to try again.")
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "source"

        set_state(rec.id, progress=2, stage_message="Downloading file")
        try:
            storage.download(rec.storage_key, src)
        except Exception as e:
            fail(rec.id, f"Could not fetch the uploaded file from storage: {e}")
            return

        try:
            duration = audio.probe_duration(src)
            set_state(rec.id, duration_s=duration, progress=5, stage_message="Splitting audio into chunks")
            wav_chunks = audio.split_to_wav_chunks(src, tmp / "chunks", settings.chunk_seconds)
        except audio.AudioError as e:
            fail(rec.id, str(e))
            return

        done = transcribe_all(rec.id, wav_chunks, rec.language_code, duration)
        if not done:
            return

    summarize(rec.id)


def transcribe_all(rec_id, wav_chunks: list[Path], language: str, duration: float) -> bool:
    with SessionLocal() as s, s.begin():
        existing = {c.index: c for c in s.scalars(select(Chunk).where(Chunk.recording_id == rec_id))}
        if len(existing) != len(wav_chunks):
            # First run (or the chunk size changed): start the chunk list from scratch.
            for c in existing.values():
                s.delete(c)
            s.flush()
            existing = {}
            for i in range(len(wav_chunks)):
                start = i * settings.chunk_seconds
                c = Chunk(recording_id=rec_id, index=i, start_s=start,
                          end_s=min(start + settings.chunk_seconds, duration))
                s.add(c)
                existing[i] = c
        # A retry only redoes chunks that have no transcript yet.
        todo = [i for i, c in existing.items() if c.transcript is None]

    total = len(wav_chunks)
    finished = total - len(todo)
    errors: dict[int, str] = {}

    set_state(rec_id, status=Status.transcribing, progress=progress_for(finished, total),
              stage_message=f"Transcribing chunk {finished + 1} of {total}")

    with ThreadPoolExecutor(max_workers=CHUNK_CONCURRENCY) as pool:
        futures = {pool.submit(transcribe_chunk, wav_chunks[i], language): i for i in todo}
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                text, err = fut.result(), None
            except GnaniError as e:
                text, err = None, str(e)
                errors[i] = err
            with SessionLocal() as s, s.begin():
                s.execute(update(Chunk).where(Chunk.recording_id == rec_id, Chunk.index == i)
                          .values(transcript=text, error=err))
            finished += 1
            set_state(rec_id, progress=progress_for(finished, total),
                      stage_message=f"Transcribed {finished} of {total} chunks")

    if errors:
        first = min(errors)
        start = first * settings.chunk_seconds
        fail(rec_id, f"{len(errors)} of {total} chunks failed to transcribe. "
                     f"First failure at {fmt_time(start)}: {errors[first]}. "
                     f"Press Retry - completed chunks are kept.")
        return False

    with SessionLocal() as s:
        parts = s.scalars(select(Chunk.transcript).where(Chunk.recording_id == rec_id).order_by(Chunk.index))
        transcript = " ".join(p for p in parts if p)
    set_state(rec_id, transcript=transcript, progress=90)
    return True


def progress_for(finished: int, total: int) -> int:
    # 5% for download/split, 85% spread over chunks, the last 10% for the summary.
    return 5 + int(85 * finished / total)


def summarize(rec_id) -> None:
    with SessionLocal() as s:
        transcript = s.get(Recording, rec_id).transcript or ""

    if not transcript.strip():
        set_state(rec_id, status=Status.completed, progress=100, stage_message=None, locked_at=None,
                  summary=None, summary_error="No speech was detected in this recording.")
        return

    set_state(rec_id, status=Status.summarizing, stage_message="Generating summary")
    try:
        summary, error = llm.summarize(transcript), None
    except llm.LLMError as e:
        summary, error = None, str(e)
    # The transcript is still useful on its own, so a summary failure doesn't fail the recording.
    set_state(rec_id, status=Status.completed, progress=100, stage_message=None, locked_at=None,
              summary=summary, summary_error=error)


def expire_abandoned_uploads() -> None:
    with SessionLocal() as s, s.begin():
        s.execute(
            update(Recording)
            .where(Recording.status == Status.uploading,
                   Recording.created_at < now() - ABANDONED_UPLOAD_AFTER)
            .values(status=Status.failed, error_message="The upload never finished. Please upload the file again.")
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    Base.metadata.create_all(engine)
    log.info("worker started")
    last_cleanup = 0.0
    while True:
        if time.monotonic() - last_cleanup > 300:
            expire_abandoned_uploads()
            last_cleanup = time.monotonic()

        rec = claim_next()
        if rec is None:
            time.sleep(POLL_SECONDS)
            continue

        log.info("processing %s (%s)", rec.id, rec.filename)
        try:
            process(rec)
        except Exception as e:  # never let one bad recording kill the worker
            log.exception("unexpected error on %s", rec.id)
            fail(rec.id, f"Unexpected server error: {e}")


if __name__ == "__main__":
    main()
