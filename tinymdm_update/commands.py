from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import questionary
import requests
from rich.console import Console
from rich.table import Table
from rich.text import Text

from tinymdm_update.api import TinyMDMClient
from tinymdm_update.config import (
    CONFIG_PATH,
    Config,
    ConfigError,
    extract_version,
    get_last_update,
    parse_store_date,
    record_update,
    save_config,
)


def _collect_policy_app_ids(futures: dict, console: Console) -> dict[str, set[str]]:
    """Resolve per-policy app-ID futures. Policies whose fetch failed are
    omitted, so callers can tell "unknown" apart from "no apps"."""
    policy_app_ids: dict[str, set[str]] = {}
    for pid, fut in futures.items():
        try:
            policy_app_ids[pid] = fut.result()
        except requests.RequestException as exc:
            console.print(f"[yellow]Could not fetch apps for policy {pid}: {exc}[/yellow]")
    return policy_app_ids


def _scan_policy_app_ids(client: TinyMDMClient, policies: list, console: Console) -> dict[str, set[str]]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {p["id"]: pool.submit(client.fetch_policy_app_ids, p["id"]) for p in policies}
        return _collect_policy_app_ids(futures, console)


def _policy_setup_title(
    policy: dict,
    existing_ids: set[str],
    matching_ids: set[str] | None,
    failed_ids: set[str],
) -> str:
    """Policy name, annotated relative to the --package filter when one is active."""
    title = policy.get("name", policy["id"])
    if matching_ids is None:
        return title
    if policy["id"] in failed_ids:
        return title + "  (check failed)"
    if policy["id"] not in matching_ids:
        return title + "  (package not installed)"
    if policy["id"] not in existing_ids:
        return title + "  (new)"
    return title


def cmd_setup(
    client: TinyMDMClient,
    cfg: Config,
    console: Console,
    debug: bool = False,
    package: str | None = None,
) -> int:
    existing_policy_ids = set(cfg.get("watched_policy_ids", []))
    existing_app_ids = {a["id"] for a in cfg.get("tracked_apps", [])}

    with console.status("Fetching policies and store catalog..."), ThreadPoolExecutor(max_workers=2) as pool:
        policies_future = pool.submit(client.fetch_policies)
        store_future = pool.submit(client.fetch_store_apps)
        policies = policies_future.result()
        all_apps = store_future.result()

    if not policies:
        console.print("[yellow]No policies found.[/yellow]")
        return 0

    console.print(f"[dim]Found {len(policies)} policies.[/dim]\n")

    package_app = None
    policy_app_ids: dict[str, set[str]] = {}
    matching_ids: set[str] | None = None
    failed_ids: set[str] = set()
    if package:
        package_app = next((a for a in all_apps if a.get("package_name") == package), None)
        if package_app is None:
            known = ", ".join(sorted(a["package_name"] for a in all_apps if a.get("package_name")))
            console.print(
                f"[bold red]Error:[/] Package [bold]{package}[/bold] not found in the TinyMDM store. "
                f"Available packages: {known or 'none'}"
            )
            return 1

        with console.status(f"Scanning {len(policies)} policies for {package}..."):
            policy_app_ids = _scan_policy_app_ids(client, policies, console)

        matching_ids = {pid for pid, ids in policy_app_ids.items() if package_app["id"] in ids}
        failed_ids = {p["id"] for p in policies} - policy_app_ids.keys()
        summary = f"{len(matching_ids)} of {len(policies)} policies contain {package}."
        if failed_ids:
            summary += f" {len(failed_ids)} could not be checked and are listed as (check failed)."
        console.print(f"[dim]{summary}[/dim]\n")
        # Keep already-watched and unverifiable policies visible so setup doesn't silently drop them.
        policies = [
            p for p in policies
            if p["id"] in matching_ids or p["id"] in existing_policy_ids or p["id"] in failed_ids
        ]
        if not policies:
            console.print(f"[yellow]No policies contain {package}.[/yellow]")
            return 0

    watched_ids = questionary.checkbox(
        "Select policies to watch:",
        choices=[
            questionary.Choice(
                title=_policy_setup_title(p, existing_policy_ids, matching_ids, failed_ids),
                value=p["id"],
                checked=p["id"] in existing_policy_ids,
            )
            for p in policies
        ],
    ).ask()

    if not watched_ids:
        console.print("[yellow]No policies selected. Setup aborted.[/yellow]")
        return 0

    if matching_ids is not None:
        # Every policy was already scanned; prefer one that contains the package as the app source.
        first_id = next((pid for pid in watched_ids if pid in matching_ids), watched_ids[0])
        first_app_ids = policy_app_ids.get(first_id, set())
    else:
        with console.status("Fetching apps from first watched policy..."):
            first_app_ids = client.fetch_policy_app_ids(watched_ids[0])

    apps = [a for a in all_apps if a.get("id") in first_app_ids]

    if not apps:
        console.print("[yellow]No apps found in the first selected policy.[/yellow]")
        return 0

    if debug:
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
                checked=app["id"] in existing_app_ids
                or (package_app is not None and app["id"] == package_app["id"]),
            )
            for app in apps
        ],
    ).ask()

    if not tracked_apps:
        console.print("[yellow]No apps selected. Setup aborted.[/yellow]")
        return 0

    cfg["watched_policy_ids"] = watched_ids
    cfg["tracked_apps"] = tracked_apps
    try:
        save_config(cfg)
    except ConfigError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        return 1

    console.print(
        f"\n[bold green]Setup complete.[/bold green] "
        f"Watching [cyan]{len(watched_ids)}[/cyan] "
        f"{'policy' if len(watched_ids) == 1 else 'policies'} and tracking "
        f"[cyan]{len(tracked_apps)}[/cyan] "
        f"{'app' if len(tracked_apps) == 1 else 'apps'}.\n"
        f"Config saved to [dim]{CONFIG_PATH}[/dim]"
    )
    return 0


