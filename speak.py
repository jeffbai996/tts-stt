"""
tts-stt — text → ElevenLabs → mp3 file path.

Usage:
    python speak.py "Hello there"
    python speak.py "Some text" --voice <voice_id>

Returns the path to the generated mp3 on stdout (so callers can grab it).
"""
import os
import sys
import argparse
import tempfile
import subprocess
import requests
import logging
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ELEVENLABS_API_KEY")
if not API_KEY:
    raise RuntimeError("ELEVENLABS_API_KEY not set in .env")

# Voice config via .env — different instances (MacClaude, Fraggy) can have different voices.
# MacClaude default: Scott (m99arlGCGHhMIOwh8bGc) — native Scottish, no accent tag needed
# Fraggy default:    Chris (iP95p4xoKVk53GoZ742B) — natural American, no accent tag
DEFAULT_VOICE_ID = os.getenv("TTS_VOICE_ID", "m99arlGCGHhMIOwh8bGc")
# Optional Chinese voice — auto-selected when text is majority-CJK
DEFAULT_VOICE_ID_ZH = os.getenv("TTS_VOICE_ID_ZH")
DEFAULT_MODEL    = os.getenv("TTS_MODEL", "eleven_v3")
# Set TTS_ACCENT_TAG="" in .env to disable accent tagging (e.g. for American voices)
ACCENT_TAG       = os.getenv("TTS_ACCENT_TAG", "[Scottish accent]")
# Playback speed multiplier applied via ffmpeg after generation (1.0 = no change)
TTS_SPEED        = float(os.getenv("TTS_SPEED", "1.05"))


def _is_cjk(text: str, threshold: float = 0.3) -> bool:
    """Return True if >threshold fraction of non-whitespace chars are CJK."""
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return False
    # CJK Unified Ideographs + common CJK ranges
    cjk = sum(1 for c in chars if '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf')
    return (cjk / len(chars)) > threshold

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger(__name__)


def synthesize(text: str, voice_id: str = DEFAULT_VOICE_ID, model: str = DEFAULT_MODEL) -> str:
    """Convert text to speech. Returns absolute path to the mp3 file."""
    # Auto-swap to Chinese voice if text is majority-CJK and caller didn't override
    is_zh = _is_cjk(text)
    if is_zh and voice_id == DEFAULT_VOICE_ID and DEFAULT_VOICE_ID_ZH:
        voice_id = DEFAULT_VOICE_ID_ZH

    # Prepend accent tag if not already present — skip for CJK (accent tags are English-only)
    if ACCENT_TAG and not is_zh and not text.lstrip().startswith("["):
        text = f"{ACCENT_TAG} {text}"

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": 0.35,
            "similarity_boost": 0.85,
            "style": 0.60,
            "use_speaker_boost": True,
        },
    }

    resp = requests.post(url, headers=headers, json=payload)
    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"ElevenLabs API error: {resp.text}") from e

    # Write raw ElevenLabs output to a temp file
    fd, raw_path = tempfile.mkstemp(suffix=".mp3", dir=OUTPUT_DIR)
    with os.fdopen(fd, "wb") as f:
        f.write(resp.content)

    # Apply speed adjustment via ffmpeg (atempo filter, quality-preserving)
    if TTS_SPEED != 1.0:
        fd2, final_path = tempfile.mkstemp(suffix=".mp3", dir=OUTPUT_DIR)
        os.close(fd2)
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", raw_path, "-filter:a", f"atempo={TTS_SPEED}", final_path],
                check=True, capture_output=True,
            )
            return final_path
        except subprocess.CalledProcessError as e:
            if os.path.exists(final_path):
                os.remove(final_path)
            raise RuntimeError(f"ffmpeg failed: {e.stderr.decode()}") from e
        finally:
            if os.path.exists(raw_path):
                os.remove(raw_path)

    return raw_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="tts-stt speak")
    parser.add_argument("text", nargs="+", help="Text to synthesize")
    parser.add_argument("--voice", default=DEFAULT_VOICE_ID, help="ElevenLabs voice ID")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="ElevenLabs model ID")
    args = parser.parse_args()

    text = " ".join(args.text)
    path = synthesize(text, voice_id=args.voice, model=args.model)
    # Print ONLY the path — callers can capture this cleanly
    print(path)
