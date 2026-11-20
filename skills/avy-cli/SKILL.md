---
name: avy-cli
description: Report housing faults, list invoices, cases and tenancy details through the unofficial Avy resident API from the terminal instead of the mobile app. Use when a tenant wants to automate Avy errands or avoid the app UI.
---

# avy-cli

Unofficial, agent-facing CLI for the Avy resident API. Not affiliated with
Avy AB. Uses undocumented endpoints; they may break without notice. Never
bypasses BankID — a human must approve login in their own BankID app.

## Prerequisites

- Python 3.9+ with `qrcode` and `pillow` installed.
- A session token: run `python3 avy-login.py`, open the printed localhost URL,
  scan the live QR with BankID and approve. Token is saved to
  `~/.avy/token.json` (mode 0600).

## Commands

```bash
python3 avy.py profile
python3 avy.py tenants
python3 avy.py invoices
python3 avy.py cases
python3 avy.py case-types
python3 avy.py form --options
python3 avy.py case-create "Description of fault"          # dry run
python3 avy.py case-create "Description of fault" --confirm # submits
python3 avy.py raw GET /v1/message/list
```

## Agent guidance

- Always run `case-create` **without** `--confirm` first and show the user the
  payload. Only add `--confirm` after explicit approval, since it creates a
  real maintenance case sent to the landlord.
- Fields are discovered at runtime for any landlord integration. Use
  `form --options` to find a field UUID, then override it with
  `--set '<field-uuid>=<option label or uuid>'` when a dry run picks the wrong
  value. Option UUID, external ID and label are all accepted.
- Read `~/.avy/capabilities.json` (or run `avy capabilities`) first to see
  which features the landlord enabled and which form types exist. Use
  `avy capabilities --refresh` to rebuild it; no personal data is stored.
- Never print, log or commit the token. Never paste `tenants`/`invoices` output
  into shared channels: it contains personal data.
- A 401 means the token expired: ask the user to run `avy-login.py` again.
- Output is JSON; use `--raw`-style parsing with `python3 -c` or `jq`.
- `403 {"status":"feature not available"}` means the landlord has not enabled
  that feature for this tenancy — not a bug in the CLI.

## Configuration

`AVY_TOKEN_FILE`, `AVY_API_BASE`, `AVY_LOGIN_PORT`, `AVY_LOGIN_TIMEOUT`.
