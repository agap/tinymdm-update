from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
import requests
from rich.console import Console

from tinymdm_update.commands import cmd_setup, cmd_update
from tinymdm_update.config import record_update


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_policy(pid="pol1", name="Test Policy"):
    return {"id": pid, "name": name}

def make_app(aid="app1", name="com.example.app"):
    return {"id": aid, "app_type": "tinymdm_store_app", "name": name}

def make_store_app(aid="app1", version="2.0.0", last_update="2026-04-01 00:00:00", package_name="com.example.app"):
    return {"id": aid, "version_name": version, "last_update_date": last_update, "package_name": package_name}

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


def choice_title(choice):
    """Flatten a questionary Choice title into plain text.

    Update-picker titles are lists of (style, text) tuples so the status
    icon can be colored; plain strings are used elsewhere.
    """
    if isinstance(choice.title, str):
        return choice.title
    return "".join(text for _, text in choice.title)


# ---------------------------------------------------------------------------
# needs_update detection
# ---------------------------------------------------------------------------

def test_cmd_update_flags_policy_when_store_newer(mocker):
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

    flagged = [c for c in captured_choices["choices"] if c.value["needs_update"]]
    assert len(flagged) == 1
    assert "↑" in choice_title(flagged[0])
    # Nothing is ever preselected; the ↑ marker is the only signal.
    assert not any(c.checked for c in captured_choices["choices"])


def test_cmd_update_does_not_flag_when_store_not_newer(mocker):
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

    flagged = [c for c in captured_choices["choices"] if c.value["needs_update"]]
    assert len(flagged) == 0
    assert "✓" in choice_title(captured_choices["choices"][0])
    assert not any(c.checked for c in captured_choices["choices"])


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


# ---------------------------------------------------------------------------
# Fetch efficiency — store catalog and policy app-ids should be fetched once
# ---------------------------------------------------------------------------

def _checkbox_mock(first_answer, later_answer=None, record=None):
    """Mock questionary.checkbox so the first call returns first_answer and
    every subsequent call returns later_answer (default []). If record is a
    list, each call's choices are appended to it."""
    calls = {"n": 0}

    def factory(prompt, choices):
        calls["n"] += 1
        if record is not None:
            record.append(choices)
        result = first_answer if calls["n"] == 1 else (later_answer or [])
        return MagicMock(ask=MagicMock(return_value=result))

    return factory


def test_store_catalog_fetched_once_across_multiple_apps(mocker):
    apps = [make_app("app1"), make_app("app2"), make_app("app3")]
    cfg = {
        "watched_policy_ids": ["pol1", "pol2"],
        "tracked_apps": apps,
    }
    client = make_client(
        policies=[make_policy("pol1"), make_policy("pol2")],
        store_apps=[make_store_app("app1"), make_store_app("app2"), make_store_app("app3")],
    )

    mocker.patch("questionary.checkbox", side_effect=_checkbox_mock(apps))
    mocker.patch("tinymdm_update.commands.save_config", lambda cfg, **kw: None)

    cmd_update(client, cfg, silent_console())

    assert client.fetch_store_apps.call_count == 1


def test_policy_app_ids_fetched_once_per_policy(mocker):
    apps = [make_app("app1"), make_app("app2")]
    cfg = {
        "watched_policy_ids": ["pol1", "pol2", "pol3"],
        "tracked_apps": apps,
    }
    client = make_client(
        policies=[make_policy("pol1"), make_policy("pol2"), make_policy("pol3")],
        store_apps=[make_store_app("app1"), make_store_app("app2")],
    )

    mocker.patch("questionary.checkbox", side_effect=_checkbox_mock(apps))
    mocker.patch("tinymdm_update.commands.save_config", lambda cfg, **kw: None)

    cmd_update(client, cfg, silent_console())

    assert client.fetch_policy_app_ids.call_count == 3
    called_pids = {call.args[0] for call in client.fetch_policy_app_ids.call_args_list}
    assert called_pids == {"pol1", "pol2", "pol3"}


