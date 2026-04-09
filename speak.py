"""
MacClaude TTS — text → ElevenLabs → mp3 file path.

Usage:
    python speak.py "Aye, nae bother mate"
    python speak.py "Some text" --voice <voice_id>

Returns the path to the generated mp3 on stdout (so callers can grab it).
"""
import os
import sys
import argparse
import tempfile
import requests
import logging
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ELEVENLABS_API_KEY")
if not API_KEY:
    raise RuntimeError("ELEVENLABS_API_KEY not set in .env")

# George — warm British voice that takes Scottish accent audio tags well on eleven_v3.
# Community Scottish voices (e.g. Scott, Archie) require a paid ElevenLabs plan.
# On free tier: [Scottish accent] tag in the text + eleven_v3 model works cleanly.
DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"  # George

DEFAULT_MODEL = "eleven_v3"

# Prepended to every synthesis call — tells v3 to emulate a Scottish accent.
ACCENT_TAG = "[Scottish accent]"

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger(__name__)


def synthesize(text: str, voice_id: str = DEFAULT_VOICE_ID, model: str = DEFAULT_MODEL) -> str:
    """Convert text to speech. Returns absolute path to the mp3 file."""
    # Prepend accent tag if not already present — v3 uses this to emulate Scottish
    if not text.startswith("["):
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
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }

    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()

    # Write to a named temp file in the output directory so the path persists
    # long enough for the Discord plugin to attach it.
    fd, path = tempfile.mkstemp(suffix=".mp3", dir=OUTPUT_DIR)
    with os.fdopen(fd, "wb") as f:
        f.write(resp.content)

    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MacClaude TTS")
    parser.add_argument("text", nargs="+", help="Text to synthesize")
    parser.add_argument("--voice", default=DEFAULT_VOICE_ID, help="ElevenLabs voice ID")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="ElevenLabs model ID")
    args = parser.parse_args()

    text = " ".join(args.text)
    path = synthesize(text, voice_id=args.voice, model=args.model)
    # Print ONLY the path — callers can capture this cleanly
    print(path)
