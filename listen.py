"""
tts-stt — audio file → whisper → transcript on stdout.

Usage:
    python listen.py /path/to/audio.ogg
"""
import os
import shutil
import subprocess
from dotenv import load_dotenv

load_dotenv()

# Defaults matching the spec. All overridable via .env or CLI flag.
DEFAULT_MODEL = os.getenv("STT_MODEL", "base")
DEFAULT_LANGUAGE = os.getenv("STT_LANGUAGE", "en")
# Default: <script_dir>/transcripts/ — mirrors speak.py's OUTPUT_DIR pattern
# for plug-and-play portability (script works from any CWD).
_DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "transcripts")
DEFAULT_OUTPUT_DIR = os.getenv("STT_OUTPUT_DIR", _DEFAULT_OUTPUT_DIR)

# All extensions whisper may write into STT_OUTPUT_DIR — used for cleanup.
_WHISPER_EXTENSIONS = ("txt", "json", "srt", "vtt", "tsv")


def transcribe(
    audio_path: str,
    model: str | None = None,
    language: str | None = None,
    output_dir: str | None = None,
) -> str:
    """Transcribe audio file to text via local whisper CLI.

    Args overrides .env overrides defaults.
    Returns stripped transcript. Empty string for silent audio.
    Raises RuntimeError on any failure.
    """
    if not os.path.exists(audio_path):
        raise RuntimeError(f"file not found: {audio_path}")

    whisper_bin = shutil.which("whisper")
    if whisper_bin is None:
        raise RuntimeError(
            "whisper CLI not found on PATH. "
            "Install: brew install openai-whisper (Mac) or pip3 install openai-whisper (Linux)"
        )

    m = model or DEFAULT_MODEL
    lang = language or DEFAULT_LANGUAGE
    out_dir = output_dir or DEFAULT_OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    cmd = [
        whisper_bin, audio_path,
        "--model", m,
        "--language", lang,
        "--output_dir", out_dir,
        "--output_format", "txt",
        "--fp16", "False",
        "--verbose", "False",
    ]

    audio_basename = os.path.splitext(os.path.basename(audio_path))[0]

    try:
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"whisper failed: {result.stderr.decode(errors='replace')}")

        txt_path = os.path.join(out_dir, f"{audio_basename}.txt")
        if not os.path.exists(txt_path):
            raise RuntimeError(f"whisper produced no output file at {txt_path}")

        with open(txt_path) as f:
            transcript = f.read().strip()

        return transcript
    finally:
        # Best-effort cleanup. Swallow OSError to avoid masking the original
        # exception from the try block (e.g. RuntimeError from whisper failure).
        for ext in _WHISPER_EXTENSIONS:
            try:
                os.remove(os.path.join(out_dir, f"{audio_basename}.{ext}"))
            except OSError:
                pass


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="tts-stt listen")
    parser.add_argument("audio_path", help="Path to the audio file")
    parser.add_argument("--model", default=None, help="Whisper model (overrides STT_MODEL)")
    parser.add_argument("--language", default=None, help="ISO language code (overrides STT_LANGUAGE)")
    args = parser.parse_args()

    try:
        transcript = transcribe(args.audio_path, model=args.model, language=args.language)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Print ONLY the transcript — callers can capture cleanly
    print(transcript)
