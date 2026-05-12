from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
import requests
from rich.console import Console

from tinymdm_update.commands import cmd_update
from tinymdm_update.config import record_update


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_policy(pid="pol1", name="Test Policy"):
    return {"id": pid, "name": name}

def make_app(aid="app1", name="com.example.app"):
    return {"id": aid, "app_type": "tinymdm_store_app", "name": name}

def make_store_app(aid="app1", version="2.0.0", last_update="2026-04-01 00:00:00"):
    return {"id": aid, "version_name": version, "last_update_date": last_update, "package_name": "com.example.app"}

def mock_response(ok=True, status_code=200):
    resp = MagicMock(spec=requests.Response)
    resp.ok = ok
    resp.status_code = status_code
    return resp

def make_client(policies=None, store_apps=None, policy_app_ids=None, update_ok=True, users=None):
    client = MagicMock()
    client.fetch_policies.return_value = policies or [make_policy()]
    client.fetch_store_apps.return_value = store_apps or [make_store_app()]
    client.fetch_policy_app_ids.return_value = policy_app_ids if policy_app_ids is not None else {"app1"}
    client.fetch_users.return_value = users if users is not None else []
    client.update_policy_app.return_value = mock_response(ok=update_ok, status_code=200 if update_ok else 400)
    return client

def silent_console():
    return Console(quiet=True)


# ---------------------------------------------------------------------------
# needs_update detection
# ---------------------------------------------------------------------------

def test_cmd_update_prechecks_policy_when_store_newer(mocker):
    store_date = datetime(2026, 4, 1)
    last_push = store_date - timedelta(days=10)

    cfg = {
        "watched_policy_ids": ["pol1"],
        "tracked_apps": [make_app()],
        "update_history": {"pol1:app1": last_push.isoformat()},
    }
    client = make_client(store_apps=[make_store_app(last_update="2026-04-01 00:00:00")])

    captured_choices = {}
    def fake_checkbox(prompt, choices):
        captured_choices["choices"] = choices
        m = MagicMock()
        m.ask.return_value = []
        return m
    mocker.patch("questionary.checkbox", side_effect=fake_checkbox)

    cmd_update(client, cfg, silent_console())

    checked = [c for c in captured_choices["choices"] if c.checked]
    assert len(checked) == 1

def test_cmd_update_does_not_precheck_when_store_not_newer(mocker):
    store_date = datetime(2026, 3, 1)
    last_push = store_date + timedelta(days=5)

    cfg = {
        "watched_policy_ids": ["pol1"],
        "tracked_apps": [make_app()],
        "update_history": {"pol1:app1": last_push.isoformat()},
    }
    client = make_client(store_apps=[make_store_app(last_update="2026-03-01 00:00:00")])

    captured_choices = {}
    def fake_checkbox(prompt, choices):
        captured_choices["choices"] = choices
        m = MagicMock()
        m.ask.return_value = []
        return m
    mocker.patch("questionary.checkbox", side_effect=fake_checkbox)

    cmd_update(client, cfg, silent_console())

    checked = [c for c in captured_choices["choices"] if c.checked]
    assert len(checked) == 0


# ---------------------------------------------------------------------------
# History recording
# ---------------------------------------------------------------------------

def test_cmd_update_records_history_on_success(mocker, tmp_path):
    cfg = {
        "watched_policy_ids": ["pol1"],
        "tracked_apps": [make_app()],
    }
    client = make_client(update_ok=True)

    policy_obj = {"policy": make_policy(), "is_installed": True, "last_updated_dt": None, "needs_update": False}
    mocker.patch("questionary.checkbox", return_value=MagicMock(ask=MagicMock(return_value=[policy_obj])))

    config_path = tmp_path / "config.json"
    mocker.patch("tinymdm_update.commands.save_config", lambda cfg, **kw: None)

    cmd_update(client, cfg, silent_console())

    assert "pol1:app1" in cfg.get("update_history", {})

def test_cmd_update_does_not_record_history_on_failure(mocker, tmp_path):
    cfg = {
        "watched_policy_ids": ["pol1"],
        "tracked_apps": [make_app()],
    }
    client = make_client(update_ok=False)

    policy_obj = {"policy": make_policy(), "is_installed": True, "last_updated_dt": None, "needs_update": False}
    mocker.patch("questionary.checkbox", return_value=MagicMock(ask=MagicMock(return_value=[policy_obj])))
    mocker.patch("tinymdm_update.commands.save_config", lambda cfg, **kw: None)

    cmd_update(client, cfg, silent_console())

    assert "pol1:app1" not in cfg.get("update_history", {})


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

def test_cmd_update_returns_1_on_any_failure(mocker):
    cfg = {
        "watched_policy_ids": ["pol1"],
        "tracked_apps": [make_app()],
    }
    client = make_client(update_ok=False)

    policy_obj = {"policy": make_policy(), "is_installed": True, "last_updated_dt": None, "needs_update": False}
    mocker.patch("questionary.checkbox", return_value=MagicMock(ask=MagicMock(return_value=[policy_obj])))
    mocker.patch("tinymdm_update.commands.save_config", lambda cfg, **kw: None)

    result = cmd_update(client, cfg, silent_console())
    assert result == 1

def test_cmd_update_returns_0_on_success(mocker):
    cfg = {
        "watched_policy_ids": ["pol1"],
        "tracked_apps": [make_app()],
    }
    client = make_client(update_ok=True)

    policy_obj = {"policy": make_policy(), "is_installed": True, "last_updated_dt": None, "needs_update": False}
    mocker.patch("questionary.checkbox", return_value=MagicMock(ask=MagicMock(return_value=[policy_obj])))
    mocker.patch("tinymdm_update.commands.save_config", lambda cfg, **kw: None)

    result = cmd_update(client, cfg, silent_console())
    assert result == 0

def test_cmd_update_returns_1_when_no_config(mocker):
    result = cmd_update(MagicMock(), {}, silent_console())
    assert result == 1
