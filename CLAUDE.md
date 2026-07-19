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
hrd domain-info example.com
hrd owner-info 173216
hrd owner-list --details
hrd nameservers example.com ns1.example.com ns2.example.com
hrd host list
hrd notifications --ack --limit 10
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
  (`login`, `partner_get_balance`, `domain_list`, `domain_info`, `domain_renew`, `domain_update`,
  `domain_host_create/update/delete/info/list`, `action_list`, `action_info`, `user_info`,
  `user_list`, `poll_get`, `poll_ack`) returns raw dicts/`ElementTree` data, not domain models. See
  `docs_api/PROTOCOL.md` for the full protocol spec — read it before touching `api.py`.
  - Request signing is load-bearing and easy to get subtly wrong: signature =
    `SHA512(exact_utf8_xml_bytes + binary_api_hash)`, sent as 64 raw bytes immediately before the
    XML payload, all inside the length-prefixed frame.
  - The session `token` returned by `login` is **not** resent in later requests — auth is carried
    entirely by the per-request signature. Don't "fix" this by adding the token back into requests.
  - `HRDApi(..., debug=True)` (wired to the CLI's `--debug` flag) prints every request/response XML
    in `_execute()`. The password in the `login` request's `<pass>...</pass>` is masked with
    asterisks by `_redact_pass()` before printing — but only for the printed copy; the original
    `xml_str` (unmasked) is still what actually gets signed and sent, since the signature must
    cover the exact bytes transmitted. `domain_info`'s nested fields (`ns`, `host`, `dnssec`, `actions`) need
    dedicated parsing helpers (`_parse_ns_element`, `_parse_host_element`) since they contain child
    elements rather than a flat `.text`, unlike every other field on that response.
  - Most methods build their request via the flat-dict `_request(module, method, params)` helper
    (backed by `_dict_to_xml`, which silently drops list values — it only handles flat
    scalars/nested dicts). Requests with nested/repeated elements — `domain_update`'s nameserver
    list, `domain_host_create`/`domain_host_update`'s repeated `ipv4`/`ipv6` — instead use
    `_request_custom(module, method, build_fn)`, which hands the raw target `ET.Element` to a
    builder callback so it can append children directly. Both funnel into the shared `_execute()`
    tail (send/read/error-check), so the debug printing and error handling stay in one place.
    `domain_update`'s nameserver XML is a triple-nested `<ns>` (`nsOrGroupType` → the "explicit
    list" choice branch → one `<ns><name>` per server) mirroring the PHP client's `nsToXml()`
    exactly — the API also rejects fewer than 2 nameservers (`minOccurs="2"` in the XSD), so
    `domain_update`/the `nameservers` CLI command must be called with at least 2.
  - `poll_get()` returns at most one pending notification (the head of the account's notification
    queue) as a flat dict, or `None` if the queue is empty — it does **not** return a list.
    `poll_ack(id)` permanently consumes that notification so the next `poll_get()` returns the
    following one; there's no way to "peek" at more than one without acking through them.
- **`hrd_py/client.py` (`HRDClient`)** — high-level API. Wraps an `HRDApi` instance and converts
  raw responses into the dataclasses in `hrd_py/models.py` (`Balance`, `Domain`, `HistoryEntry`,
  `Owner`, `DomainDetails`). Handles `domain_list`/`action_list` pagination (loops using
  `lastName`/`lastId` until a short/empty batch comes back — the API has no documented page-size
  limit) and tolerates per-domain `domain_info` failures by falling back to a `status="unknown"`
  `Domain` rather than failing the whole listing. `get_history(limit)` lists actions
  oldest-id-first via `action_list`, but only calls `action_info` (one request per id) for the
  most recent `limit` ids, to avoid one round trip per historical action ever performed on the
  account. `get_domain_details(name)` resolves the registrant/owner by feeding `domain_info`'s
  `user` id into `user_info` — the API exposes no separate "sale"/invoice concept, so `Owner` is
  the closest thing to billing-relevant contact data. `Domain.owner_id`/`DomainDetails.owner_id`
  hold that same raw numeric subscriber id even when the `Owner` lookup itself fails or is
  skipped; `get_owner(owner_id)` resolves it standalone, and finding "every domain a subscriber
  owns" is just `[d for d in list_domains() if d.owner_id == owner_id]` — the API has no
  dedicated by-owner domain query. `list_owner_ids()` and `list_hosts()` paginate `user_list`/
  `domain_host_list` the same way `list_domains()`/`get_history()` do (loop on `lastId`/`lastName`
  until a short/empty batch). `update_nameservers`, `create_host`/`update_host`/`delete_host`, and
  `get_next_notification`/`ack_notification` are thin pass-throughs to the matching `HRDApi`
  methods — they don't need pagination or dataclass wrapping.
- **`hrd_py/models.py`** — plain dataclasses. `Domain.is_expiring_soon(days=30)` is a **method**,
  not a property — call it as `d.is_expiring_soon()`/`d.is_expiring_soon(days)`.
- **`hrd_py/config.py` (`ConfigManager`)** — multi-profile credential storage at
  `~/.config/hrd/config.yaml` (chmod 600 on save). Supports multiple named profiles plus a
  default profile.
- **`hrd_py/cli.py`** — Click-based CLI. `CLIContext.get_client()` resolves credentials in order:
  (1) named/default profile from `ConfigManager`, (2) `HRD_LOGIN`/`HRD_PASS`/`HRD_HASH` env vars
  (via `.env`, loaded with `load_dotenv(override=True)` so `.env` always wins over pre-existing
  shell env vars) — env fallback only applies when no specific non-default profile was requested.
  The global `--debug` flag flows from `CLIContext.debug` into every `HRDClient`/`HRDApi` it
  constructs (including per-profile ones created inside the multi-profile loops below).
  `balance`, `domains`, `auto-renew`, and `history` all process every configured profile by default
  (via `CLIContext.get_profiles_to_process()`, fresh `CLIContext` per profile) unless the global
  `--profile` option pins them to one — `explicit_profile` (the raw `--profile` value) vs.
  `profile_name` (that value falling back to the configured default) is the distinction that
  drives this. `auto-renew` also asks for confirmation before renewing each domain (showing its
  expiry date) unless `--no-ask` is passed. `history` merges every profile's entries into one
  table sorted by date, tagging each row with its owning profile. `domain-info`, `owner-info`, and
  `renew`, and `nameservers` target a single domain/subscriber rather than iterating everything
  per profile, but still loop over `get_profiles_to_process()` and stop at the first profile that
  actually has it — a domain/subscriber belongs to exactly one profile, but the CLI has no way to
  know which one without asking the API, so `--profile` is only needed to skip that search or to
  disambiguate. `nameservers` requires at least 2 hostnames (the API rejects fewer) and is
  otherwise a thin wrapper over `update_nameservers`. The `host` group (`list`/`info`/`create`/
  `update`/`delete`) manages glue records the same way: `host list` iterates every profile like
  `domains`/`balance`, while `host info`/`create`/`update`/`delete` search-and-stop like
  `domain-info`/`renew` since a given host belongs to one profile's parent domain.
  `notifications` reads the account's poll queue: without `--ack` it only ever shows the current
  head-of-queue message per profile (calling `poll.get` repeatedly without acking returns the same
  one every time), so peeking never consumes anything; `--ack` drains and permanently
  acknowledges up to `--limit` messages per profile, showing each right before it's acked.
  `owner-list` lists every subscriber id per profile via `list_owner_ids()`; `--details` adds one
  `user_info` round trip per id to resolve names too, so it's slower on accounts with many
  subscribers.
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
