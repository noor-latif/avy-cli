# avy-cli

Unofficial command-line client for the **Avy resident app** API. Tenants can
report faults and read invoices, cases and tenancy details from the terminal
instead of the mobile app, with JSON output that scripts and agents can use.

> **Unofficial.** Not affiliated with, endorsed by, or connected to Avy AB or
> any landlord. It uses undocumented endpoints that can change or stop working
> at any time. Use at your own risk and check whether it conflicts with your
> provider's terms. It does **not** bypass BankID — you approve every login in
> your own BankID app.

## Install

```bash
pip install git+https://github.com/noor-latif/avy-cli.git
avy-login   # one-time BankID login, then use `avy`
```

Requires Python 3.9+. The package installs two commands, `avy` and `avy-login`.

To work from a checkout:

```bash
git clone https://github.com/noor-latif/avy-cli.git
cd avy-cli
make setup          # .venv with the package and its dependencies
```

## Login

`avy-login` starts a local page at `http://127.0.0.1:8765/` and prints its
address. Open it, scan the **live** QR with your BankID app, and approve. The
QR rotates every second, so a screenshot will not work. Check that BankID shows
**Avy** as the relying party before approving.

The session token is written to `~/.avy/token.json` with mode `0600`. Treat it
like a password. Re-run the login helper when it expires.

After login the helper writes `~/.avy/capabilities.json` (mode `0600`) with the
enabled features, form types and token expiry — no token or personal data.
Read it with `avy capabilities`; rebuild it with `--refresh`.

### Log in from your phone

The login page binds `127.0.0.1`. To open it from a phone that is not on the
same network, tunnel the port it prints, from the same host:

```bash
avy-login
# Open http://127.0.0.1:8765/ and scan the live QR with BankID.
```

```bash
npx devhop 8765 --no-qr
```

Substitute the port `avy-login` printed if it is not 8765. Open the HTTPS URL
Devhop prints. A fresh quick tunnel takes up to a minute before its name
resolves; if the browser says the host was not found, wait a minute and reload.
On iOS and Android the page tries to open BankID by itself; if
the browser blocks the launch, return to the page and tap **Open BankID**. On
desktop, scan the live QR with your phone. Approve only if BankID names **Avy**.

Avy's BankID order has to be started within about 30 seconds. If nothing opens
the app in that window, the helper arms a new order (up to five) and the page
reopens BankID by itself, so a missed first attempt still recovers.

The tunnel URL is the page's only credential; stop Devhop when the login
finishes. The session token is written on the machine running the CLI, never in
the browser or through the tunnel.

`avy-login` refuses to replace a stored session that has not expired; pass
`--confirm` to replace one anyway.

Devhop is a separate tool you run yourself (the CLI does not call or bundle
it); the tunnel makes an outbound connection, so no inbound port or router
change is needed.

## Commands

From a checkout, run the same commands with `.venv/bin/avy` (after `make setup`)
or `python3 avy.py`.

```bash
avy profile                    # tenant profile
avy tenants                    # contracts and property details
avy invoices                   # invoice list
avy cases                      # existing cases
avy case-types                 # available form types
avy capabilities [--refresh]   # cached features and form types
avy form [--type ID] [--options]
avy case-create "Description" [--type ID] [--key Nej] [--set UUID=VALUE ...] [--confirm]
avy raw METHOD PATH [--body JSON] [--confirm]
```

### Report a fault

```bash
avy form --options                      # options for your tenancy
avy case-create "Kitchen tap is leaking" # dry run: resolved fields + payload
avy case-create "Kitchen tap is leaking" --confirm
```

Field UUIDs, option trees and parent links come from the live form schema. The
tested path is one tenancy; other Avy landlords use the same schema-driven code
but are unverified. The CLI picks the first option compatible with the chosen
parent and answers key/access questions with `Nej`. Override any field shown by
`form --options`:

```bash
avy case-create "Leaking tap" \
  --set 'f9364cdc-...=Asfaltering' --key Ja --type 24
```

`--set UUID=VALUE` is repeatable. VALUE may be an option UUID, external ID or
label, resolved under the selected parent. Unknown fields, unknown options and
options that do not fit the parent abort before submission. Required fields are
filled; optional fields only when overridden or needed as a parent. Text and
attachment fields send an override as-is. A required attachment needs `--set`.

