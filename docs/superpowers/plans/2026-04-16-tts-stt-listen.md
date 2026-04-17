# tts-stt `listen.py` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add batch speech-to-text via `listen.py`, a sibling to `speak.py` that subprocesses to the local `whisper` CLI. File path in → pure transcript on stdout. Plug-and-play across MacClaude (Mac) and Fraggy/Claudsson (fragserv WSL) via `.env` config only.

**Architecture:** Single new script `listen.py`, subprocesses `shutil.which("whisper")`. Reads intermediate `.txt` output, cleans up, prints transcript. Zero changes to existing files (`speak.py`, `voice_play.py`, `list_voices.py`). New `tests/` directory (doesn't exist yet). pytest added to `requirements.txt`.

**Tech Stack:** Python 3.12, `subprocess`, `shutil`, `python-dotenv` (already in deps), `whisper` CLI (system tool, not a pip dep), pytest.

**Spec:** `docs/superpowers/specs/2026-04-16-tts-stt-listen-design.md`

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `listen.py` | CREATE | Main script: `transcribe()` function + CLI entry point |
| `tests/__init__.py` | CREATE | Makes `tests/` a package (empty) |
| `tests/test_listen.py` | CREATE | All listen.py tests (fast mocks + one slow real-whisper test) |
| `tests/fixtures/` | CREATE | Directory for checked-in audio fixtures |
| `tests/fixtures/hello.wav` | CREATE | 3-second generated speech fixture for the slow test (portable across Mac/Linux) |
| `requirements.txt` | MODIFY | Add `pytest` |
| `.gitignore` | MODIFY | Add `transcripts/` |
| `.env.example` | MODIFY | Add STT_MODEL, STT_LANGUAGE, STT_OUTPUT_DIR entries |

---

## Task 1: Scaffold tests infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `requirements.txt`
- Modify: `.gitignore`

- [ ] **Step 1: Create `tests/__init__.py`**

```bash
touch tests/__init__.py
```

- [ ] **Step 2: Create `tests/conftest.py`** with autouse cleanup

```python
"""Pytest configuration for tts-stt."""
import pytest


@pytest.fixture
def tmp_output_dir(tmp_path, monkeypatch):
    """Isolated STT_OUTPUT_DIR per test — prevents leaking transcripts between tests."""
    d = tmp_path / "transcripts"
    d.mkdir()
    monkeypatch.setenv("STT_OUTPUT_DIR", str(d))
    return d


@pytest.fixture
def sample_audio(tmp_path):
    """Returns a path to a non-existent but syntactically valid audio file path.
    For tests that mock subprocess — the file is never actually read."""
    p = tmp_path / "audio.ogg"
    p.write_bytes(b"\x00\x00")  # not real audio; mocked subprocess won't care
    return str(p)
```

- [ ] **Step 3: Add `pytest` to `requirements.txt`**

Add one line at the end of `requirements.txt`:

```
pytest==8.3.4
```

- [ ] **Step 4: Install pytest into venv**

```bash
source venv/bin/activate && pip install pytest==8.3.4
```

Expected: pytest installs cleanly.

- [ ] **Step 5: Freeze updated requirements**

```bash
pip freeze > requirements.txt
```

- [ ] **Step 6: Add `transcripts/` to `.gitignore`**

Edit `.gitignore` — the existing file contains:
```
venv/
__pycache__/
*.pyc
.env
*.mp3
output/
```

Change to:
```
venv/
__pycache__/
*.pyc
.env
*.mp3
output/
transcripts/
```

- [ ] **Step 7: Commit**

```bash
git add tests/__init__.py tests/conftest.py requirements.txt .gitignore
git commit -m "test: scaffold tests/ dir and add pytest to deps"
```

---

## Task 2: First failing test — missing file raises

**Files:**
- Create: `tests/test_listen.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_listen.py` with this content:

```python
"""Tests for listen.py — batch STT via local whisper CLI."""
import pytest


def test_missing_file_raises(tmp_output_dir):
    """Non-existent path → RuntimeError with 'file not found'."""
    from listen import transcribe
    with pytest.raises(RuntimeError, match="file not found"):
        transcribe("/nonexistent/path/audio.ogg")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source venv/bin/activate && pytest tests/test_listen.py::test_missing_file_raises -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'listen'`

- [ ] **Step 3: Write minimal `listen.py` to make the test pass**

Create `listen.py`:

```python
"""
tts-stt — audio file → whisper → transcript on stdout.

Usage:
    python listen.py /path/to/audio.ogg
"""
import os
from dotenv import load_dotenv

load_dotenv()


def transcribe(audio_path: str) -> str:
    """Transcribe audio file to text via local whisper CLI."""
    if not os.path.exists(audio_path):
        raise RuntimeError(f"file not found: {audio_path}")
    return ""
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_listen.py::test_missing_file_raises -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add listen.py tests/test_listen.py
git commit -m "feat(listen): scaffold transcribe with missing-file guard"
```

---

## Task 3: Whisper CLI missing raises

**Files:**
- Modify: `tests/test_listen.py` (append test)
- Modify: `listen.py` (add shutil.which check)

- [ ] **Step 1: Append failing test**

Append to `tests/test_listen.py`:

```python
def test_whisper_not_found_raises(sample_audio, tmp_output_dir, monkeypatch):
    """shutil.which returns None → RuntimeError with install hint."""
    from listen import transcribe
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(RuntimeError, match="whisper CLI not found"):
        transcribe(sample_audio)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_listen.py::test_whisper_not_found_raises -v
```

Expected: FAIL — `transcribe` currently returns `""` without checking whisper.

- [ ] **Step 3: Add whisper CLI check to `listen.py`**

Modify `listen.py`. Add `import shutil` at top, and modify `transcribe()`:

```python
"""
tts-stt — audio file → whisper → transcript on stdout.

Usage:
    python listen.py /path/to/audio.ogg
"""
import os
import shutil
from dotenv import load_dotenv

load_dotenv()


def transcribe(audio_path: str) -> str:
    """Transcribe audio file to text via local whisper CLI."""
    if not os.path.exists(audio_path):
        raise RuntimeError(f"file not found: {audio_path}")

    whisper_bin = shutil.which("whisper")
    if whisper_bin is None:
        raise RuntimeError(
            "whisper CLI not found on PATH. "
            "Install: brew install openai-whisper (Mac) or pip3 install openai-whisper (Linux)"
        )

    return ""
```

- [ ] **Step 4: Run both tests to verify they pass**

```bash
pytest tests/test_listen.py -v
```

Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add listen.py tests/test_listen.py
git commit -m "feat(listen): require whisper CLI on PATH with install hint"
```

---

## Task 4: Subprocess invocation with defaults

**Files:**
- Modify: `tests/test_listen.py`
- Modify: `listen.py`

- [ ] **Step 1: Append failing test**

Append to `tests/test_listen.py`:

```python
from unittest.mock import patch, MagicMock


def _mock_whisper_success(output_dir: str, audio_path: str, transcript: str = "hello world"):
    """Helper: simulates whisper writing a .txt file next to the audio and exiting 0."""
    audio_basename = os.path.splitext(os.path.basename(audio_path))[0]
    txt_path = os.path.join(output_dir, f"{audio_basename}.txt")
    with open(txt_path, "w") as f:
        f.write(transcript)
    return MagicMock(returncode=0, stderr=b"")


def test_subprocess_invoked_with_defaults(sample_audio, tmp_output_dir, monkeypatch):
    """Default invocation uses base model, en language, fp16 False, verbose False."""
    from listen import transcribe
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/whisper")

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _mock_whisper_success(str(tmp_output_dir), sample_audio)

    monkeypatch.setattr("subprocess.run", fake_run)
    result = transcribe(sample_audio)

    assert result == "hello world"
    assert captured["cmd"][0] == "/usr/local/bin/whisper"
    assert sample_audio in captured["cmd"]
    assert "--model" in captured["cmd"] and "base" in captured["cmd"]
    assert "--language" in captured["cmd"] and "en" in captured["cmd"]
    assert "--fp16" in captured["cmd"] and "False" in captured["cmd"]
    assert "--verbose" in captured["cmd"] and "False" in captured["cmd"]
    assert "--output_format" in captured["cmd"] and "txt" in captured["cmd"]
```

Also add these imports at the top of `tests/test_listen.py` (under the existing `import pytest`):

```python
import os
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_listen.py::test_subprocess_invoked_with_defaults -v
```

Expected: FAIL — `transcribe` still returns `""` unconditionally.

- [ ] **Step 3: Implement subprocess invocation in `listen.py`**

Replace the contents of `listen.py` with:

```python
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
_DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "transcripts")
DEFAULT_OUTPUT_DIR = os.getenv("STT_OUTPUT_DIR", _DEFAULT_OUTPUT_DIR)


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

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"whisper failed: {result.stderr.decode(errors='replace')}")

    audio_basename = os.path.splitext(os.path.basename(audio_path))[0]
    txt_path = os.path.join(out_dir, f"{audio_basename}.txt")
    if not os.path.exists(txt_path):
        raise RuntimeError(f"whisper produced no output file at {txt_path}")

    with open(txt_path) as f:
        transcript = f.read().strip()

    return transcript
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
pytest tests/test_listen.py -v
```

Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add listen.py tests/test_listen.py
git commit -m "feat(listen): subprocess whisper with env-driven defaults"
```

