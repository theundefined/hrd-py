# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`hrd-py` is a Python library and CLI (`hrd`) for the HRD.pl domain registrar API. It speaks a
custom binary/SSL protocol on port 9999 (not HTTP/REST), so most of the complexity lives in
correctly reproducing that wire format rather than in typical web-API glue code.

## Commands

```bash
# Install (editable, with dev tooling)
pip install -e ".[dev]"

# Run the CLI
hrd balance
hrd domains --all
hrd history --limit 20
hrd renew example.com
hrd auto-renew --days 7 --dry-run

# Tests
pytest -q
pytest tests/test_api.py::test_partner_get_balance -q   # single test

# Lint / format / type-check (all run in CI, see .github/workflows/ci.yml)
ruff check .
black --check .    # `black .` to actually reformat
mypy hrd_py
```

## Release process

`./release.sh [major|minor|patch|vX.Y.Z]` (default: patch) bumps the version in `pyproject.toml`,
commits, tags `vX.Y.Z`, and pushes — pushing the tag triggers the GitHub Actions `publish` job,
which builds and publishes to PyPI via trusted publishing (OIDC; no stored token). `publish_manual.sh`
is a fallback that builds and uploads via `twine` using a `PYPI_TOKEN` env var.

## Architecture

Two-layer client design, mirrored by `docs_api/php-lib` (the official PHP client, kept as a
reference implementation — consult it when a protocol detail is unclear or a new API method needs
to be added):

- **`hrd_py/api.py` (`HRDApi`)** — low-level transport. Owns the raw `socket`/`ssl.SSLSocket`,
  the 4-byte big-endian length-prefixed framing, XML request construction
  (`xmlns="http://api.hrd.pl/api/"`), and response parsing. One method per API call
  (`login`, `partner_get_balance`, `domain_list`, `domain_info`, `domain_renew`, `action_list`,
  `action_info`) returns raw dicts/`ElementTree` data, not domain models. See
  `docs_api/PROTOCOL.md` for the full protocol spec — read it before touching `api.py`.
  - Request signing is load-bearing and easy to get subtly wrong: signature =
    `SHA512(exact_utf8_xml_bytes + binary_api_hash)`, sent as 64 raw bytes immediately before the
    XML payload, all inside the length-prefixed frame.
  - The session `token` returned by `login` is **not** resent in later requests — auth is carried
    entirely by the per-request signature. Don't "fix" this by adding the token back into requests.
- **`hrd_py/client.py` (`HRDClient`)** — high-level API. Wraps an `HRDApi` instance and converts
  raw responses into the dataclasses in `hrd_py/models.py` (`Balance`, `Domain`, `HistoryEntry`).
  Handles `domain_list`/`action_list` pagination (loops using `lastName`/`lastId` until a
  short/empty batch comes back — the API has no documented page-size limit) and tolerates
  per-domain `domain_info` failures by falling back to a `status="unknown"` `Domain` rather than
  failing the whole listing. `get_history(limit)` lists actions oldest-id-first via `action_list`,
  but only calls `action_info` (one request per id) for the most recent `limit` ids, to avoid one
  round trip per historical action ever performed on the account.
- **`hrd_py/models.py`** — plain dataclasses. `Domain.is_expiring_soon(days=30)` is a **method**,
  not a property — call it as `d.is_expiring_soon()`/`d.is_expiring_soon(days)`.
- **`hrd_py/config.py` (`ConfigManager`)** — multi-profile credential storage at
  `~/.config/hrd/config.yaml` (chmod 600 on save). Supports multiple named profiles plus a
  default profile.
- **`hrd_py/cli.py`** — Click-based CLI. `CLIContext.get_client()` resolves credentials in order:
  (1) named/default profile from `ConfigManager`, (2) `HRD_LOGIN`/`HRD_PASS`/`HRD_HASH` env vars
  (via `.env`, loaded with `load_dotenv(override=True)` so `.env` always wins over pre-existing
  shell env vars) — env fallback only applies when no specific non-default profile was requested.
  `balance`, `domains`, `auto-renew`, and `history` all process every configured profile by default
  (via `CLIContext.get_profiles_to_process()`, fresh `CLIContext` per profile) unless the global
  `--profile` option pins them to one — `explicit_profile` (the raw `--profile` value) vs.
  `profile_name` (that value falling back to the configured default) is the distinction that
  drives this. `auto-renew` also asks for confirmation before renewing each domain (showing its
  expiry date) unless `--no-ask` is passed. `history` merges every profile's entries into one
  table sorted by date, tagging each row with its owning profile.
- **`hrd_py/exceptions.py`** — `HRDError` base, with `HRDCommunicationError` (socket/framing),
  `HRDAuthError` (login), and `HRDAPIError` (API returned an error status/message).

## Reference material

- `docs_api/PROTOCOL.md` — authoritative protocol documentation (framing, signing, XML shape).
- `docs_api/php-lib/src/HRDApi.php` — official PHP implementation; when adding a new API method
  or debugging a protocol mismatch, check how the PHP client builds/parses it.
- `docs_api/php-lib/schemas/*.xsd` — XSD schemas for request/response XML.

## Gotchas

- `.env` and `.pass` in the repo root contain real HRD.pl credentials for this project's
  maintainer — never print, log, or otherwise exfiltrate their contents.
- XML must be sent as the *exact* string that was hashed — re-serializing or reformatting the XML
  between hashing and sending will invalidate the signature.
