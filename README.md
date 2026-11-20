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

Override paths/ports with environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `AVY_TOKEN_FILE` | `~/.avy/token.json` | where the token is stored |
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

Fields are discovered from the live form schema by their `source`, so nothing
is hardcoded to one landlord. You can override any selection with
`--object`, `--space`, `--error` and `--type` (values accept option UUID,
external ID or label).

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

## License

MIT — see [LICENSE](LICENSE).
