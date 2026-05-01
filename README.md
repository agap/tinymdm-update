# tinymdm-update

CLI tool for batch-updating apps across TinyMDM policies without fighting the web UI.

TinyMDM's interface resets its filters after every policy update, making it tedious to update the same app across a handful of policies one by one. This tool lets you configure a short watchlist of policies and tracked apps, then shows you at a glance which ones are outdated and fires the update API calls for all selected policies in one go.

## Features

- **One-time setup** — pick your watched policies (e.g. 6 out of 58) and the apps to track; saved to `~/.config/tinymdm-update/config.json`
- **Version status at a glance** — compares the installed version in each policy against the latest version in the TinyMDM Store; outdated policies are pre-checked
- **Multi-app support** — track several apps; choose which one(s) to process each session
- **Rich terminal output** — spinner while fetching, interactive checkboxes, result table with per-policy status

## Installation

Requires Python 3.9+.

```bash
pip install -e .
```

## Configuration

Set your TinyMDM API credentials as environment variables (add to `.bashrc` / `.zshrc` or a `.env` file):

```bash
export TINYMDM_PUBLIC_KEY=your_public_key
export TINYMDM_SECRET_KEY=your_secret_key
```

## Usage

**First run — configure watchlist:**

```bash
tinymdm-update setup
```

Fetches all policies, lets you pick the ones you care about, then picks the app(s) to track.

**Daily use — update outdated policies:**

```bash
tinymdm-update
```

Shows watched policies with version status (`↑ outdated` / `✓ up-to-date`), outdated ones pre-checked. Confirm selection and updates fire immediately.

**Troubleshooting / API field discovery:**

```bash
tinymdm-update --debug
```

Prints raw API response objects so you can confirm version field names if version comparison shows `?`.

## API

Uses the [TinyMDM REST API](https://www.tinymdm.net/mobile-device-management/api/) (`https://www.tinymdm.net/api/v1/`). Credentials are passed via `X-Tinymdm-Apikey-Public` and `X-Tinymdm-Apikey-Secret` headers.
