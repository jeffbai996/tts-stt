"""Tests for listen.py — batch STT via local whisper CLI."""
import os
import shutil

import pytest
from unittest.mock import MagicMock


def _mock_whisper_success(output_dir: str, audio_path: str, transcript: str = "hello world"):
    """Helper: simulates whisper writing a .txt file next to the audio and exiting 0."""
    audio_basename = os.path.splitext(os.path.basename(audio_path))[0]
    txt_path = os.path.join(output_dir, f"{audio_basename}.txt")
    with open(txt_path, "w") as f:
        f.write(transcript)
    return MagicMock(returncode=0, stderr=b"")


def test_missing_file_raises(tmp_output_dir):
    """Non-existent path → RuntimeError with 'file not found'."""
    from listen import transcribe
    with pytest.raises(RuntimeError, match="file not found"):
        transcribe("/nonexistent/path/audio.ogg")


def test_whisper_not_found_raises(sample_audio, tmp_output_dir, monkeypatch):
    """shutil.which returns None → RuntimeError with install hint."""
    from listen import transcribe
    monkeypatch.setattr("listen.shutil.which", lambda _: None)
    with pytest.raises(RuntimeError, match="whisper CLI not found"):
        transcribe(sample_audio)


def test_subprocess_invoked_with_defaults(sample_audio, tmp_output_dir, monkeypatch):
    """Default invocation uses base model, en language, fp16 False, verbose False."""
    from listen import transcribe
    monkeypatch.setattr("listen.shutil.which", lambda _: "/usr/local/bin/whisper")
    # DEFAULT_OUTPUT_DIR is frozen at import time; patch the module attribute directly
    # (env var set by tmp_output_dir fixture arrives too late to affect it)
    monkeypatch.setattr("listen.DEFAULT_OUTPUT_DIR", str(tmp_output_dir))

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _mock_whisper_success(str(tmp_output_dir), sample_audio)

    monkeypatch.setattr("listen.subprocess.run", fake_run)
    result = transcribe(sample_audio)

    assert result == "hello world"
    assert captured["cmd"][0] == "/usr/local/bin/whisper"
    assert sample_audio in captured["cmd"]
    assert "--model" in captured["cmd"] and "base" in captured["cmd"]
    assert "--language" in captured["cmd"] and "en" in captured["cmd"]
    assert "--fp16" in captured["cmd"] and "False" in captured["cmd"]
    assert "--verbose" in captured["cmd"] and "False" in captured["cmd"]
    assert "--output_format" in captured["cmd"] and "txt" in captured["cmd"]


