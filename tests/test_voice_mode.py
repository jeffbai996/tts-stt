"""Tests for voice_mode pure logic — config parsing, pairing lookup, presence check."""
import json

import pytest

from voice_mode import VoiceModeConfig, allowlisted_present


def write_config(tmp_path, data) -> str:
    p = tmp_path / "voice_mode.json"
    p.write_text(json.dumps(data))
    return str(p)


def test_config_loads_pairs_and_allowlist(tmp_path):
    path = write_config(tmp_path, {
        "allow_user_ids": ["111", 222],
        "pairs": {"1000": "2000", "1001": 2001},
    })
    cfg = VoiceModeConfig.load(path)
    assert cfg.allow_user_ids == {111, 222}
    assert cfg.paired_vc(1000) == 2000
    assert cfg.paired_vc(1001) == 2001


def test_config_token_file_optional(tmp_path):
    path = write_config(tmp_path, {"allow_user_ids": [], "pairs": {}})
    assert VoiceModeConfig.load(path).token_file is None
    path = write_config(tmp_path, {"allow_user_ids": [], "pairs": {}, "token_file": "/x/.env"})
    assert VoiceModeConfig.load(path).token_file == "/x/.env"


def test_paired_vc_returns_none_for_unmapped_channel(tmp_path):
    path = write_config(tmp_path, {"allow_user_ids": ["111"], "pairs": {"1000": "2000"}})
    cfg = VoiceModeConfig.load(path)
    assert cfg.paired_vc(9999) is None


def test_config_missing_keys_raises(tmp_path):
    path = write_config(tmp_path, {"pairs": {}})
    with pytest.raises(ValueError, match="allow_user_ids"):
        VoiceModeConfig.load(path)
    path = write_config(tmp_path, {"allow_user_ids": []})
    with pytest.raises(ValueError, match="pairs"):
        VoiceModeConfig.load(path)


def test_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        VoiceModeConfig.load(str(tmp_path / "nope.json"))


def test_allowlisted_present_true_on_overlap():
    assert allowlisted_present({111, 333}, {111, 222}) is True


def test_allowlisted_present_false_when_no_overlap():
    assert allowlisted_present({333, 444}, {111, 222}) is False


def test_allowlisted_present_false_when_vc_empty():
    assert allowlisted_present(set(), {111, 222}) is False
