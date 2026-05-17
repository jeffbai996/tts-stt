"""Tests for speak.py — text-to-speech via ElevenLabs with CJK auto-routing."""
import os
import subprocess

import pytest
from unittest.mock import MagicMock


def _mock_tts_success(audio_bytes: bytes = b"\xff\xfb\x90\x00fake mp3 data"):
    """Helper: builds a MagicMock that mimics a successful ElevenLabs response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.content = audio_bytes
    resp.text = ""
    resp.raise_for_status = MagicMock()
    return resp


def _mock_tts_error(status_code: int, body: str):
    """Helper: builds a MagicMock that mimics an HTTP error response."""
    import requests
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = b""
    resp.text = body
    # raise_for_status() should raise HTTPError; speak.py catches it and re-raises
    # as RuntimeError that includes resp.text.
    err = requests.exceptions.HTTPError(f"{status_code} error")
    err.response = resp
    resp.raise_for_status = MagicMock(side_effect=err)
    return resp


def test_cjk_detection_threshold():
    """_is_cjk: pure ASCII False; majority CJK True; minority CJK below threshold; empty False."""
    from speak import _is_cjk

    assert _is_cjk("hello world") is False
    assert _is_cjk("你好世界") is True
    # "hi 你" = 3 non-space chars, 1 CJK → 1/3 ≈ 0.33 > 0.3 default threshold → True
    assert _is_cjk("hi 你") is True
    # Drop just below threshold: "hii 你" = 4 non-space chars, 1 CJK = 0.25 < 0.3 → False
    assert _is_cjk("hii 你") is False
    assert _is_cjk("") is False


def test_cjk_text_routes_to_zh_voice(monkeypatch):
    """Majority-CJK text + TTS_VOICE_ID_ZH set → API URL contains the zh voice id."""
    import speak
    monkeypatch.setattr("speak.DEFAULT_VOICE_ID_ZH", "zh_voice_abc123")

    captured = {}

    def fake_post(url, headers=None, json=None):
        captured["url"] = url
        captured["json"] = json
        return _mock_tts_success()

    monkeypatch.setattr("speak.requests.post", fake_post)
    # Avoid invoking ffmpeg
    monkeypatch.setattr("speak.TTS_SPEED", 1.0)

    speak.synthesize("你好世界,这是一个测试")

    assert "zh_voice_abc123" in captured["url"]
    # And: no accent tag prepended to CJK text
    assert not captured["json"]["text"].startswith("[")


def test_cjk_text_no_zh_voice_falls_back(monkeypatch):
    """Majority-CJK text but TTS_VOICE_ID_ZH unset → falls back to default voice."""
    import speak
    monkeypatch.setattr("speak.DEFAULT_VOICE_ID_ZH", None)

    captured = {}

    def fake_post(url, headers=None, json=None):
        captured["url"] = url
        return _mock_tts_success()

    monkeypatch.setattr("speak.requests.post", fake_post)
    monkeypatch.setattr("speak.TTS_SPEED", 1.0)

    speak.synthesize("你好世界")

    assert speak.DEFAULT_VOICE_ID in captured["url"]


def test_explicit_voice_override_wins_over_cjk_routing(monkeypatch):
    """Caller passing voice_id= explicitly wins, even for majority-CJK text."""
    import speak
    monkeypatch.setattr("speak.DEFAULT_VOICE_ID_ZH", "zh_voice_abc123")

    captured = {}

    def fake_post(url, headers=None, json=None):
        captured["url"] = url
        return _mock_tts_success()

    monkeypatch.setattr("speak.requests.post", fake_post)
    monkeypatch.setattr("speak.TTS_SPEED", 1.0)

    speak.synthesize("你好世界", voice_id="explicit_override_voice_xyz")

    assert "explicit_override_voice_xyz" in captured["url"]
    assert "zh_voice_abc123" not in captured["url"]


def test_accent_tag_prepended(monkeypatch):
    """Non-CJK text gets ACCENT_TAG prepended in the API payload's text field."""
    import speak
    monkeypatch.setattr("speak.ACCENT_TAG", "[Scottish accent]")

    captured = {}

    def fake_post(url, headers=None, json=None):
        captured["json"] = json
        return _mock_tts_success()

    monkeypatch.setattr("speak.requests.post", fake_post)
    monkeypatch.setattr("speak.TTS_SPEED", 1.0)

    speak.synthesize("hello world")

    assert captured["json"]["text"] == "[Scottish accent] hello world"


def test_accent_tag_empty_string_no_prepend(monkeypatch):
    """ACCENT_TAG='' → no tag prepended (the `if ACCENT_TAG and ...` short-circuit holds)."""
    import speak
    monkeypatch.setattr("speak.ACCENT_TAG", "")

    captured = {}

    def fake_post(url, headers=None, json=None):
        captured["json"] = json
        return _mock_tts_success()

    monkeypatch.setattr("speak.requests.post", fake_post)
    monkeypatch.setattr("speak.TTS_SPEED", 1.0)

    speak.synthesize("hello world")

    assert captured["json"]["text"] == "hello world"
    assert not captured["json"]["text"].startswith("[")