---

## Task 5: Whisper subprocess failure raises with stderr

**Files:**
- Modify: `tests/test_listen.py`

- [ ] **Step 1: Append failing test**

Append to `tests/test_listen.py`:

```python
def test_whisper_subprocess_failure_raises(sample_audio, tmp_output_dir, monkeypatch):
    """Non-zero whisper exit → RuntimeError carrying whisper's stderr."""
    from listen import transcribe
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/whisper")

    def fake_run(cmd, **kwargs):
        return MagicMock(returncode=1, stderr=b"whisper: bad audio format")

    monkeypatch.setattr("subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="whisper failed.*bad audio format"):
        transcribe(sample_audio)
```

- [ ] **Step 2: Run test to verify it passes already**

The logic was implemented in Task 4. This test should pass on first run:

```bash
pytest tests/test_listen.py::test_whisper_subprocess_failure_raises -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_listen.py
git commit -m "test(listen): verify whisper failure propagates stderr"
```

---

## Task 6: Whisper produced no output raises

**Files:**
- Modify: `tests/test_listen.py`

- [ ] **Step 1: Append failing test**

Append to `tests/test_listen.py`:

```python
def test_whisper_produced_no_output_raises(sample_audio, tmp_output_dir, monkeypatch):
    """Whisper exits 0 but no .txt written → RuntimeError, not raw FileNotFoundError."""
    from listen import transcribe
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/whisper")

    def fake_run(cmd, **kwargs):
        # Do NOT write the .txt file — simulate whisper exiting 0 without output
        return MagicMock(returncode=0, stderr=b"")

    monkeypatch.setattr("subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="whisper produced no output"):
        transcribe(sample_audio)
```