def test_fetch_users_failure_does_not_abort(mocker):
    cfg = {
        "watched_policy_ids": ["pol1"],
        "tracked_apps": [make_app()],
    }
    client = make_client()
    client.fetch_users.side_effect = requests.HTTPError("boom")

    captured_choices = {}
    def fake_checkbox(prompt, choices):
        captured_choices["choices"] = choices
        return MagicMock(ask=MagicMock(return_value=[]))
    mocker.patch("questionary.checkbox", side_effect=fake_checkbox)
    mocker.patch("tinymdm_update.commands.save_config", lambda cfg, **kw: None)

    cmd_update(client, cfg, silent_console())

    assert "choices" in captured_choices


def test_fetch_policy_app_ids_failure_falls_back_to_empty(mocker):
    cfg = {
        "watched_policy_ids": ["pol1"],
        "tracked_apps": [make_app()],
    }
    client = make_client()
    client.fetch_policy_app_ids.side_effect = requests.HTTPError("boom")

    captured_choices = {}
    def fake_checkbox(prompt, choices):
        captured_choices["choices"] = choices
        return MagicMock(ask=MagicMock(return_value=[]))
    mocker.patch("questionary.checkbox", side_effect=fake_checkbox)
    mocker.patch("tinymdm_update.commands.save_config", lambda cfg, **kw: None)

    cmd_update(client, cfg, silent_console())

    # The single policy should still render, marked as "not installed".
    assert len(captured_choices["choices"]) == 1


def test_user_counts_aggregated_per_policy(mocker):
    cfg = {
        "watched_policy_ids": ["pol1", "pol2"],
        "tracked_apps": [make_app()],
    }
    client = make_client(
        policies=[make_policy("pol1", "Policy One"), make_policy("pol2", "Policy Two")],
        users=[
            {"id": "u1", "policy_id": "pol1"},
            {"id": "u2", "policy_id": "pol1"},
            {"id": "u3", "policy_id": "pol2"},
            {"id": "u4", "policy_id": None},
        ],
    )

    captured_choices = {}
    def fake_checkbox(prompt, choices):
        captured_choices["choices"] = choices
        return MagicMock(ask=MagicMock(return_value=[]))
    mocker.patch("questionary.checkbox", side_effect=fake_checkbox)
    mocker.patch("tinymdm_update.commands.save_config", lambda cfg, **kw: None)

    cmd_update(client, cfg, silent_console())

    titles = [choice_title(c) for c in captured_choices["choices"]]
    assert any("2 users" in t and "Policy One" in t for t in titles)
    assert any("1 user " in t and "Policy Two" in t for t in titles)


# ---------------------------------------------------------------------------
# setup --package filtering
# ---------------------------------------------------------------------------

def _setup_client(policy_apps, store_apps=None):
    """policy_apps maps policy id -> set of app ids installed in it."""
    client = make_client(
        policies=[make_policy(pid, f"Policy {pid}") for pid in policy_apps],
        store_apps=store_apps or [make_store_app("app1"), make_store_app("app2", package_name="com.other.app")],
    )
    client.fetch_policy_app_ids.side_effect = lambda pid: policy_apps[pid]
    return client


def _capture_setup_checkboxes(mocker, policy_answer=(), app_answer=()):
    calls = []
    mocker.patch(
        "questionary.checkbox",
        side_effect=_checkbox_mock(list(policy_answer), list(app_answer), record=calls),
    )
    return calls


def test_setup_package_filters_policies(mocker):
    client = _setup_client({"pol1": {"app1"}, "pol2": {"app2"}, "pol3": {"app1", "app2"}})
    calls = _capture_setup_checkboxes(mocker)

    rc = cmd_setup(client, {}, silent_console(), package="com.example.app")

    assert rc == 0
    assert [c.value for c in calls[0]] == ["pol1", "pol3"]
    assert client.fetch_policy_app_ids.call_count == 3


