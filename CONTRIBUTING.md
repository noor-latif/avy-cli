# Contributing

Thanks for helping. This project is unofficial and talks to a private API, so
we keep contributor rules strict but simple.

## 30-second setup

```bash
git clone https://github.com/noor-latif/avy-cli.git
cd avy-cli
make setup          # creates .venv and installs the package
make test           # unit tests; no network, no token needed
```

`make test` uses the active `python3`. Activate `.venv` after `make setup`
to include the login test; without `qrcode` it is skipped. The Codespaces
devcontainer installs the package and dependencies automatically.

## Ground rules (enforced by CI)

1. **No secrets, no personal data.** Never commit a token, real API response,
   personnummer, address, phone number, log file or HAR. Use synthetic
   fixtures. `scripts/check-secrets.sh` greps tracked files for common patterns.
2. **No new network destinations.** All HTTP must go to the configured
   `AVY_API_BASE`. No telemetry, no analytics, no third-party CDNs in runtime
   code.
3. **Side effects require confirmation.** `case-create` and non-read `raw`
   calls are dry runs by default and act only with `--confirm`.
4. **No hardcoded landlord data.** Field UUIDs, option trees and form types
   must be discovered from the live schema at runtime. See the synthetic
   schemas in `tests/test_avy.py`.
5. **Tests for behaviour changes.** Add a synthetic schema fixture; never test
   against a real account.

## Good contributions

- Support for another property-management integration that is not yet covered.
  Open a **"New landlord / integration"** issue with a synthetic schema that
  preserves the field types and parent links, not real form output: option
  labels can contain property data.
- New read-only commands (`messages`, `booking`, invoice detail/PDF).
- Better error messages when a feature is disabled (`403 feature not available`).
- Robustness: token expiry handling, retries, offline capability cache.

## Pull request flow

1. Fork and create a branch: `git switch -c my-improvement`.
2. Make the change and add tests.
3. Run `make check` (tests + secret scan).
4. Open a PR using the template. Describe what changed and how you verified it.
5. If the change affects a specific landlord, say which integration family it
   targets and include a synthetic fixture.

## Adding a new integration family

1. Add a field-source family to the discovery notes in `docs/api.md`.
2. Add a synthetic schema fixture to `tests/test_avy.py` mirroring its field
   names and parent links.
3. Confirm the field builder resolves it without landlord-specific code.
4. If automatic classification is ambiguous, add a generic keyword pattern —
   never a landlord-specific UUID.

## Agents

`AGENTS.md` has the same ground rules in agent-readable form; point coding
agents there first. `SKILL.md` is the user-facing skill for driving the CLI
(and `skills/avy-cli/SKILL.md` is its published copy). Agent-driven
improvements follow the same rules and PR flow.

## License

By contributing you agree that your work is licensed under MIT.