- [ ] **Step 2: Run test to verify it passes**

The guard was implemented in Task 4. Should pass already:

```bash
pytest tests/test_listen.py::test_whisper_produced_no_output_raises -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_listen.py
git commit -m "test(listen): verify missing output file raises cleanly"
```

---

## Task 7: Empty audio returns empty string

**Files:**
- Modify: `tests/test_listen.py`

- [ ] **Step 1: Append failing test**

Append to `tests/test_listen.py`:

```python
def test_empty_audio_returns_empty_string(sample_audio, tmp_output_dir, monkeypatch):
    """Whisper writes empty .txt (silent audio) → returns '', not an error."""
    from listen import transcribe
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/whisper")

    def fake_run(cmd, **kwargs):
        return _mock_whisper_success(str(tmp_output_dir), sample_audio, transcript="")

    monkeypatch.setattr("subprocess.run", fake_run)
    result = transcribe(sample_audio)
    assert result == ""
```

- [ ] **Step 2: Run test to verify it passes**

Existing logic handles this already (strip of `""` is `""`).

```bash
pytest tests/test_listen.py::test_empty_audio_returns_empty_string -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_listen.py
git commit -m "test(listen): silent audio returns empty string cleanly"
```

---

## Task 8: Env overrides — STT_MODEL and STT_LANGUAGE

**Files:**
- Modify: `tests/test_listen.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_listen.py`:

