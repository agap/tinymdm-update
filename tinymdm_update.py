#!/usr/bin/env python3
"""TinyMDM policy app updater CLI."""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import questionary
import requests
from rich.console import Console
from rich.table import Table
from rich.text import Text

BASE_URL = "https://www.tinymdm.net/api/v1/"
CONFIG_PATH = Path.home() / ".config" / "tinymdm-update" / "config.json"
console = Console()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def get_headers() -> dict:
    public_key = os.environ.get("TINYMDM_PUBLIC_KEY")
    secret_key = os.environ.get("TINYMDM_SECRET_KEY")
    account_id = os.environ.get("TINYMDM_ACCOUNT_ID")
    if not public_key or not secret_key or not account_id:
        console.print(
            "[bold red]Error:[/] TINYMDM_PUBLIC_KEY, TINYMDM_SECRET_KEY, and "
            "TINYMDM_ACCOUNT_ID environment variables must be set."
        )
        sys.exit(1)
    return {
        "X-Tinymdm-Manager-Apikey-Public": public_key,
        "X-Tinymdm-Manager-Apikey-Secret": secret_key,
        "X-Account-Id": account_id,
        "Content-Type": "application/json",
    }


def fetch_all(path: str, headers: dict) -> list:
    """Follow pagination and return flat list of all results."""
    url = BASE_URL + path
    results = []
    while url:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
            break
        results.extend(data.get("results", []))
        url = data.get("next")
    return results


