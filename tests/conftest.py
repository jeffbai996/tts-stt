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