def test_whisper_subprocess_failure_raises(sample_audio, tmp_output_dir, monkeypatch):
    """Non-zero whisper exit → RuntimeError carrying whisper's stderr."""
    from listen import transcribe
    monkeypatch.setattr("listen.shutil.which", lambda _: "/usr/local/bin/whisper")

    def fake_run(cmd, **kwargs):
        return MagicMock(returncode=1, stderr=b"whisper: bad audio format")

    monkeypatch.setattr("listen.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="whisper failed.*bad audio format"):
        transcribe(sample_audio)


def test_whisper_produced_no_output_raises(sample_audio, tmp_output_dir, monkeypatch):
    """Whisper exits 0 but no .txt written → RuntimeError, not raw FileNotFoundError."""
    from listen import transcribe
    monkeypatch.setattr("listen.shutil.which", lambda _: "/usr/local/bin/whisper")
    # DEFAULT_OUTPUT_DIR is frozen at import time; patch the module attribute directly
    # (env var set by tmp_output_dir fixture arrives too late to affect it)
    monkeypatch.setattr("listen.DEFAULT_OUTPUT_DIR", str(tmp_output_dir))

    def fake_run(cmd, **kwargs):
        # Do NOT write the .txt file — simulate whisper exiting 0 without output
        return MagicMock(returncode=0, stderr=b"")

    monkeypatch.setattr("listen.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="whisper produced no output"):
        transcribe(sample_audio)


def test_empty_audio_returns_empty_string(sample_audio, tmp_output_dir, monkeypatch):
    """Whisper writes empty .txt (silent audio) → returns '', not an error."""
    from listen import transcribe
    monkeypatch.setattr("listen.shutil.which", lambda _: "/usr/local/bin/whisper")
    # DEFAULT_OUTPUT_DIR is frozen at import time; patch the module attribute directly
    # (env var set by tmp_output_dir fixture arrives too late to affect it)
    monkeypatch.setattr("listen.DEFAULT_OUTPUT_DIR", str(tmp_output_dir))

    def fake_run(cmd, **kwargs):
        return _mock_whisper_success(str(tmp_output_dir), sample_audio, transcript="")

    monkeypatch.setattr("listen.subprocess.run", fake_run)
    result = transcribe(sample_audio)
    assert result == ""


def test_stt_model_env_override(sample_audio, tmp_output_dir, monkeypatch):
    """STT_MODEL=small in env → whisper called with --model small."""
    monkeypatch.setenv("STT_MODEL", "small")

    import importlib
    import listen
    importlib.reload(listen)

    # Patch AFTER reload so we target the reloaded module's namespace
    monkeypatch.setattr("listen.shutil.which", lambda _: "/usr/local/bin/whisper")

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _mock_whisper_success(str(tmp_output_dir), sample_audio)

    monkeypatch.setattr("listen.subprocess.run", fake_run)
    listen.transcribe(sample_audio)

    assert "--model" in captured["cmd"]
    model_idx = captured["cmd"].index("--model")
    assert captured["cmd"][model_idx + 1] == "small"

    # Restore defaults by reloading with original env
    monkeypatch.delenv("STT_MODEL")
    importlib.reload(listen)


def test_stt_language_env_override(sample_audio, tmp_output_dir, monkeypatch):
    """STT_LANGUAGE=zh in env → whisper called with --language zh."""
    monkeypatch.setenv("STT_LANGUAGE", "zh")

    import importlib
    import listen
    importlib.reload(listen)

    # Patch AFTER reload so we target the reloaded module's namespace
    monkeypatch.setattr("listen.shutil.which", lambda _: "/usr/local/bin/whisper")

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _mock_whisper_success(str(tmp_output_dir), sample_audio)

    monkeypatch.setattr("listen.subprocess.run", fake_run)
    listen.transcribe(sample_audio)

    assert "--language" in captured["cmd"]
    lang_idx = captured["cmd"].index("--language")
    assert captured["cmd"][lang_idx + 1] == "zh"

    # Restore defaults by reloading with original env
    monkeypatch.delenv("STT_LANGUAGE")
    importlib.reload(listen)


def test_language_kwarg_overrides_env(sample_audio, tmp_output_dir, monkeypatch):
    """Language kwarg overrides STT_LANGUAGE env var at the library level."""
    monkeypatch.setenv("STT_LANGUAGE", "en")

    import importlib
    import listen
    importlib.reload(listen)

    monkeypatch.setattr("listen.shutil.which", lambda _: "/usr/local/bin/whisper")

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _mock_whisper_success(str(tmp_output_dir), sample_audio)

    monkeypatch.setattr("listen.subprocess.run", fake_run)
    # The `language` kwarg simulates what the CLI flag does — overrides env
    listen.transcribe(sample_audio, language="zh")

    lang_idx = captured["cmd"].index("--language")
    assert captured["cmd"][lang_idx + 1] == "zh"

    # Restore defaults
    monkeypatch.delenv("STT_LANGUAGE")
    importlib.reload(listen)


def test_cli_error_path_exits_nonzero_with_stderr():
    """End-to-end CLI: nonexistent file path → ERROR on stderr, nothing on stdout, exit 1.

    Verifies argparse wiring, the RuntimeError → stderr → sys.exit(1) path, and
    the stdout contract (transcript only, no error noise).
    """
    import subprocess
    import sys
    from pathlib import Path

    listen_py = Path(__file__).parent.parent / "listen.py"
    result = subprocess.run(
        [sys.executable, str(listen_py), "/definitely/not/a/real/file.ogg"],
        capture_output=True,
        timeout=10,
    )

    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    assert result.stdout == b"", f"expected empty stdout, got {result.stdout!r}"
    assert b"ERROR:" in result.stderr, f"expected 'ERROR:' in stderr, got {result.stderr!r}"
    assert b"file not found" in result.stderr, (
        f"expected 'file not found' message in stderr, got {result.stderr!r}"
    )


def test_cleanup_removes_intermediate_files(sample_audio, tmp_output_dir, monkeypatch):
    """After success, tmp_output_dir has no .txt/.json/.srt leftovers."""
    from listen import transcribe
    monkeypatch.setattr("listen.shutil.which", lambda _: "/usr/local/bin/whisper")
    # DEFAULT_OUTPUT_DIR is frozen at import time; patch the module attribute directly
    # (env var set by tmp_output_dir fixture arrives too late to affect it)
    monkeypatch.setattr("listen.DEFAULT_OUTPUT_DIR", str(tmp_output_dir))

    def fake_run(cmd, **kwargs):
        # Write all five formats whisper might leave around
        base = os.path.splitext(os.path.basename(sample_audio))[0]
        for ext in ("txt", "json", "srt", "vtt", "tsv"):
            with open(os.path.join(str(tmp_output_dir), f"{base}.{ext}"), "w") as f:
                f.write("hello world" if ext == "txt" else "{}")
        return MagicMock(returncode=0, stderr=b"")

    monkeypatch.setattr("listen.subprocess.run", fake_run)
    transcribe(sample_audio)

    leftovers = list(tmp_output_dir.iterdir())
    assert leftovers == [], f"expected clean output dir, found {leftovers}"


def test_cleanup_on_whisper_failure(sample_audio, tmp_output_dir, monkeypatch):
    """Whisper fails → any partial output still cleaned up."""
    from listen import transcribe
    monkeypatch.setattr("listen.shutil.which", lambda _: "/usr/local/bin/whisper")
    monkeypatch.setattr("listen.DEFAULT_OUTPUT_DIR", str(tmp_output_dir))

    def fake_run(cmd, **kwargs):
        # Simulate partial write before whisper crashed
        base = os.path.splitext(os.path.basename(sample_audio))[0]
        with open(os.path.join(str(tmp_output_dir), f"{base}.txt"), "w") as f:
            f.write("partial")
        return MagicMock(returncode=1, stderr=b"whisper died mid-transcription")

    monkeypatch.setattr("listen.subprocess.run", fake_run)
    with pytest.raises(RuntimeError):
        transcribe(sample_audio)

    leftovers = list(tmp_output_dir.iterdir())
    assert leftovers == [], f"expected clean output dir after failure, found {leftovers}"


def test_default_output_dir_is_script_relative(monkeypatch):
    """With STT_OUTPUT_DIR unset, default resolves relative to listen.py, not CWD.

    This is the plug-and-play portability guarantee — a bot calling listen.py from
    any CWD must get the same output dir as if it called from the repo root.
    """
    monkeypatch.delenv("STT_OUTPUT_DIR", raising=False)

    import importlib
    import listen
    importlib.reload(listen)

    # Resolve what the script directory should be
    listen_py_dir = os.path.dirname(os.path.abspath(listen.__file__))
    expected = os.path.join(listen_py_dir, "transcripts")

    assert listen.DEFAULT_OUTPUT_DIR == expected, (
        f"Default output dir must be script-relative for portability. "
        f"Got: {listen.DEFAULT_OUTPUT_DIR}, expected: {expected}"
    )


@pytest.mark.slow
def test_transcribes_real_speech(tmp_output_dir, monkeypatch):
    """End-to-end: real whisper CLI transcribes a real speech clip.

    Slow (~5-10s). Skip with: pytest -m 'not slow'
    Requires `whisper` CLI on PATH.
    """
    import importlib
    import listen
    importlib.reload(listen)

    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "hello.wav")
    assert os.path.exists(fixture), f"fixture missing: {fixture}"

    if shutil.which("whisper") is None:
        pytest.skip("whisper CLI not installed")

    transcript = listen.transcribe(fixture).lower()
    # Lenient match — whisper may punctuate or capitalize differently
    assert "hello" in transcript or "test" in transcript, (
        f"expected transcript to contain 'hello' or 'test', got: {transcript!r}"
    )