def cmd_update(
    client: TinyMDMClient,
    cfg: Config,
    console: Console,
    debug: bool = False,
) -> int:
    watched_ids: list = cfg.get("watched_policy_ids", [])
    if not watched_ids:
        console.print(
            "[bold red]No watched policies configured.[/bold red] "
            "Run [bold]tinymdm-update setup[/bold] first."
        )
        return 1

    tracked_apps: list = cfg.get("tracked_apps", [])
    if not tracked_apps:
        console.print(
            "[bold red]No tracked apps configured.[/bold red] "
            "Run [bold]tinymdm-update setup[/bold] first."
        )
        return 1

    if len(tracked_apps) > 1:
        apps_to_process = questionary.checkbox(
            "Select app(s) to update this session:",
            choices=[
                questionary.Choice(
                    title=app.get("name", app["id"]),
                    value=app,
                    checked=False,
                )
                for app in tracked_apps
            ],
        ).ask()
        if not apps_to_process:
            console.print("[yellow]No apps selected.[/yellow]")
            return 0
    else:
        apps_to_process = tracked_apps

    with console.status("Loading policies, users, store catalog, and policy contents..."):
        with ThreadPoolExecutor(max_workers=min(8, 3 + len(watched_ids))) as pool:
            policies_future = pool.submit(client.fetch_policies)
            users_future = pool.submit(client.fetch_users)
            store_future = pool.submit(client.fetch_store_apps)
            policy_app_ids_futures = {
                pid: pool.submit(client.fetch_policy_app_ids, pid)
                for pid in watched_ids
            }

            all_policies = policies_future.result()

            try:
                users = users_future.result()
            except requests.HTTPError as exc:
                console.print(f"[yellow]Could not fetch users: {exc}[/yellow]")
                users = []

            try:
                store_apps = store_future.result()
            except requests.HTTPError as exc:
                console.print(f"[yellow]Could not fetch store catalog: {exc}[/yellow]")
                store_apps = []

            policy_app_ids = _collect_policy_app_ids(policy_app_ids_futures, console)

    policy_by_id = {p["id"]: p for p in all_policies}
    watched_policies = [policy_by_id[pid] for pid in watched_ids if pid in policy_by_id]

    missing = [pid for pid in watched_ids if pid not in policy_by_id]
    if missing:
        console.print(f"[yellow]Warning:[/yellow] {len(missing)} watched policy ID(s) not found in API response.")

    if not watched_policies:
        console.print("[yellow]None of the watched policy IDs were found.[/yellow]")
        return 0

    users_per_policy: dict[str, int] = {}
    for user in users:
        pid = user.get("policy_id")
        if pid:
            users_per_policy[pid] = users_per_policy.get(pid, 0) + 1

    store_by_id = {a["id"]: a for a in store_apps if a.get("id")}
    if debug and store_apps:
        console.print("[dim]First store app object (raw):[/dim]")
        console.print(store_apps[0])

    any_failure = False

    for app in apps_to_process:
        app_label = app.get("name", app["id"])
        console.rule(f"[bold]{app_label}[/bold]")

        latest_version = "?"
        store_updated_dt: datetime | None = None
        store_match = store_by_id.get(app["id"])
        if store_match:
            latest_version = extract_version(store_match)
            store_updated_dt = parse_store_date(store_match.get("last_update_date", ""))
        elif store_apps:
            console.print(
                f"[yellow]App {app['id']} not found in store catalog "
                f"— version comparison unavailable.[/yellow]"
            )

        store_updated_str = store_updated_dt.strftime("%b %d, %Y") if store_updated_dt else ""

        policy_status = []
        for policy in watched_policies:
            is_installed = app["id"] in policy_app_ids.get(policy["id"], set())
            last_updated_dt = get_last_update(cfg, policy["id"], app["id"])
            needs_update = bool(
                is_installed
                and store_updated_dt
                and last_updated_dt
                and store_updated_dt > last_updated_dt
            )
            policy_status.append({
                "policy": policy,
                "is_installed": is_installed,
                "last_updated_dt": last_updated_dt,
                "needs_update": needs_update,
            })

        rows = []
        for ps in policy_status:
            pname = ps["policy"].get("name", ps["policy"]["id"])
            if not ps["is_installed"]:
                status, middle = "-", "not installed"
            elif ps["last_updated_dt"]:
                last_str = ps["last_updated_dt"].strftime("%b %d, %Y")
                status = "↑" if ps["needs_update"] else "✓"
                middle = f"last pushed {last_str}"
            else:
                status, middle = "?", "no update recorded"
            user_count = users_per_policy.get(ps["policy"]["id"], 0)
            rows.append((status, middle, pname, user_count, ps))

        rows.sort(key=lambda r: (not r[4]["needs_update"], r[3]))

        name_width = max(len(pname) for _, _, pname, _, _ in rows)
        ucount_strs = [
            f"{u} user{'s' if u != 1 else ''}" for _, _, _, u, _ in rows
        ]
        ucount_width = max(len(s) for s in ucount_strs)

        status_styles = {
            "↑": "fg:#f97316 bold",
            "✓": "fg:#22c55e",
            "?": "fg:#9ca3af",
            "-": "fg:#6b7280",
        }

        choices = [
            questionary.Choice(
                title=[
                    ("", f"  {pname:<{name_width}}    {ucount_str:>{ucount_width}}    "),
                    (status_styles.get(status, ""), status),
                    ("", f"  {middle}"),
                ],
                value=ps,
                checked=False,
            )
            for (status, middle, pname, _, ps), ucount_str in zip(rows, ucount_strs)
        ]

        prompt = "Select policies to update"
        if latest_version != "?":
            prompt += f"  —  latest: v{latest_version}"
            if store_updated_str:
                prompt += f", released {store_updated_str}"
        prompt += ":"

        to_update = questionary.checkbox(prompt, choices=choices).ask()

        if not to_update:
            console.print(f"[yellow]No policies selected for {app_label}.[/yellow]")
            continue

        table = Table(show_header=True, header_style="bold")
        table.add_column("Policy", style="cyan")
        table.add_column("Was")
        table.add_column("Now")
        table.add_column("Result")

        for ps in to_update:
            pname = ps["policy"].get("name", ps["policy"]["id"])
            policy_id = ps["policy"]["id"]
            prev = ps["last_updated_dt"].strftime("%b %d, %Y") if ps["last_updated_dt"] else "?"

            resp = client.update_policy_app(policy_id, app["id"])

            if resp.ok:
                result_cell = Text("✓ OK", style="bold green")
                now = datetime.now().strftime("%b %d, %Y")
                record_update(cfg, policy_id, app["id"])
                try:
                    save_config(cfg)
                except ConfigError as exc:
                    console.print(f"[yellow]Warning: could not save update history: {exc}[/yellow]")
            else:
                result_cell = Text(f"✗ {resp.status_code}", style="bold red")
                now = prev
                any_failure = True

            table.add_row(pname, prev, now, result_cell)

        console.print(table)

    return 1 if any_failure else 0
