# avy-cli

A small command-line client for the **Avy resident app** API, so tenants can
handle errands (fault reports, invoices, cases) without clicking through the
mobile app.

> **Unofficial.** Not affiliated with, endorsed by, or connected to Avy AB or
> any landlord. It uses undocumented endpoints that can change or stop working
> at any time. Use at your own risk and check whether it conflicts with your
> provider's terms. It does **not** bypass BankID — you still approve every
> login in your own BankID app.

## Why

The app is slow and GUI-only. This tool talks to the same HTTPS API the app
uses, with structured JSON output that scripts and agents can consume.

## Install

Python 3.9+ and two packages for the login helper:

```bash
pip install qrcode pillow
git clone <your-repo-url> avy-cli
cd avy-cli
chmod +x avy.py avy-login.py
```

Optional: symlink the scripts into `~/.local/bin`.

## Login

```bash
python3 avy-login.py
```

Open the printed URL (`http://127.0.0.1:8765/` by default) in a browser, scan
the **live** QR with your BankID app, and approve. The BankID QR rotates every
second, which is why a static screenshot will not work. Check that the BankID
app shows **Avy** as the relying party before approving.

The session token is written to `~/.avy/token.json` with mode `0600`. Treat it
like a password. Re-run the login helper whenever it expires.

**On first login**, the helper also records which features your landlord has
enabled in `~/.avy/capabilities.json` (mode `0600`): feature flags, available
case form types and the token expiry. No personal data and no token are stored
there. View it with `avy capabilities`, or rebuild it at any time with
`avy capabilities --refresh`. Future sessions — including agents — can read
this file instead of re-probing the API.

Override paths/ports with environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `AVY_TOKEN_FILE` | `~/.avy/token.json` | where the token is stored |
| `AVY_CAPABILITIES_FILE` | `~/.avy/capabilities.json` | cached capability map |
| `AVY_API_BASE` | `https://api.avy.se/api` | API base URL |
| `AVY_LOGIN_PORT` | `8765` | local login page port |
| `AVY_LOGIN_TIMEOUT` | `300` | seconds to wait for approval |

## Usage

```bash
python3 avy.py profile                # tenant profile
python3 avy.py tenants                # contracts and property details
python3 avy.py invoices               # invoice list
python3 avy.py cases                  # existing cases
python3 avy.py case-types             # available form types
python3 avy.py form --options         # full form schema with select options
```

### Report an issue

```bash
# 1. See the available options for your tenancy
python3 avy.py form --options

# 2. Dry run — prints the exact payload, creates nothing
python3 avy.py case-create "Kitchen tap is leaking"

# 3. Submit for real
python3 avy.py case-create "Kitchen tap is leaking" --confirm
```

Everything is discovered from the live form schema: field UUIDs, the option
tree, parent dependencies and landlord-specific field names. Nothing is
hardcoded to one integration, so it also works for landlords using Balder,
Fast2, Lime, Momentum, Pigello, Tampuuri, Unit4, Dynamics 365 and others.

The CLI picks the first valid option in each dependent chain and answers
key/access questions with `Nej` by default. To choose something else, inspect
`form --options` and override any field:

```bash
python3 avy.py case-create "Leaking tap" \
  --set 'f9364cdc-...=Asfaltering' --key Ja --type 24
```

`--set UUID=VALUE` is repeatable; VALUE accepts an option UUID, external ID or
label.

### Arbitrary calls

```bash
python3 avy.py raw GET /v1/message/list
python3 avy.py raw POST /v2/contact-form --body '{"form_type_id": 24, "fields": {}}'
```

## Security and privacy

- The token is a credential for your own account. Never commit it, paste it
  into a chat, or include it in an issue report.
- API responses contain personal data (personnummer, address, phone, invoices).
  Be careful where you paste command output.
- The login helper runs a local HTTP server bound to `127.0.0.1` only, makes no
  third-party requests, and stores no telemetry.
- Review the source before running it, especially the login helper.

## Documentation

- [docs/api.md](docs/api.md) — endpoints and authentication flow
- [docs/discovery.md](docs/discovery.md) — how the API was recovered from the app
- [SKILL.md](SKILL.md) — agent-facing usage notes

## For CLI-Anything / CLI-Hub visitors

This is a **standalone** CLI, not a harness inside the CLI-Anything monorepo.
It ships a `SKILL.md` in the CLI-Anything agent-skill format (at
`skills/avy-cli/SKILL.md`), so agents can discover and drive it the usual way.

Install directly for now (it is not yet listed on CLI-Hub):

```bash
pip install git+https://github.com/noor-latif/avy-cli.git
npx skills add noor-latif/avy-cli --skill avy-cli -g -y
```

Each user then logs in with **their own** BankID — credentials are never shared:

```bash
avy-login          # one-time BankID QR approval
avy capabilities   # shows which features this landlord enabled
```

An agent prompt can be as simple as: *"Use the avy-cli skill to report a
leaking tap."* Side-effecting commands are dry-run by default; the agent must
ask for explicit approval before adding `--confirm`.

**Want this on CLI-Hub?** Open a PR against
[HKUDS/CLI-Anything](https://github.com/HKUDS/CLI-Anything) adding this entry
to `public_registry.json`:

```json
{
  "name": "avy",
  "display_name": "Avy Resident CLI",
  "version": "0.1.0",
  "description": "Unofficial CLI for the Avy resident API — report housing faults and manage tenant errands from the terminal",
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

Contributions to the CLI itself go through this repo's
[CONTRIBUTING.md](CONTRIBUTING.md), not the CLI-Anything monorepo.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Short version:

```bash
make setup    # venv + dependencies
make check    # tests + secret scan
```

Open a **"New landlord / integration"** issue and paste `avy form --options` if
your landlord's case form isn't handled — that output is form structure, not
personal data. A GitHub Codespaces devcontainer is included for one-click setup.
Agents should read [AGENTS.md](AGENTS.md).

## License

MIT — see [LICENSE](LICENSE).
