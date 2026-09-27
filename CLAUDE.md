# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Requires Python ≥ 3.14.2 (Home Assistant 2026.9). The venv is `.venv/`.

```bash
/opt/homebrew/bin/python3.14 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest                                   # all tests
.venv/bin/pytest tests/test_coordinator.py -v      # one file
.venv/bin/pytest tests/test_api.py::test_boost -v  # one test
.venv/bin/ruff check . --fix && .venv/bin/ruff format .
```

## Architecture

Home Assistant custom integration `everyday_rewards` (HACS), in `custom_components/everyday_rewards/`.

- `api.py` has no HA imports. `EverydayRewardsClient` wraps the unofficial boost API used by the Everyday Rewards web widget at `https://prod.api-wr.com`. The flow: card number → `GET /v1/oam/getFirstName` returns `hashed_crn`, then `hashcrn` + `client_id` headers on `GET /wx/v1/csl/customers/offers` and `POST .../offers/boost` (`{"offerIds": [...]}`). There's no OAuth.
- One config entry per account (unique ID = `hashed_crn`). `entry.runtime_data` is that account's `EverydayRewardsCoordinator`.
- Each coordinator refresh fetches offers. If the `auto_boost` option is on, it boosts every `NotActivated` offer in one POST, re-fetches, stores a `RunResult`, and fires `everyday_rewards_boosted`. `async_boost_now()` (button + `boost_all` service) does the same regardless of the option.
- A 401/403 raises `AccessDeniedError`, which creates the `api_access_denied` repair issue and a `ConfigEntryError`. Other API errors raise `UpdateFailed`.
- Changing options doesn't reload the entry, because a reload would trigger a boost. The update listener in `__init__.py` applies the new interval in place, and the auto-boost switch writes to entry options.
- All UI strings live in `translations/en.json`. There's no `strings.json`.

The design spec with the captured API contract is in `docs/superpowers/specs/2026-09-27-everyday-rewards-integration-design.md`.

## Rules

- Card numbers and `hashed_crn` are secrets. Keep them out of entity states and attributes, unique IDs (use `entry.entry_id`), logs and diagnostics (redacted in `diagnostics.py`).
- A fixture that builds a client from `async_get_clientsession(hass)` must be `async` and must depend on `aioclient_mock`. Otherwise it gets a real session and makes real network calls.
- HA imports `config_flow.py` on every config entry setup, so the integration can't load in tests without it.
- In HA 2026.9, `DeviceRegistry.async_get_device(identifiers=...)` raises. Use `async_get_device_by_identifier((DOMAIN, entry_id), entry_id)` instead.
- Tests use `aioclient_mock` with fake IDs (`tests/helpers.py`). Never use real card numbers or real captured responses. `.playwright-mcp/` is gitignored because it holds live browser captures.
