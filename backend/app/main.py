"""HTTP API. Everything here is quick and synchronous; slow work lives in app/worker.py."""

import uuid
from contextlib import asynccontextmanager
from pathlib import PurePath

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.config import settings
from app.db import Base, engine, get_session
from app.models import Recording, Status

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".webm", ".mp4", ".amr"}
LANGUAGES = {"en-IN", "hi-IN", "bn-IN", "gu-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Small schema, no migrations tool: create missing tables on startup.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Audio Notes API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.frontend_origin.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateUpload(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="application/octet-stream", max_length=100)
    size_bytes: int = Field(gt=0)
    language_code: str = "en-IN"


def get_recording(session: Session, recording_id: uuid.UUID) -> Recording:
    rec = session.get(Recording, recording_id)
    if rec is None:
        raise HTTPException(404, "Recording not found")
    return rec


def summary_row(r: Recording) -> dict:
    return {
        "id": r.id,
        "filename": r.filename,
        "status": r.status,
        "progress": r.progress,
        "stage_message": r.stage_message,
        "error_message": r.error_message,
        "duration_s": r.duration_s,
        "size_bytes": r.size_bytes,
        "language_code": r.language_code,
        "created_at": r.created_at,
    }


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/uploads", status_code=201)
def create_upload(body: CreateUpload, session: Session = Depends(get_session)):
    """Step 1 of an upload: validate, create the row, return a URL the browser PUTs the file to."""
    ext = PurePath(body.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{ext or 'none'}'. "
                                 f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    if body.size_bytes > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(400, f"File is larger than the {settings.max_upload_mb} MB limit")
    if body.language_code not in LANGUAGES:
        raise HTTPException(400, f"Unsupported language '{body.language_code}'")

    rec = Recording(
        id=uuid.uuid4(),
        filename=body.filename,
        content_type=body.content_type or "application/octet-stream",
        size_bytes=body.size_bytes,
        language_code=body.language_code,
        status=Status.uploading,
        stage_message="Uploading",
    )
    rec.storage_key = f"uploads/{rec.id}{ext}"
    session.add(rec)
    session.commit()

    return {
        "recording_id": rec.id,
        "upload_url": storage.presigned_put_url(rec.storage_key, rec.content_type),
        "content_type": rec.content_type,
    }


@app.post("/api/uploads/{recording_id}/complete")
def complete_upload(recording_id: uuid.UUID, session: Session = Depends(get_session)):
    """Step 2: the browser says the PUT finished. Check the bucket really has it, then queue it."""
    rec = get_recording(session, recording_id)
    if rec.status != Status.uploading:
        return summary_row(rec)  # already queued - calling twice is harmless

    size = storage.object_size(rec.storage_key)
    if size is None:
        raise HTTPException(409, "The file is not in storage yet. The upload may have failed.")

    rec.size_bytes = size
    rec.status = Status.queued
    rec.progress = 0
    rec.stage_message = "Waiting for a worker"
    session.commit()
    return summary_row(rec)


@app.post("/api/uploads/{recording_id}/abort")
def abort_upload(recording_id: uuid.UUID, session: Session = Depends(get_session)):
    """The browser's PUT failed: record it so the history shows a failure, not a stuck upload."""
    rec = get_recording(session, recording_id)
    if rec.status == Status.uploading:
        rec.status = Status.failed
        rec.error_message = "The upload failed before the file reached storage. Please try again."
        rec.stage_message = None
        session.commit()
    return summary_row(rec)


@app.get("/api/recordings")
def list_recordings(session: Session = Depends(get_session)):
    rows = session.scalars(select(Recording).order_by(Recording.created_at.desc()).limit(100))
    return [summary_row(r) for r in rows]


@app.get("/api/recordings/{recording_id}")
def get_recording_detail(recording_id: uuid.UUID, session: Session = Depends(get_session)):
    rec = get_recording(session, recording_id)
    chunks_total = len(rec.chunks)
    chunks_done = sum(1 for c in rec.chunks if c.transcript is not None)
    return {
        **summary_row(rec),
        "transcript": rec.transcript,
        "summary": rec.summary,
        "summary_error": rec.summary_error,
        "chunks_total": chunks_total,
        "chunks_done": chunks_done,
        "audio_url": audio_url(rec),
    }


def audio_url(rec: Recording) -> str | None:
    # Playback is a nice-to-have: a storage problem must not hide a finished transcript.
    if rec.status == Status.uploading:
        return None
    try:
        return storage.presigned_get_url(rec.storage_key)
    except Exception:
        return None


@app.post("/api/recordings/{recording_id}/retry")
def retry(recording_id: uuid.UUID, session: Session = Depends(get_session)):
    """Re-queue a failed recording, or one whose summary failed. Finished chunks are reused."""
    rec = get_recording(session, recording_id)
    can_retry = rec.status == Status.failed or (rec.status == Status.completed and rec.summary_error)
    if not can_retry:
        raise HTTPException(409, f"Nothing to retry (status is {rec.status.value})")
    if rec.status == Status.failed and storage.object_size(rec.storage_key) is None:
        raise HTTPException(409, "The original file never reached storage. Please upload it again.")

    rec.status = Status.queued
    rec.attempts = 0
    rec.error_message = None
    rec.summary_error = None
    rec.stage_message = "Waiting for a worker"
    session.commit()
    return summary_row(rec)


@app.delete("/api/recordings/{recording_id}", status_code=204)
def delete_recording(recording_id: uuid.UUID, session: Session = Depends(get_session)):
    """Remove a recording, its chunks (FK cascade) and the audio file in the bucket."""
    rec = get_recording(session, recording_id)
    if rec.status in (Status.processing, Status.transcribing, Status.summarizing):
        raise HTTPException(409, "This recording is being processed. Delete it once it finishes.")
    # Bucket first: if that fails we keep the row, so nothing is left orphaned in storage.
    try:
        storage.delete(rec.storage_key)
    except Exception:
        raise HTTPException(502, "Could not delete the audio file from storage. Please try again.")
    session.delete(rec)
    session.commit()
