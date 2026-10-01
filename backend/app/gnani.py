"""Client for Gnani's synchronous REST speech-to-text endpoint.

Docs: https://docs.gnani.ai/api/STT/speech-to-text
One request = one audio file of at most 30 s (docs say 60, the API says 30), so long recordings are split
into chunks before they reach this module (see app/audio.py).
"""

import time
from pathlib import Path

import httpx

from app.config import settings

# Status codes the docs describe as transient: rate limit, server error, service down.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class GnaniError(Exception):
    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


def _transcribe_once(client: httpx.Client, wav_path: Path, language_code: str) -> str:
    with wav_path.open("rb") as f:
        response = client.post(
            settings.gnani_stt_url,
            headers={"X-API-Key-ID": settings.gnani_api_key},
            files={"audio_file": (wav_path.name, f, "audio/wav")},
            data={"language_code": language_code, "format": "transcribe"},
        )

    if response.status_code in RETRYABLE_STATUS:
        raise GnaniError(f"Gnani returned {response.status_code}", retryable=True)
    if response.status_code in (401, 403):
        raise GnaniError("Gnani rejected the API key", retryable=False)
    if response.status_code != 200:
        raise GnaniError(f"Gnani returned {response.status_code}: {response.text[:200]}", retryable=False)

    body = response.json()
    if not body.get("success", False):
        raise GnaniError(f"Gnani reported failure: {str(body)[:200]}", retryable=False)
    return body.get("transcript", "").strip()


def transcribe_chunk(wav_path: Path, language_code: str, max_attempts: int = 3) -> str:
    """Transcribe one chunk, retrying transient failures with exponential backoff (2 s, 4 s)."""
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        for attempt in range(1, max_attempts + 1):
            try:
                return _transcribe_once(client, wav_path, language_code)
            except httpx.TimeoutException:
                error = GnaniError("Gnani timed out", retryable=True)
            except httpx.TransportError as e:
                error = GnaniError(f"Network error talking to Gnani: {e}", retryable=True)
            except GnaniError as e:
                error = e

            if not error.retryable or attempt == max_attempts:
                raise error
            time.sleep(2**attempt)

    raise AssertionError("unreachable")