`--key` defaults to `Nej` (any negative option, such as `No`). Another answer
must match a label case-insensitively; with no match the run aborts instead of
selecting `Ja`.

### Raw calls

Read methods (`GET`, `HEAD`, `OPTIONS`) run immediately. Other methods are
writes: without `--confirm` the CLI reports that nothing was sent and makes no
request.

```bash
avy raw GET /v1/message/list
avy raw POST /v2/contact-form \
  --body '{"form_type_id": 24, "fields": {"<field-uuid>": [{"value": "<option-uuid>"}]}}'
```

Add `--confirm` to send the write.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `AVY_TOKEN_FILE` | `~/.avy/token.json` | where the token is stored |
| `AVY_CAPABILITIES_FILE` | `~/.avy/capabilities.json` | cached capability map |
| `AVY_API_BASE` | `https://api.avy.se/api` | API base URL |
| `AVY_LOGIN_PORT` | `8765` | login page port |
| `AVY_LOGIN_TIMEOUT` | `300` | seconds to wait for approval |

## Security and privacy

- The token is a credential for your own account. Never commit it, paste it
  into a chat, or include it in an issue report.
- API responses contain personal data (personnummer, address, phone, invoices);
  redact before sharing.
- The login helper serves `127.0.0.1` and stores no telemetry. Tunneling that
  port with Devhop reaches it from another device; the tunnel URL is the page's
  only credential. Cloudflare terminates TLS in front of Devhop, so the QR and
  status pass through that relay; the token does not. Devhop needs no account
  or email. Stop the tunnel when the login finishes.

## Agents and CLI-Hub

This repository is a standalone CLI, not part of the CLI-Anything monorepo.
The agent skill is [SKILL.md](./SKILL.md) at the repo root;
[skills/avy-cli/SKILL.md](skills/avy-cli/SKILL.md) is the published copy used
by the skills installer, and the two are kept identical.

```bash
npx skills add noor-latif/avy-cli --skill avy-cli -g -y
```

A prompt can be as simple as: *"Use the avy-cli skill to report a leaking
tap."* Side-effecting commands are dry runs by default; an agent must get
explicit approval before adding `--confirm`.

To list the CLI on CLI-Hub, open a PR against
[HKUDS/CLI-Anything](https://github.com/HKUDS/CLI-Anything) adding this entry
to `public_registry.json`:

```json
{
  "name": "avy",
  "display_name": "Avy Resident CLI",
  "version": "0.1.0",
  "description": "Unofficial CLI for the Avy resident API - report housing faults and manage tenant errands from the terminal",
  "category": "productivity",
  "requires": "Python >= 3.9; an Avy tenant account and BankID for login",
  "homepage": "https://www.avy.se",
  "source_url": "https://github.com/noor-latif/avy-cli",
  "package_manager": "pip",
  "install_strategy": "command",
  "install_cmd": "pip install git+https://github.com/noor-latif/avy-cli.git",
  "skill_md": "https://raw.githubusercontent.com/noor-latif/avy-cli/master/skills/avy-cli/SKILL.md",
  "entry_point": "avy",
  "contributors": [
    { "name": "noor-latif", "url": "https://github.com/noor-latif" }
  ]
}
```

## Documentation and contributing

- [docs/api.md](docs/api.md) — endpoints and authentication flow
- [docs/discovery.md](docs/discovery.md) — how the API was recovered from the app
- [AGENTS.md](AGENTS.md) — rules for coding agents
- [CONTRIBUTING.md](CONTRIBUTING.md) — setup and PR flow
- [SKILL.md](./SKILL.md) — agent-facing usage notes

`make setup` creates `.venv`; `make check` runs the unit tests and a secret
scan. Open a **"New landlord / integration"** issue with a synthetic schema
that preserves the field types and parent links, not real form output: option
labels can contain property data. A GitHub Codespaces devcontainer is included.
CLI changes go through CONTRIBUTING, not the CLI-Anything monorepo.

## License

MIT — see [LICENSE](LICENSE).
