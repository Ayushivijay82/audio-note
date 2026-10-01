"""One-off for R2/AWS S3 only: allow the frontend to upload straight to the bucket (CORS).
Supabase Storage already allows all origins, so skip this there.

Usage (from backend/):  python -m scripts.setup_cors
Uses FRONTEND_ORIGIN from .env (comma-separated for several origins).
"""

from app import storage
from app.config import settings

origins = [o.strip() for o in settings.frontend_origin.split(",")]
storage.set_cors(origins)
print("CORS set on bucket", settings.s3_bucket, "for", origins)
