"""ffprobe / ffmpeg helpers. Both binaries must be on PATH (the Dockerfile installs them)."""

import json
import subprocess
from pathlib import Path


class AudioError(Exception):
    pass


def probe_duration(path: Path) -> float:
    """Return duration in seconds. Raises AudioError if the file isn't decodable audio."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_type:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise AudioError("The file could not be read as audio. It may be corrupted or not an audio file.")

    info = json.loads(result.stdout or "{}")
    if not info.get("streams"):
        raise AudioError("The file has no audio track.")
    try:
        duration = float(info["format"]["duration"])
    except (KeyError, ValueError):
        raise AudioError("Could not determine the audio duration. The file may be corrupted.")
    if duration < 0.5:
        raise AudioError("The audio is too short to transcribe.")
    return duration


def split_to_wav_chunks(src: Path, out_dir: Path, chunk_seconds: int) -> list[Path]:
    """Decode to 16 kHz mono PCM WAV and cut into fixed-length chunks.

    Converting first means every chunk Gnani gets is the same simple format,
    whatever the user uploaded. PCM WAV can be cut at any sample, so chunks are
    exactly chunk_seconds long (the last one shorter).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(src),
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
         "-f", "segment", "-segment_time", str(chunk_seconds),
         str(out_dir / "chunk_%04d.wav")],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise AudioError(f"Failed to decode the audio: {result.stderr.strip()[-300:]}")

    chunks = sorted(out_dir.glob("chunk_*.wav"))
    if not chunks:
        raise AudioError("Decoding produced no audio.")
    return chunks
