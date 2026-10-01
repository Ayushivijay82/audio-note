"""Day-1 smoke test: send one short audio file straight to Gnani.

Usage (from backend/):
    .venv/bin/python -m scripts.try_gnani path/to/clip.wav [en-IN]

The file is converted to 16 kHz mono WAV first, same as the worker will do.
Only the first 25 s is sent - Gnani rejects requests over 30 s.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from app.config import settings
from app.gnani import transcribe_chunk


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if not settings.gnani_api_key:
        sys.exit("GNANI_API_KEY is empty - fill it in backend/.env")

    src = Path(sys.argv[1])
    language = sys.argv[2] if len(sys.argv) > 2 else "en-IN"

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "clip.wav"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(src), "-ac", "1", "-ar", "16000", "-t", "25", str(wav)],
            check=True,
        )
        print(transcribe_chunk(wav, language))


if __name__ == "__main__":
    main()
