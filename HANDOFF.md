# HANDOFF

State of `avy-cli` as of 2026-11-20. Unofficial CLI for the Avy resident API
(tenant errands, BankID login). Python 3.9+, one dependency: `qrcode`.

## Where it stands

- Branch `master`, pushed to `noor-latif/avy-cli`, HEAD `0e71ac0`, CI green.
- `pyproject.toml` still says `0.1.0`; no tag has been cut.
- `make check` = unit tests + secret scan. Last run: 21 tests, `Secret scan clean.`
- Install from git is verified in a clean venv:
  `pip install git+https://github.com/noor-latif/avy-cli.git`

## How login works now

Two paths, one server (`avy_login.py`), always bound to `127.0.0.1`.

Local: `avy-login`, open the printed URL, scan the live QR with the phone.
Remote: `avy-login`, then `npx devhop <printed port> --no-qr` on the same host,
open the tunnel URL on the phone. The page hands off to the BankID app.

Rules that the code enforces, each for a reason:

- **The tunnel URL is the only credential.** There is no invite token: anyone
  who reaches the page during the order can complete a login as themselves, and
  that session is what gets stored. Owner's decision, recorded in `SECURITY.md`.
- **One active order per login process.** The page requests it (`POST /rearm`);
  nothing is armed at CLI start. Tabs reuse an existing order until Avy reports
  it expired, rather than replacing an order someone may be approving.
- **Order lifetime is about 30 seconds.** Measured: `startFailed` and
  `qr start token expired` at 31 s with no client. On expiry the page says so
  and a reload arms a fresh order.
- **Launches use `bankid://`**, built at page load and kept in the anchor's
  href, so a tap is a normal browser navigation. Scripted `location.assign`
  after `await` loses user activation and is ignored by mobile browsers.
  `app.bankid.com` is the fallback link, not the primary.
- **In-app browsers and Android WebViews are detected** and told to open
  Safari or Chrome; they cannot hand off to the app at all.
- **`--confirm` is required to replace a stored session that has not provably
  expired**, because a stranger's login can otherwise overwrite a working one.
  A corrupt or empty token file counts as no session.

## Known limits

- Devhop quick tunnels take 52–58 s before the new hostname resolves, while its
  `--json` `ready` event fires immediately. Filed as
  [fullstacked-labs/devhop#3](https://github.com/fullstacked-labs/devhop/issues/3).
  Meanwhile: open the link after it loads, not when it is printed.
- Cloudflare terminates TLS in front of Devhop; treat it and Devhop as trusted
  with the QR and status. The Avy token never crosses the tunnel.
- If the app is mid-approval when an order expires, that approval is lost;
  reload and approve again.
- The page's JavaScript is verified by hand-run node harnesses against the
  inline script, not by `make check`. Python tests cover the server contract
  (`/`, `/qr.svg`, `/status`, `GET /launch`, `POST /rearm`) and the re-arm,
  timeout and `--confirm` paths with a synthetic Avy.

## Suggested next steps

1. Bump to `0.2.0` and cut a `v0.2.0` tag so friends can pin the login rework.
2. Move the JS checks into the repo (e.g. `tests/page.mjs` under node) so CI
   catches page regressions; today only the Python contract is gated.
3. Re-test the flow on an Android phone; everything so far was verified on iOS
   Chrome/Safari.
4. Revisit devhop#3 when it lands; the wait-for-DNS loop in the test harness
   (`getaddrinfo` polling) is the workaround to delete.

## Files

- `avy.py` — CLI, API calls, capability cache, `token_expiry`.
- `avy_login.py` — login server, page, BankID handoff, `--confirm` guard.
- `tests/test_avy.py`, `tests/test_login.py` — synthetic fixtures only.
- `README.md` — user-facing flow. `SECURITY.md` — credential model.
- `SKILL.md` and `skills/avy-cli/SKILL.md` — must stay identical.