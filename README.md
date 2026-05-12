# tinymdm-update

A command-line tool for pushing app updates across multiple TinyMDM policies in one go.

TinyMDM's web interface resets its filters after every policy update, making it tedious to roll out the same app update across a handful of policies one by one. This tool lets you maintain a short watchlist of policies and apps, then shows which policies are likely out of date and fires all update requests with a single confirmation.

## Features

- **One-time setup** — interactively pick the policies and apps you care about; saved to `~/.config/tinymdm-update/config.json`
- **Re-runnable setup** — existing selections are pre-checked so re-configuring is non-destructive
- **Update history** — every successful push is timestamped; future runs show when each policy was last updated and flag it as stale if the store has published a newer version since
- **Smart pre-selection** — policies where the store version is newer than your last push are pre-checked automatically
- **Prioritized ordering** — stale policies float to the top, with ties broken by user count ascending so the smallest rollouts come first
- **User counts** — every policy row shows how many users are assigned, helping you stage updates from least to most disruptive
- **Aligned policy list** — fixed-width columns make it easy to scan status at a glance
- **Multi-app support** — track several apps; choose which to process each session
- **Manager API support** — works with TinyMDM's Manager API so one set of credentials can manage multiple accounts

## Requirements

- Python 3.9+
- [pipx](https://pipx.pypa.io) for installation
- A TinyMDM Manager account with API access

## Installation

```bash
pipx install git+https://github.com/agap/tinymdm-update.git
```

`tinymdm-update` will be available globally with no virtualenv management needed. To update to the latest version:

```bash
pipx upgrade tinymdm-update
```

## Configuration

Set your TinyMDM Manager API credentials as environment variables (add to `.bashrc`, `.zshrc`, or a `.env` file):

```bash
export TINYMDM_PUBLIC_KEY=your_manager_public_key
export TINYMDM_SECRET_KEY=your_manager_secret_key
export TINYMDM_ACCOUNT_ID=the_account_id_to_manage
```

These correspond to the `X-Tinymdm-Manager-Apikey-Public`, `X-Tinymdm-Manager-Apikey-Secret`, and `X-Account-Id` headers defined in the [TinyMDM Manager API](https://www.tinymdm.net/mobile-device-management/api/) docs. The account ID can be retrieved from the `managers/manageable_accounts` endpoint.

## Usage

### First run — configure your watchlist

```bash
tinymdm-update setup
```

Fetches all policies from TinyMDM, lets you select the ones you want to watch, then shows the apps installed in the first selected policy for you to track. Re-running setup at any time pre-checks your existing selections so you can add or remove entries without starting from scratch.

### Daily use — roll out updates

```bash
tinymdm-update
```

For each tracked app the prompt title shows the latest version available in the TinyMDM store and its release date. Each policy row shows its name, the number of users assigned to it, and its update status. Rows needing an update float to the top, and ties break by user count ascending so the smallest rollouts surface first:

```
Select policies to update  —  latest: v4.41, released Apr 12, 2026:
 » ↑  Driver Tablets          3 users    ↑  last pushed Jan 28, 2026
   ↑  Warehouse Android      18 users    ↑  last pushed Feb 10, 2026
   ○  QA Device Pool          2 users    ?  no update recorded
   ○  Office Kiosks          24 users    ✓  last pushed Apr 15, 2026
   ○  Legacy Pilot Group     47 users    -  not installed
```

| Symbol | Meaning |
|--------|---------|
| `↑` | Store has a newer version than your last push — pre-checked |
| `✓` | Store has not been updated since your last push |
| `?` | App is installed but never updated via this tool |
| `-` | App is not installed in this policy |

Confirm the selection and all update requests fire immediately. Successful pushes are recorded in the local history so future runs can detect staleness automatically.

### Troubleshooting / API field discovery

```bash
tinymdm-update setup --debug
tinymdm-update --debug
```

Prints raw API response objects, useful if version fields or app names aren't displaying as expected.

## Development

```bash
git clone https://github.com/agap/tinymdm-update.git
cd tinymdm-update
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Run the test suite:

```bash
pytest
```

41 tests cover config helpers, the API client, and command business logic. No real API credentials are needed — all network calls are mocked.

## Contributing

Bug reports and pull requests are welcome. For significant changes please open an issue first to discuss what you'd like to change.

## License

[MIT](LICENSE)