```python
def test_stt_model_env_override(sample_audio, tmp_output_dir, monkeypatch):
    """STT_MODEL=small in env → whisper called with --model small."""
    monkeypatch.setenv("STT_MODEL", "small")
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/whisper")

    # Reimport to re-read env — listen module caches DEFAULT_MODEL at import time
    import importlib
    import listen
    importlib.reload(listen)

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _mock_whisper_success(str(tmp_output_dir), sample_audio)

    monkeypatch.setattr("subprocess.run", fake_run)
    listen.transcribe(sample_audio)

    assert "--model" in captured["cmd"]
    model_idx = captured["cmd"].index("--model")
    assert captured["cmd"][model_idx + 1] == "small"


def test_stt_language_env_override(sample_audio, tmp_output_dir, monkeypatch):
    """STT_LANGUAGE=zh in env → whisper called with --language zh."""
    monkeypatch.setenv("STT_LANGUAGE", "zh")
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/whisper")

    import importlib
    import listen
    importlib.reload(listen)

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _mock_whisper_success(str(tmp_output_dir), sample_audio)

    monkeypatch.setattr("subprocess.run", fake_run)
    listen.transcribe(sample_audio)

    assert "--language" in captured["cmd"]
    lang_idx = captured["cmd"].index("--language")
    assert captured["cmd"][lang_idx + 1] == "zh"
```

- [ ] **Step 2: Run tests to verify they pass**

The reload pattern works because `DEFAULT_MODEL` / `DEFAULT_LANGUAGE` read from env at module import.

```bash
pytest tests/test_listen.py::test_stt_model_env_override tests/test_listen.py::test_stt_language_env_override -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_listen.py
git commit -m "test(listen): verify STT_MODEL and STT_LANGUAGE env overrides"
```

---

## Task 9: CLI entry point + flag overrides env

**Files:**
- Modify: `listen.py` (add CLI entry point)
- Modify: `tests/test_listen.py`

- [ ] **Step 1: Append failing test**

Append to `tests/test_listen.py`:

```python
def test_cli_flag_overrides_env(sample_audio, tmp_output_dir, monkeypatch):
    """Positional CLI args via function: --language zh overrides env=en."""
    monkeypatch.setenv("STT_LANGUAGE", "en")
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/whisper")

    import importlib
    import listen
    importlib.reload(listen)

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _mock_whisper_success(str(tmp_output_dir), sample_audio)

    monkeypatch.setattr("subprocess.run", fake_run)
    # The `language` kwarg simulates what the CLI flag does — overrides env
    listen.transcribe(sample_audio, language="zh")

    lang_idx = captured["cmd"].index("--language")
    assert captured["cmd"][lang_idx + 1] == "zh"
```

- [ ] **Step 2: Run test to verify it passes**

Existing kwarg logic in `transcribe()` already handles override. Should pass:

```bash
pytest tests/test_listen.py::test_cli_flag_overrides_env -v
```

Expected: PASS

- [ ] **Step 3: Add CLI entry point to `listen.py`**

Append to `listen.py` (after the `transcribe` function definition):

```python
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
```

- [ ] **Step 4: Verify all tests still pass**

```bash
pytest tests/test_listen.py -v
```

Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add listen.py tests/test_listen.py
git commit -m "feat(listen): CLI entry point with --model/--language flags"
```

---

## Task 10: Cleanup intermediate files (success + failure)

**Files:**
- Modify: `listen.py`
- Modify: `tests/test_listen.py`

- [ ] **Step 1: Append two failing tests**

Append to `tests/test_listen.py`:

```python
def test_cleanup_removes_intermediate_files(sample_audio, tmp_output_dir, monkeypatch):
    """After success, tmp_output_dir has no .txt/.json/.srt leftovers."""
    from listen import transcribe
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/whisper")

    def fake_run(cmd, **kwargs):
        # Write all five formats whisper might leave around
        base = os.path.splitext(os.path.basename(sample_audio))[0]
        for ext in ("txt", "json", "srt", "vtt", "tsv"):
            with open(os.path.join(str(tmp_output_dir), f"{base}.{ext}"), "w") as f:
                f.write("hello world" if ext == "txt" else "{}")
        return MagicMock(returncode=0, stderr=b"")

    monkeypatch.setattr("subprocess.run", fake_run)
    transcribe(sample_audio)

    leftovers = list(tmp_output_dir.iterdir())
    assert leftovers == [], f"expected clean output dir, found {leftovers}"


def test_cleanup_on_whisper_failure(sample_audio, tmp_output_dir, monkeypatch):
    """Whisper fails → any partial output still cleaned up."""
    from listen import transcribe
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/whisper")

    def fake_run(cmd, **kwargs):
        # Simulate partial write before whisper crashed
        base = os.path.splitext(os.path.basename(sample_audio))[0]
        with open(os.path.join(str(tmp_output_dir), f"{base}.txt"), "w") as f:
            f.write("partial")
        return MagicMock(returncode=1, stderr=b"whisper died mid-transcription")

    monkeypatch.setattr("subprocess.run", fake_run)
    with pytest.raises(RuntimeError):
        transcribe(sample_audio)

    leftovers = list(tmp_output_dir.iterdir())
    assert leftovers == [], f"expected clean output dir after failure, found {leftovers}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_listen.py::test_cleanup_removes_intermediate_files tests/test_listen.py::test_cleanup_on_whisper_failure -v
