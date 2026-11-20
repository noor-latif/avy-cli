# Contributing

Thanks for helping. This project is unofficial and talks to a private API, so
we keep contributor rules strict but simple.

## 30-second setup

```bash
git clone https://github.com/noor-latif/avy-cli.git
cd avy-cli
make setup          # creates .venv and installs dev dependencies
make test           # 12 unit tests, no network, no token needed
```

Or open the repo in GitHub Codespaces — the devcontainer does the same thing.

## Ground rules (enforced by CI)

1. **No secrets, no personal data.** Never commit a token, real API response,
   personnummer, address, phone number, log file or HAR. Use synthetic
   fixtures. `make check` greps tracked files for common patterns.
2. **No new network destinations.** All HTTP must go to the configured
   `AVY_API_BASE`. No telemetry, no analytics, no third-party CDNs in runtime
   code.
3. **Side effects require confirmation.** Any command that creates or changes
   real data (e.g. `case-create`) must be a dry run by default and only act
   when `--confirm` is passed.
4. **No hardcoded landlord data.** Field UUIDs, option trees and form types
   must be discovered from the live schema at runtime. See
   `build_fields()` in `avy.py` and the Lime-shaped fixture in
   `tests/test_avy.py`.
5. **Tests for behaviour changes.** Add a synthetic schema fixture; never test
   against a real account.

## Good contributions

- Support for another property-management integration (Balder, Fast2, Lime,
  Momentum, Pigello, Tampuuri, Unit4, Dynamics 365, Hogia…). Open a
  **"New landlord / integration"** issue with `avy form --options` output —
  that output contains form structure, not personal data.
- New read-only commands (`messages`, `booking`, invoice detail/PDF).
- Better error messages when a feature is disabled (`403 feature not available`).
- Robustness: token expiry handling, retries, offline capability cache.

## Pull request flow

1. Fork and create a branch: `git switch -c my-improvement`.
2. Make the change + test.
3. Run `make check` (tests + secret scan).
4. Open a PR using the template. Describe what changed and how you verified it.
5. If the change affects a specific landlord, say which integration family it
   targets and include a synthetic fixture.

## Adding a new integration family

1. Add a field-source family to the discovery notes in `docs/api.md`.
2. Add a synthetic schema fixture to `tests/test_avy.py` mirroring its field
   names and parent links.
3. Confirm `build_fields()` resolves it without landlord-specific code.
4. If automatic classification is ambiguous, add a generic keyword pattern —
   never a landlord-specific UUID.

## Agents

`AGENTS.md` and `SKILL.md` contain the same rules in agent-readable form. If
you use an AI coding agent, point it at those files first. The repo layout is
also compatible with the CLI-Anything harness style, so agent-driven
improvements should follow this same workflow.

## License

By contributing you agree that your work is licensed under MIT.
