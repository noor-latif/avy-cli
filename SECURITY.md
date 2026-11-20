# Security policy

## Handling credentials

- `avy-login.py` writes the session token to `~/.avy/token.json` with mode 0600.
  It never prints the token and makes no network requests except to the
  configured Avy API base URL.
- The token is a credential for the user's own account. Do not commit it,
  include it in bug reports, or send it to anyone.
- API responses include personal data (personnummer, address, phone, invoices).
  Redact examples before sharing them.

## Reporting a vulnerability

Open a private issue or contact the maintainer directly. Please do not include
real tokens, personal data, or captured traffic in public issues.

## Scope

This project is unofficial and interacts with a third-party service through
undocumented endpoints. Reports about Avy's own service should go to Avy.