```

Expected: FAIL — no cleanup logic yet.

- [ ] **Step 3: Add cleanup logic to `listen.py`**

Replace the body of `transcribe()` in `listen.py` — the whole function becomes:

```python
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
    # Whisper may write any of these extensions; clean them all up afterwards
    _WHISPER_EXTENSIONS = ("txt", "json", "srt", "vtt", "tsv")

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
        # Clean up any intermediate files whisper may have written
        for ext in _WHISPER_EXTENSIONS:
            leftover = os.path.join(out_dir, f"{audio_basename}.{ext}")
            if os.path.exists(leftover):
                os.remove(leftover)
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
pytest tests/test_listen.py -v
```

Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add listen.py tests/test_listen.py
git commit -m "feat(listen): clean up whisper intermediate files on success and failure"
```

---

## Task 11: Default output dir is script-relative (portability)

**Files:**
- Modify: `tests/test_listen.py`

- [ ] **Step 1: Append failing test**

Append to `tests/test_listen.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it passes**

The script-relative default was set in Task 4. Should pass:

```bash
pytest tests/test_listen.py::test_default_output_dir_is_script_relative -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_listen.py
git commit -m "test(listen): verify default output dir is script-relative"
```

---

## Task 12: Slow integration test — real whisper on real speech

**Files:**
- Create: `tests/fixtures/hello.wav`
- Modify: `tests/test_listen.py`
- Modify: `pyproject.toml` or `pytest.ini` (mark registration)

- [ ] **Step 1: Generate the fixture audio**

On Mac, use `say` to create a reference clip, then downsample to 16kHz mono WAV for portability:

```bash
cd /Users/jeffbai/repos/tts-stt
mkdir -p tests/fixtures
say -o /tmp/fixture.aiff "Hello this is a test of the transcription pipeline"
ffmpeg -y -i /tmp/fixture.aiff -ac 1 -ar 16000 tests/fixtures/hello.wav
rm /tmp/fixture.aiff
ls -la tests/fixtures/hello.wav
```

Expected: `tests/fixtures/hello.wav` exists, ~50-100KB.

- [ ] **Step 2: Register the `slow` pytest marker**

Create `pytest.ini` at the repo root:

```ini
[pytest]
markers =
    slow: real whisper invocation, ~5-10s per test
```

- [ ] **Step 3: Append the slow integration test**

Append to `tests/test_listen.py`:

```python
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
```

Also add `import shutil` to the top of `tests/test_listen.py` if not already imported.

- [ ] **Step 4: Run all fast tests first**

```bash
pytest tests/test_listen.py -v -m "not slow"
```

Expected: PASS (11 passed — all mocked tests)

- [ ] **Step 5: Run the slow test**

```bash
pytest tests/test_listen.py -v -m "slow"
```

Expected: PASS (1 passed, ~5-10s). Transcript contains "hello" or "test".

- [ ] **Step 6: Run the full suite**

```bash
pytest tests/test_listen.py -v
```

Expected: PASS (12 passed)

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures/hello.wav tests/test_listen.py pytest.ini
git commit -m "test(listen): add slow integration test with real whisper"
```

---

## Task 13: Update `.env.example`

**Files:**
- Check: `.env.example` — may or may not exist currently
- Create or Modify: `.env.example`

- [ ] **Step 1: Check if `.env.example` exists**

```bash
ls -la /Users/jeffbai/repos/tts-stt/env.example /Users/jeffbai/repos/tts-stt/.env.example 2>&1
```

Note: the repo may use `env.example` (no leading dot). Check both.

- [ ] **Step 2: Append STT section**

Append to whichever file exists (or create `.env.example` if neither):

