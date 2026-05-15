import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from tinymdm_update.api import CredentialError, TinyMDMClient, client_from_env

BASE = "https://www.tinymdm.net/api/v1/"


def make_client() -> TinyMDMClient:
    return TinyMDMClient("pub", "sec", "acct", base_url=BASE)


def mock_response(json_data, status_code=200):
    resp = MagicMock(spec=requests.Response)
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.ok = status_code < 400
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    return resp


# ---------------------------------------------------------------------------
# fetch_all
# ---------------------------------------------------------------------------

def test_fetch_all_single_page(mocker):
    client = make_client()
    mocker.patch(
        "requests.Session.get",
        return_value=mock_response({"results": [{"id": "a"}, {"id": "b"}], "next": None}),
    )
    assert client.fetch_all("policies") == [{"id": "a"}, {"id": "b"}]

def test_fetch_all_pagination(mocker):
    client = make_client()
    page1 = mock_response({"results": [{"id": "a"}], "next": BASE + "policies?page=2"})
    page2 = mock_response({"results": [{"id": "b"}], "next": None})
    mocker.patch("requests.Session.get", side_effect=[page1, page2])
    assert client.fetch_all("policies") == [{"id": "a"}, {"id": "b"}]

def test_fetch_all_list_response(mocker):
    client = make_client()
    mocker.patch("requests.Session.get", return_value=mock_response([{"id": "x"}]))
    assert client.fetch_all("some/path") == [{"id": "x"}]

def test_fetch_all_raises_on_http_error(mocker):
    client = make_client()
    mocker.patch("requests.Session.get", return_value=mock_response({}, status_code=404))
    with pytest.raises(requests.HTTPError):
        client.fetch_all("policies")


# ---------------------------------------------------------------------------
# fetch_policy_app_ids
# ---------------------------------------------------------------------------

def test_fetch_policy_app_ids_returns_set(mocker):
    client = make_client()
    mocker.patch(
        "requests.Session.get",
        return_value=mock_response({"applications_id": ["app1", "app2"]}),
    )
    assert client.fetch_policy_app_ids("pol1") == {"app1", "app2"}

def test_fetch_policy_app_ids_missing_key_returns_empty_set(mocker):
    client = make_client()
    mocker.patch("requests.Session.get", return_value=mock_response({}))
    assert client.fetch_policy_app_ids("pol1") == set()

def test_fetch_policy_app_ids_raises_on_http_error(mocker):
    client = make_client()
    mocker.patch("requests.Session.get", return_value=mock_response({}, status_code=403))
    with pytest.raises(requests.HTTPError):
        client.fetch_policy_app_ids("pol1")


# ---------------------------------------------------------------------------
# update_policy_app
# ---------------------------------------------------------------------------

def test_update_policy_app_returns_response_on_success(mocker):
    client = make_client()
    resp = mock_response({"app_type": "tinymdm_store_app", "id": "app1"}, status_code=200)
    mocker.patch("requests.Session.post", return_value=resp)
    result = client.update_policy_app("pol1", "app1")
    assert result.ok is True

def test_update_policy_app_returns_response_on_failure(mocker):
    client = make_client()
    resp = mock_response({}, status_code=400)
    mocker.patch("requests.Session.post", return_value=resp)
    result = client.update_policy_app("pol1", "app1")
    assert result.ok is False
    assert result.status_code == 400

def test_update_policy_app_sends_correct_payload(mocker):
    client = make_client()
    mock_post = mocker.patch("requests.Session.post", return_value=mock_response({}))
    client.update_policy_app("pol1", "app1")
    _, kwargs = mock_post.call_args
    assert kwargs["json"] == {"app_type": "tinymdm_store_app", "id": "app1"}


# ---------------------------------------------------------------------------
# client_from_env
# ---------------------------------------------------------------------------

def test_client_from_env_raises_when_all_missing(monkeypatch):
    monkeypatch.delenv("TINYMDM_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("TINYMDM_SECRET_KEY", raising=False)
    monkeypatch.delenv("TINYMDM_ACCOUNT_ID", raising=False)
    with pytest.raises(CredentialError):
        client_from_env()

def test_client_from_env_raises_when_one_missing(monkeypatch):
    monkeypatch.setenv("TINYMDM_PUBLIC_KEY", "pub")
    monkeypatch.setenv("TINYMDM_SECRET_KEY", "sec")
    monkeypatch.delenv("TINYMDM_ACCOUNT_ID", raising=False)
    with pytest.raises(CredentialError, match="TINYMDM_ACCOUNT_ID"):
        client_from_env()

def test_client_from_env_returns_client_when_all_set(monkeypatch):
    monkeypatch.setenv("TINYMDM_PUBLIC_KEY", "pub")
    monkeypatch.setenv("TINYMDM_SECRET_KEY", "sec")
    monkeypatch.setenv("TINYMDM_ACCOUNT_ID", "acct")
    client = client_from_env()
    assert isinstance(client, TinyMDMClient)
