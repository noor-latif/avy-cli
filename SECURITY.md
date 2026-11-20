# Security policy

## Handling credentials

- `avy-login.py` writes the session token to `~/.avy/token.json` with mode 0600.
  It never prints the token and makes no network requests except to the
  configured Avy API base URL.
- The token is a credential for the user's own account. Do not commit it,
  include it in bug reports, or send it to anyone.
- API responses include personal data (personnummer, address, phone, invoices).
  Redact examples before sharing them.

## Remote login (`avy-login --remote`)

Remote login is an explicit opt-in for headless or remote machines. It serves
the same loopback login page through a temporary Devhop tunnel so a phone can
open it and scan the live BankID QR.

- Only `--remote` may be exposed. A normal `avy-login` binds `127.0.0.1` and
  must not be tunneled; do not start Devhop against a local login session.
- The public HTTPS URL by itself cannot fetch the QR or the BankID status. The
  invite suffix (`#…`) is a one-time bearer credential; redeeming it sets a
  `Secure`, `HttpOnly`, `SameSite=Strict` browser cookie, valid for this login
  only, and removes the invite from the address bar. Anyone holding the
  complete URL can redeem it until then, and clients or agents that open links
  automatically can consume it, so never commit it, post it in chat or an
  issue, or paste it into logs.
- The invite expires with the BankID order or the login timeout
  (`AVY_LOGIN_TIMEOUT`, 300 seconds by default). After it is consumed or
  expires, stop Devhop, start `avy-login --remote` again and use the new invite.
- Cloudflare terminates HTTPS. Treat it and Devhop as trusted with the invite,
  browser cookie, QR and status. The Avy account token never crosses the
  tunnel: the CLI obtains it from Avy and writes it locally with mode 0600.
- Devhop requires no account or email address and does not create a per-user
  server; the tunnel is ephemeral. Stop Devhop when login finishes.

## Reporting a vulnerability

Open a private issue or contact the maintainer directly. Please do not include
real tokens, personal data, or captured traffic in public issues.

## Scope

This project is unofficial and interacts with a third-party service through
undocumented endpoints. Reports about Avy's own service should go to Avy.
