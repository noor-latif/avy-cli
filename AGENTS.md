# Instructions for coding agents

Read `CONTRIBUTING.md` first. Summary of non-negotiables:

- Never write tokens, API keys, logs, HARs or personal data (personnummer,
  address, phone, invoices) into files, commits, issues or PRs.
- All HTTP goes to `AVY_API_BASE`; no other network destinations, no telemetry.
- Anything that creates or changes real data must be dry-run by default and
  require `--confirm`.
- Discover field UUIDs, form types and option trees at runtime. Do not
  hardcode landlord-specific identifiers; use synthetic fixtures in tests.
- Run `make check` before finishing. It runs the unit tests and a secret scan.

Useful files:

- `avy.py` — CLI and payload construction (`build_fields`, `choose_value`)
- `avy-login.py` — BankID login and capability cache
- `tests/test_avy.py` — synthetic schemas, including a non-Vitec integration
- `docs/api.md` — endpoint map and form field sources
- `.local/INVESTIGATION.md` — local-only handoff notes (gitignored; not present
  in clones)

When improving cross-landlord support, add a fixture shaped like the new
integration rather than special-casing a UUID.