def fetch_policy_app_ids(policy_id: str, headers: dict) -> set:
    """Return the set of app IDs assigned to a policy."""
    resp = requests.get(
        f"{BASE_URL}policies/{policy_id}/applications",
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return set(resp.json().get("applications_id", []))


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def extract_version(app: dict) -> str:
    # TODO: confirm correct field name after first real run with --debug
    return (
        app.get("version_name")
        or app.get("version")
        or str(app.get("version_code") or "")
        or "?"
    )


# ---------------------------------------------------------------------------
# setup command
# ---------------------------------------------------------------------------

def cmd_setup(args) -> None:
    headers = get_headers()
    cfg = load_config()
    existing_policy_ids = set(cfg.get("watched_policy_ids", []))
    existing_app_ids = {a["id"] for a in cfg.get("tracked_apps", [])}

    with console.status("Fetching all policies..."):
        policies = fetch_all("policies", headers)

    if not policies:
        console.print("[yellow]No policies found.[/yellow]")
        return

    console.print(f"[dim]Found {len(policies)} policies.[/dim]\n")

    watched_ids = questionary.checkbox(
        "Select policies to watch:",
        choices=[
            questionary.Choice(
                title=p.get("name", p["id"]),
                value=p["id"],
                checked=p["id"] in existing_policy_ids,
            )
            for p in policies
        ],
    ).ask()

    if not watched_ids:
        console.print("[yellow]No policies selected. Setup aborted.[/yellow]")
        return

    # Fetch apps from the first watched policy so the user can pick tracked apps.
    first_id = watched_ids[0]
    with console.status("Fetching apps from first watched policy..."):
        policy_app_ids = fetch_policy_app_ids(first_id, headers)
        all_apps = fetch_all("tinymdm_store", headers)

    apps = [a for a in all_apps if a.get("id") in policy_app_ids]

    if not apps:
        console.print("[yellow]No apps found in the first selected policy.[/yellow]")
        return

    if args.debug:
        console.print("[dim]First app object (raw):[/dim]")
        console.print(apps[0])

    tracked_apps = questionary.checkbox(
        "Select apps to track for updates:",
        choices=[
            questionary.Choice(
                title=f"{app.get('name_en') or app.get('name_fr') or app.get('package_name') or app['id']}  [{app.get('id', '?')}]",
                value={
                    "id": app["id"],
                    "app_type": "tinymdm_store_app",
                    "name": app.get("name_en") or app.get("name_fr") or app.get("package_name") or app["id"],
                },
                checked=app["id"] in existing_app_ids,
            )
            for app in apps
        ],
    ).ask()

    if not tracked_apps:
        console.print("[yellow]No apps selected. Setup aborted.[/yellow]")
        return

    cfg["watched_policy_ids"] = watched_ids
    cfg["tracked_apps"] = tracked_apps
    save_config(cfg)

    console.print(
        f"\n[bold green]Setup complete.[/bold green] "
        f"Watching [cyan]{len(watched_ids)}[/cyan] "
        f"{'policy' if len(watched_ids) == 1 else 'policies'} and tracking "
        f"[cyan]{len(tracked_apps)}[/cyan] "
        f"{'app' if len(tracked_apps) == 1 else 'apps'}.\n"
        f"Config saved to [dim]{CONFIG_PATH}[/dim]"
    )


# ---------------------------------------------------------------------------
# update command
# ---------------------------------------------------------------------------

def cmd_update(args) -> None:
    headers = get_headers()
    cfg = load_config()

    watched_ids: list = cfg.get("watched_policy_ids", [])
    if not watched_ids:
        console.print(
            "[bold red]No watched policies configured.[/bold red] "
            "Run [bold]tinymdm-update setup[/bold] first."
        )
        sys.exit(1)

    tracked_apps: list = cfg.get("tracked_apps", [])
    if not tracked_apps:
        console.print(
            "[bold red]No tracked apps configured.[/bold red] "
            "Run [bold]tinymdm-update setup[/bold] first."
        )
        sys.exit(1)

    # When tracking multiple apps, let the user choose which to process now.
    if len(tracked_apps) > 1:
        apps_to_process = questionary.checkbox(
            "Select app(s) to update this session:",
            choices=[
                questionary.Choice(
                    title=app.get("name", app["id"]),
                    value=app,
                    checked=True,
                )
                for app in tracked_apps
            ],
        ).ask()
        if not apps_to_process:
            console.print("[yellow]No apps selected.[/yellow]")
            return
    else:
        apps_to_process = tracked_apps

    # Resolve watched policy objects once.
    with console.status("Fetching policies..."):
        all_policies = fetch_all("policies", headers)
    policy_by_id = {p["id"]: p for p in all_policies}
    watched_policies = [policy_by_id[pid] for pid in watched_ids if pid in policy_by_id]

    missing = [pid for pid in watched_ids if pid not in policy_by_id]
    if missing:
        console.print(f"[yellow]Warning:[/yellow] {len(missing)} watched policy ID(s) not found in API response.")

    if not watched_policies:
        console.print("[yellow]None of the watched policy IDs were found.[/yellow]")
        return

    any_failure = False

    for app in apps_to_process:
        app_label = app.get("name", app["id"])
        console.rule(f"[bold]{app_label}[/bold]")

        # Fetch latest version from TinyMDM store catalog.
        latest_version = "?"
        store_updated_dt = None
        store_updated_str = ""
        with console.status(f"Fetching latest store version for {app_label}..."):
            try:
                store_apps = fetch_all("tinymdm_store", headers)
                if args.debug and store_apps:
                    console.print("[dim]First store app object (raw):[/dim]")
                    console.print(store_apps[0])
                store_match = next(
                    (a for a in store_apps if a.get("id") == app["id"]), None
                )
                if store_match:
                    latest_version = extract_version(store_match)
                    raw_date = store_match.get("last_update_date", "")
                    if raw_date:
                        try:
                            store_updated_dt = datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S")
                            store_updated_str = store_updated_dt.strftime("%b %d, %Y")
                        except ValueError:
                            pass
                else:
                    console.print(
                        f"[yellow]App {app['id']} not found in store catalog "
                        f"— version comparison unavailable.[/yellow]"
                    )
            except requests.HTTPError as e:
                console.print(f"[yellow]Could not fetch store catalog: {e}[/yellow]")

        # Fetch installed app IDs from each watched policy.
        history = cfg.get("update_history", {})
        policy_status = []
        with console.status("Checking installed apps across watched policies..."):
            for policy in watched_policies:
                policy_app_ids = fetch_policy_app_ids(policy["id"], headers)
                is_installed = app["id"] in policy_app_ids
                history_key = f"{policy['id']}:{app['id']}"
                last_updated = history.get(history_key)
                last_updated_dt = datetime.fromisoformat(last_updated) if last_updated else None
                needs_update = bool(
                    is_installed
                    and store_updated_dt
                    and last_updated_dt
                    and store_updated_dt > last_updated_dt
                )
                policy_status.append(
                    {
                        "policy": policy,
                        "is_installed": is_installed,
                        "last_updated_dt": last_updated_dt,
                        "needs_update": needs_update,
                        "history_key": history_key,
                    }
                )

        # Build checkbox choices annotated with version status.
        store_info = ""
        if latest_version != "?":
            store_info = f"v{latest_version}"
            if store_updated_str:
                store_info += f", updated {store_updated_str}"

        choices = []
        for ps in policy_status:
            pname = ps["policy"].get("name", ps["policy"]["id"])
            if not ps["is_installed"]:
                label = f"  -  not installed    {pname}"
            elif ps["last_updated_dt"]:
                last_str = ps["last_updated_dt"].strftime("%b %d, %Y")
                suffix = f"  ({store_info})" if store_info else ""
                if ps["needs_update"]:
                    label = f"  ↑  last pushed {last_str}{suffix}    {pname}"
                else:
                    label = f"  ✓  last pushed {last_str}{suffix}    {pname}"
            else:
                suffix = f"  ({store_info})" if store_info else ""
                label = f"  ?  no update recorded{suffix}    {pname}"
            choices.append(
                questionary.Choice(
                    title=label,
                    value=ps,
                    checked=bool(ps["needs_update"]),
                )
            )

        prompt = f"Select policies to update"
        if latest_version != "?":
            prompt += f"  (latest: {latest_version})"
        prompt += ":"

        to_update = questionary.checkbox(prompt, choices=choices).ask()

        if not to_update:
            console.print(f"[yellow]No policies selected for {app_label}.[/yellow]")
            continue

        # Fire update requests and collect results.
        table = Table(show_header=True, header_style="bold")
        table.add_column("Policy", style="cyan")
        table.add_column("Was")
        table.add_column("Now")
        table.add_column("Result")

        for ps in to_update:
            pname = ps["policy"].get("name", ps["policy"]["id"])
            policy_id = ps["policy"]["id"]
            prev = ps["last_updated_dt"].strftime("%b %d, %Y") if ps["last_updated_dt"] else "?"

            resp = requests.post(
                f"{BASE_URL}policies/{policy_id}/applications/update",
                json={"app_type": app["app_type"], "id": app["id"]},
                headers=headers,
                timeout=30,
            )

            if resp.ok:
                result_cell = Text("✓ OK", style="bold green")
                now = datetime.now().strftime("%b %d, %Y")
                cfg.setdefault("update_history", {})[ps["history_key"]] = datetime.now().isoformat()
                save_config(cfg)
            else:
                result_cell = Text(f"✗ {resp.status_code}", style="bold red")
                now = prev
                any_failure = True

            table.add_row(pname, prev, now, result_cell)

        console.print(table)

    if any_failure:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update TinyMDM policy apps without fighting the web UI.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print raw API response shapes to aid version-field discovery.",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("setup", help="Configure watched policies and tracked apps.")
    subparsers.add_parser("update", help="Update apps across watched policies (default).")

    args = parser.parse_args()

    if args.command == "setup":
        cmd_setup(args)
    else:
        cmd_update(args)


if __name__ == "__main__":
    main()
