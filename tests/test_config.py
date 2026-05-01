import json
from datetime import datetime
from pathlib import Path

import pytest

from tinymdm_update.config import (
    ConfigError,
    extract_version,
    get_last_update,
    load_config,
    parse_store_date,
    record_update,
    save_config,
)


# ---------------------------------------------------------------------------
# extract_version
# ---------------------------------------------------------------------------

def test_extract_version_prefers_version_name():
    assert extract_version({"version_name": "1.2.3", "version": "old", "version_code": 1}) == "1.2.3"

def test_extract_version_falls_back_to_version():
    assert extract_version({"version": "2.0.0", "version_code": 5}) == "2.0.0"

def test_extract_version_falls_back_to_version_code():
    assert extract_version({"version_code": 42}) == "42"

def test_extract_version_returns_question_mark_when_empty():
    assert extract_version({}) == "?"

def test_extract_version_ignores_zero_version_code():
    assert extract_version({"version_code": 0}) == "?"


# ---------------------------------------------------------------------------
# parse_store_date
# ---------------------------------------------------------------------------

def test_parse_store_date_valid():
    result = parse_store_date("2021-01-19 15:15:16")
    assert result == datetime(2021, 1, 19, 15, 15, 16)

def test_parse_store_date_invalid_format_returns_none():
    assert parse_store_date("19/01/2021") is None

def test_parse_store_date_empty_string_returns_none():
    assert parse_store_date("") is None

def test_parse_store_date_none_returns_none():
    assert parse_store_date(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# get_last_update
# ---------------------------------------------------------------------------

def test_get_last_update_missing_key_returns_none():
    cfg = {"update_history": {}}
    assert get_last_update(cfg, "policy1", "app1") is None

def test_get_last_update_no_history_key_returns_none():
    assert get_last_update({}, "policy1", "app1") is None

def test_get_last_update_returns_datetime():
    ts = datetime(2026, 3, 20, 14, 30, 0)
    cfg = {"update_history": {"policy1:app1": ts.isoformat()}}
    assert get_last_update(cfg, "policy1", "app1") == ts

def test_get_last_update_malformed_timestamp_returns_none():
    cfg = {"update_history": {"policy1:app1": "not-a-date"}}
    assert get_last_update(cfg, "policy1", "app1") is None


# ---------------------------------------------------------------------------
# record_update
# ---------------------------------------------------------------------------

def test_record_update_writes_parseable_iso_timestamp():
    cfg = {}
    before = datetime.now()
    record_update(cfg, "p1", "a1")
    after = datetime.now()
    recorded = datetime.fromisoformat(cfg["update_history"]["p1:a1"])
    assert before <= recorded <= after

def test_record_update_creates_history_key():
    cfg = {}
    record_update(cfg, "policy-abc", "app-xyz")
    assert "policy-abc:app-xyz" in cfg["update_history"]

def test_record_update_preserves_other_history_entries():
    cfg = {"update_history": {"other:app": "2025-01-01T00:00:00"}}
    record_update(cfg, "new", "entry")
    assert "other:app" in cfg["update_history"]


# ---------------------------------------------------------------------------
# load_config / save_config
# ---------------------------------------------------------------------------

def test_load_config_missing_file_returns_empty(tmp_path):
    result = load_config(tmp_path / "nonexistent.json")
    assert result == {}

def test_load_config_reads_valid_json(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"watched_policy_ids": ["abc"]}))
    assert load_config(p) == {"watched_policy_ids": ["abc"]}

def test_load_config_corrupt_json_raises_config_error(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ not valid json")
    with pytest.raises(ConfigError, match="corrupted"):
        load_config(p)

def test_save_config_round_trips(tmp_path):
    p = tmp_path / "config.json"
    cfg = {"watched_policy_ids": ["p1"], "tracked_apps": []}
    save_config(cfg, p)
    assert load_config(p) == cfg

def test_save_config_creates_parent_dirs(tmp_path):
    p = tmp_path / "deep" / "nested" / "config.json"
    save_config({"watched_policy_ids": []}, p)
    assert p.exists()