def test_accent_tag_skipped_for_cjk(monkeypatch):
    """English-style accent tag never prepended to majority-CJK text."""
    import speak
    monkeypatch.setattr("speak.ACCENT_TAG", "[Scottish accent]")
    monkeypatch.setattr("speak.DEFAULT_VOICE_ID_ZH", None)

    captured = {}

    def fake_post(url, headers=None, json=None):
        captured["json"] = json
        return _mock_tts_success()

    monkeypatch.setattr("speak.requests.post", fake_post)
    monkeypatch.setattr("speak.TTS_SPEED", 1.0)

    speak.synthesize("你好世界")

    assert captured["json"]["text"] == "你好世界"
    assert "Scottish" not in captured["json"]["text"]


def test_accent_tag_skipped_if_text_already_tagged(monkeypatch):
    """Text starting with [anything] doesn't get a second tag prepended."""
    import speak
    monkeypatch.setattr("speak.ACCENT_TAG", "[Scottish accent]")

    captured = {}

    def fake_post(url, headers=None, json=None):
        captured["json"] = json
        return _mock_tts_success()

    monkeypatch.setattr("speak.requests.post", fake_post)
    monkeypatch.setattr("speak.TTS_SPEED", 1.0)

    speak.synthesize("[American accent] hello world")

    # Should be passed through untouched — no double-tagging
    assert captured["json"]["text"] == "[American accent] hello world"
    # And confirm exactly one leading [ ... ] tag
    assert captured["json"]["text"].count("[Scottish") == 0


def test_api_error_includes_response_body(monkeypatch):
    """ElevenLabs 401/500 → RuntimeError carries the response body (no swallowed error)."""
    import speak

    error_body = '{"detail":"invalid_api_key: bad token xyz"}'
    monkeypatch.setattr(
        "speak.requests.post",
        lambda url, headers=None, json=None: _mock_tts_error(401, error_body),
    )

    with pytest.raises(RuntimeError, match="invalid_api_key"):
        speak.synthesize("hello world")


def test_speed_one_skips_ffmpeg(monkeypatch, tmp_path):
    """TTS_SPEED=1.0 → ffmpeg subprocess never invoked; raw temp file returned as-is."""
    import speak
    monkeypatch.setattr("speak.TTS_SPEED", 1.0)
    # Funnel temp files into a clean per-test dir for ease of inspection
    monkeypatch.setattr("speak.OUTPUT_DIR", str(tmp_path))

    monkeypatch.setattr(
        "speak.requests.post",
        lambda url, headers=None, json=None: _mock_tts_success(b"raw_mp3_bytes"),
    )

    subprocess_calls = []

    def fake_run(cmd, **kwargs):
        subprocess_calls.append(cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr("speak.subprocess.run", fake_run)

    path = speak.synthesize("hello world")

    assert subprocess_calls == [], f"expected no ffmpeg call, got: {subprocess_calls}"
    assert os.path.exists(path)
    # Returned file should contain the raw bytes ElevenLabs "returned"
    with open(path, "rb") as f:
        assert f.read() == b"raw_mp3_bytes"


def test_speed_nondefault_runs_ffmpeg(monkeypatch, tmp_path):
    """TTS_SPEED != 1.0 → ffmpeg invoked with atempo= filter; returns ffmpeg output path."""
    import speak
    monkeypatch.setattr("speak.TTS_SPEED", 1.25)
    monkeypatch.setattr("speak.OUTPUT_DIR", str(tmp_path))

    monkeypatch.setattr(
        "speak.requests.post",
        lambda url, headers=None, json=None: _mock_tts_success(b"raw_mp3_bytes"),
    )

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        # Simulate ffmpeg writing the output file (last arg is the output path)
        with open(cmd[-1], "wb") as f:
            f.write(b"sped_up_mp3_bytes")
        return MagicMock(returncode=0)

    monkeypatch.setattr("speak.subprocess.run", fake_run)

    path = speak.synthesize("hello world")

    assert captured["cmd"][0] == "ffmpeg"
    # atempo filter must reflect the speed setting
    assert any("atempo=1.25" in part for part in captured["cmd"]), (
        f"expected atempo=1.25 in ffmpeg args, got: {captured['cmd']}"
    )
    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read() == b"sped_up_mp3_bytes"


def test_ffmpeg_failure_cleans_up_raw_temp(monkeypatch, tmp_path):
    """ffmpeg CalledProcessError → raw temp removed, RuntimeError raised (no leak)."""
    import speak
    monkeypatch.setattr("speak.TTS_SPEED", 1.25)
    monkeypatch.setattr("speak.OUTPUT_DIR", str(tmp_path))

    monkeypatch.setattr(
        "speak.requests.post",
        lambda url, headers=None, json=None: _mock_tts_success(b"raw_mp3_bytes"),
    )

    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1, cmd=cmd, stderr=b"ffmpeg: filter atempo not found"
        )

    monkeypatch.setattr("speak.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="ffmpeg failed.*atempo"):
        speak.synthesize("hello world")

    # No .mp3 files should be left behind in OUTPUT_DIR
    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".mp3"]
    assert leftovers == [], f"expected no leftover mp3s, found: {leftovers}"
