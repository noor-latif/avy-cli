# Security policy

## Handling credentials

- `avy-login.py` writes the session token to `~/.avy/token.json` with mode 0600.
  It never prints the token and makes no network requests except to the
  configured Avy API base URL.
- The token is a credential for the user's own account. Do not commit it,
  include it in bug reports, or send it to anyone.
- API responses include personal data (personnummer, address, phone, invoices).
  Redact examples before sharing them.

## Login over a tunnel

The login page binds `127.0.0.1`; tunneling that port (`npx devhop 8765 --no-qr`)
is how a phone on another network reaches it.

- The tunnel URL is the page's only credential: anyone who opens it during the
  order can complete a login with their own BankID, and that session is what
  the CLI stores.
- `avy-login` writes the session to `~/.avy/token.json` with mode 0600 and
  refuses to replace one that has not expired unless you pass `--confirm`.
- Cloudflare terminates HTTPS in front of Devhop; treat it and Devhop as
  trusted with the BankID QR and status. The Avy account token never crosses
  the tunnel: the CLI obtains it from Avy and writes it locally.
- Devhop requires no account or email address and does not create a per-user
  server; the tunnel is ephemeral. Stop it when login finishes.

## Reporting a vulnerability

Open a private issue or contact the maintainer directly. Please do not include
real tokens, personal data, or captured traffic in public issues.

## Scope

This project is unofficial and interacts with a third-party service through
undocumented endpoints. Reports about Avy's own service should go to Avy.
