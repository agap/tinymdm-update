from __future__ import annotations

import os

import requests

BASE_URL = "https://www.tinymdm.net/api/v1/"


class CredentialError(Exception):
    pass


class TinyMDMClient:
    def __init__(
        self,
        public_key: str,
        secret_key: str,
        account_id: str,
        base_url: str = BASE_URL,
    ) -> None:
        self._base_url = base_url
        self._session = requests.Session()
        self._session.headers.update({
            "X-Tinymdm-Manager-Apikey-Public": public_key,
            "X-Tinymdm-Manager-Apikey-Secret": secret_key,
            "X-Account-Id": account_id,
            "Content-Type": "application/json",
        })

    def fetch_all(self, path: str) -> list:
        url = self._base_url + path
        results = []
        while url:
            resp = self._session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                results.extend(data)
                break
            results.extend(data.get("results", []))
            url = data.get("next")
        return results

    def fetch_policy_app_ids(self, policy_id: str) -> set[str]:
        resp = self._session.get(
            f"{self._base_url}policies/{policy_id}/applications",
            timeout=30,
        )
        resp.raise_for_status()
        return set(resp.json().get("applications_id", []))

    def fetch_policies(self) -> list:
        return self.fetch_all("policies")

    def fetch_store_apps(self) -> list:
        return self.fetch_all("tinymdm_store")

    def fetch_users(self) -> list:
        return self.fetch_all("users")

    def update_policy_app(self, policy_id: str, app_id: str) -> requests.Response:
        return self._session.post(
            f"{self._base_url}policies/{policy_id}/applications/update",
            json={"app_type": "tinymdm_store_app", "id": app_id},
            timeout=30,
        )


def client_from_env() -> TinyMDMClient:
    keys = {
        "TINYMDM_PUBLIC_KEY": os.environ.get("TINYMDM_PUBLIC_KEY"),
        "TINYMDM_SECRET_KEY": os.environ.get("TINYMDM_SECRET_KEY"),
        "TINYMDM_ACCOUNT_ID": os.environ.get("TINYMDM_ACCOUNT_ID"),
    }
    missing = [name for name, val in keys.items() if not val]
    if missing:
        noun = "variable" if len(missing) == 1 else "variables"
        raise CredentialError(f"Missing environment {noun}: {', '.join(missing)}")
    return TinyMDMClient(keys["TINYMDM_PUBLIC_KEY"], keys["TINYMDM_SECRET_KEY"], keys["TINYMDM_ACCOUNT_ID"])