def test_setup_package_marks_new_policies_and_keeps_watched(mocker):
    client = _setup_client({"pol1": {"app1"}, "pol2": {"app2"}, "pol3": {"app1"}})
    calls = _capture_setup_checkboxes(mocker)
    cfg = {"watched_policy_ids": ["pol1", "pol2"], "tracked_apps": []}

    cmd_setup(client, cfg, silent_console(), package="com.example.app")

    choices = {c.value: c for c in calls[0]}
    assert set(choices) == {"pol1", "pol2", "pol3"}
    assert choices["pol1"].checked and choices["pol2"].checked and not choices["pol3"].checked
    assert "(new)" in choices["pol3"].title
    assert "(new)" not in choices["pol1"].title
    assert "(package not installed)" in choices["pol2"].title


def test_setup_package_prechecks_app_and_uses_matching_policy(mocker):
    client = _setup_client({"pol1": {"app2"}, "pol2": {"app1", "app2"}})
    calls = _capture_setup_checkboxes(mocker, policy_answer=["pol1", "pol2"])
    cfg = {"watched_policy_ids": ["pol1"], "tracked_apps": []}

    cmd_setup(client, cfg, silent_console(), package="com.example.app")

    # pol1 lacks the package, so the app list comes from pol2.
    app_choices = {c.value["id"]: c for c in calls[1]}
    assert set(app_choices) == {"app1", "app2"}
    assert app_choices["app1"].checked and not app_choices["app2"].checked
    # Store catalog is fetched once and reused for the app step.
    assert client.fetch_store_apps.call_count == 1


def test_setup_unknown_package_returns_1(mocker):
    client = _setup_client({"pol1": {"app1"}})
    checkbox = mocker.patch("questionary.checkbox")

    rc = cmd_setup(client, {}, silent_console(), package="com.missing.app")

    assert rc == 1
    checkbox.assert_not_called()
    client.fetch_policy_app_ids.assert_not_called()


@pytest.mark.parametrize("error", [requests.HTTPError("boom"), requests.ConnectionError("down")])
def test_setup_package_flags_policies_whose_fetch_fails(mocker, error):
    client = _setup_client({"pol1": {"app1"}, "pol2": {"app1"}, "pol3": {"app2"}})
    def flaky(pid):
        if pid == "pol2":
            raise error
        return {"pol1": {"app1"}, "pol3": {"app2"}}[pid]
    client.fetch_policy_app_ids.side_effect = flaky
    calls = _capture_setup_checkboxes(mocker)

    cmd_setup(client, {}, silent_console(), package="com.example.app")

    choices = {c.value: c for c in calls[0]}
    assert set(choices) == {"pol1", "pol2"}
    assert "(check failed)" in choices["pol2"].title
    assert "(new)" in choices["pol1"].title


def test_setup_package_failed_source_policy_does_not_crash(mocker):
    client = _setup_client({"pol1": {"app1"}})
    client.fetch_policy_app_ids.side_effect = requests.Timeout("slow")
    calls = _capture_setup_checkboxes(mocker, policy_answer=["pol1"])

    rc = cmd_setup(client, {}, silent_console(), package="com.example.app")

    assert rc == 0
    assert len(calls) == 1  # no apps known, so setup stops before the app prompt


def test_setup_without_package_lists_all_policies(mocker):
    client = _setup_client({"pol1": {"app1"}, "pol2": {"app2"}})
    calls = _capture_setup_checkboxes(mocker)

    cmd_setup(client, {}, silent_console())

    assert [c.value for c in calls[0]] == ["pol1", "pol2"]
    assert [c.title for c in calls[0]] == ["Policy pol1", "Policy pol2"]
    client.fetch_policy_app_ids.assert_not_called()
