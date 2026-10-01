from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (or backend/.env locally)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://notes:notes@localhost:5432/notes"

    gnani_api_key: str = ""
    gnani_stt_url: str = "https://api.vachana.ai/stt/v3"

    gemini_api_key: str = ""
    # Tried in order: Gemini models are regularly overloaded (503), so one busy model
    # shouldn't block the summary. Comma-separated so it can be changed without a deploy.
    gemini_models: str = "gemini-3.5-flash,gemini-flash-latest,gemini-3.5-flash-lite"

    # Any S3-compatible bucket. We use Supabase Storage (free, no card);
    # Cloudflare R2 or AWS S3 work by changing these values only.
    s3_endpoint_url: str = ""
    s3_region: str = "ap-south-1"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket: str = "audio-notes"

    frontend_origin: str = "http://localhost:3000"

    # Docs say 60 s, but the API rejects anything over 30 s (MAX_AUDIO_DURATION_EXCEEDED).
    # 25 s leaves margin for encoder padding.
    chunk_seconds: int = 25
    # Supabase's free plan caps a single object at 50 MB (roughly 50 min of 128 kbps MP3).
    max_upload_mb: int = 50

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, url: str) -> str:
        # Railway/Neon hand out postgres:// or postgresql:// URLs; SQLAlchemy needs the driver named.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url


settings = Settings()
