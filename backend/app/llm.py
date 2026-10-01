"""Summary generation with Google Gemini over its REST API (no SDK needed).

Gemini's context window is far larger than any transcript we will see, so the
whole transcript goes in a single request - no chunked map-reduce summarising.
"""

import time

import httpx

from app.config import settings

PROMPT = """You are summarising a transcript of an audio recording. It was produced by
automatic speech recognition, so expect missing punctuation and occasional misheard words.

Write:
1. A one-paragraph overview (2-4 sentences).
2. "Key points:" followed by 3-8 short bullet points.
3. If there are any action items, decisions or dates, list them under "Action items:". Otherwise omit this section.

Use plain text with "-" for bullets. Do not invent details that are not in the transcript.

Transcript:
"""


class LLMError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _generate(model: str, prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    try:
        response = httpx.post(
            url,
            headers={"x-goog-api-key": settings.gemini_api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=120,
        )
    except httpx.HTTPError as e:
        raise LLMError(f"Could not reach Gemini: {e}", retryable=True)

    if response.status_code != 200:
        raise LLMError(f"Gemini ({model}) returned {response.status_code}: {response.text[:200]}",
                       retryable=response.status_code in RETRYABLE_STATUS)
    try:
        return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        raise LLMError("Gemini returned an empty response.", retryable=True)


def summarize(transcript: str) -> str:
    """Try each configured model in turn, retrying transient errors with backoff (2 s, 4 s)."""
    if not settings.gemini_api_key:
        raise LLMError("GEMINI_API_KEY is not configured on the server.")

    error = None
    for model in [m.strip() for m in settings.gemini_models.split(",") if m.strip()]:
        for attempt in range(1, 4):
            try:
                return _generate(model, PROMPT + transcript)
            except LLMError as e:
                error = e
                if not e.retryable:
                    break
                if attempt < 3:
                    time.sleep(2**attempt)
    raise error
