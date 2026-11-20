---
name: avy-cli
description: Report housing faults, list invoices, cases and tenancy details through the unofficial Avy resident API from the terminal instead of the mobile app. Use when a tenant wants to automate Avy errands or avoid the app UI.
---

# avy-cli

Python 3.9+. Install with `pip install git+https://github.com/noor-latif/avy-cli.git`.
From a checkout, `python3 avy.py` and `python3 avy-login.py` are equivalent
once the package dependencies are installed.

Run `avy-login`, open the printed localhost URL, and have the user scan the
live QR and approve in their own BankID app. Check that BankID names Avy as
the relying party. The token is stored at `~/.avy/token.json` (mode `0600`).

```bash
avy profile
avy tenants
avy invoices
avy cases
avy case-types
avy capabilities
avy form --options
avy case-create "Description of fault"
avy raw GET /v1/message/list
```

- Preview a case without `--confirm`. Show the user the resolved fields
  privately and add `--confirm` only after explicit approval.
- Inspect `form --options`; repeat `--set UUID=VALUE` to override fields.
  Selects accept a label, external ID or option UUID under the chosen parent.
  Optional fields are only sent if overridden or needed as a parent; a
  required attachment needs an explicit value. Invalid fields or options abort.
- `--key` defaults to `Nej` and fails if no negative option matches. Never
  select a positive access answer without the user's approval.
- `raw` sends `GET`, `HEAD` and `OPTIONS` immediately. Other methods send
  nothing without explicit approval and `--confirm`.
- `capabilities` reads `~/.avy/capabilities.json` offline; `--refresh`
  rebuilds it. Read commands print JSON. On HTTP 401, ask the user to log in
  again; `403 feature not available` means the feature is disabled.
- Never print, log or commit the token. Keep account output and live form
  schemas out of shared channels and issue reports.

Configuration: `AVY_TOKEN_FILE`, `AVY_CAPABILITIES_FILE`, `AVY_API_BASE`,
`AVY_LOGIN_PORT`, `AVY_LOGIN_TIMEOUT`.