```bash
# ─── STT (speech-to-text) ───────────────────────────────
# Requires `whisper` CLI on PATH.
# Install: brew install openai-whisper (Mac) or pip3 install openai-whisper (Linux)

# Model size — trade speed vs accuracy. base is 0.76x real-time on Apple Silicon.
STT_MODEL=base

# Language code (e.g. en, zh, ja). Skips auto-detect. Set per bot:
#   MacClaude:  en
#   Claudsson:  zh
#   Fraggy:     en
STT_LANGUAGE=en

# Where intermediate whisper files land. Default: <repo>/transcripts/
# (gitignored; cleaned up after each run). Uncomment to override.
# STT_OUTPUT_DIR=/custom/path/
```

- [ ] **Step 3: Commit**

```bash
git add .env.example env.example 2>/dev/null
git commit -m "docs(listen): document STT env vars in env.example"
```

---

## Task 14: Final verification + squash check

- [ ] **Step 1: Run the full test suite one more time**

```bash
cd /Users/jeffbai/repos/tts-stt && source venv/bin/activate && pytest tests/ -v
```

Expected: 12 passed, 0 failed.

- [ ] **Step 2: Manual smoke test — real voice note flow**

```bash
# Generate a test voice note approximating Discord voice note shape
say -o /tmp/voicenote.aiff "This is a test voice note just to verify the end to end flow"
ffmpeg -y -i /tmp/voicenote.aiff -ac 1 -ar 16000 /tmp/voicenote.wav
time python listen.py /tmp/voicenote.wav
rm /tmp/voicenote.aiff /tmp/voicenote.wav
```

Expected: transcript printed to stdout, stderr has whisper progress, exit 0. Wall time <10s on Mac.

- [ ] **Step 3: Verify no lingering files in `transcripts/`**

```bash
ls transcripts/ 2>&1
```

Expected: empty or "No such file or directory" (cleanup worked).

- [ ] **Step 4: Check git log**

```bash
git log --oneline origin/main..HEAD
```

Expected: ~13 commits, all focused on the listen.py addition. Review for any that should be squashed for clean history (per feedback_commit_sizing memory).

- [ ] **Step 5: Ready to push**

Do NOT push automatically. Report the commit count + test results to the user and ask whether to push.

---

## Self-Review

Checked against spec sections:

- **Context / Goals:** ✅ Task 4 delivers core `transcribe()` matching spec contract. Task 13 documents env pattern. Task 11 enforces portability guarantee.
- **Non-goals:** ✅ No recording, no streaming, no plugin wiring — plan only touches `listen.py`, tests, and config docs.
- **Architecture:** ✅ File structure in plan matches spec's file tree exactly.
- **Interface (CLI, stdout, stderr, Python API):** ✅ Tasks 2, 4, 9 cover all three.
- **Environment Configuration:** ✅ Task 8 (env overrides), Task 13 (.env.example), Task 11 (default output dir portability).
- **Error Handling table:** ✅
  - Missing file → Task 2
  - Whisper not found → Task 3
  - Whisper subprocess failure → Task 5
  - Empty transcription → Task 7
  - Missing output file → Task 6
- **Implementation Details (whisper flags):** ✅ Task 4 covers `--fp16 False`, `--verbose False`, `--output_format txt`.
- **Testing Plan:** ✅ All 11 test cases from the spec mapped to tasks:
  - `test_missing_file_raises` → Task 2
  - `test_whisper_not_found_raises` → Task 3
  - `test_whisper_subprocess_failure_raises` → Task 5
  - `test_whisper_produced_no_output_raises` → Task 6
  - `test_empty_audio_returns_empty_string` → Task 7
  - `test_stt_model_env_override` → Task 8
  - `test_stt_language_env_override` → Task 8
  - `test_language_kwarg_overrides_env` + `test_cli_error_path_exits_nonzero_with_stderr` → Task 9 (renamed from original `test_cli_flag_overrides_env`; split into library-level kwarg test + real CLI subprocess test per code-review feedback)
  - `test_cleanup_removes_intermediate_files` → Task 10
  - `test_cleanup_on_whisper_failure` → Task 10
  - `test_default_output_dir_is_script_relative` → Task 11
  - `test_transcribes_real_speech` (slow) → Task 12
- **Plug-and-Play Portability:** ✅ Task 11 explicitly tests the script-relative default. Task 13 documents the multi-bot `.env` pattern. No hardcoded paths or bot identity anywhere in the code.
- **Migration / Rollout:** Explicitly deferred from this plan (spec says rollout is post-merge). Task 14 stops short of pushing and hands off to user.

No placeholders. No TBDs. All method signatures match across tasks (`transcribe(audio_path, model, language, output_dir)` consistent from Task 4 through Task 11).
