# Everyday Rewards Auto-Boost — Home Assistant Integration Design

Date: 2026-09-27
Status: Approved design, pending spec review

## Goal

A HACS-installable Home Assistant custom integration that automatically boosts every available
Woolworths Everyday Rewards offer, for one or more accounts, and exposes offer state in HA.

## Non-goals (v1)

- Points balance (not available without a full password login — see "API findings").
- Boosting via the Everyday Rewards app/GraphQL API or any OAuth token flow.
- Publishing the API client to PyPI or submitting to HA core.

## API findings (captured 2026-09-27)

The Everyday Rewards web "boost" widget (`activate.woolworthsrewards.com.au`) talks to an
unauthenticated REST API identified only by a hashed card number. Verified from plain Python
(no browser, no Akamai challenge).

Base URL: `https://prod.api-wr.com`
Client ID: `i0U7OrzMGFD16vPaIaCRvGZDZ0YIeGGQ` (public, embedded in the widget's JS bundle)

| Call | Request | Response |
|---|---|---|
| Resolve account | `GET /v1/oam/getFirstName`, headers `client_id`, `loyalty_card_number: <13-digit card>`, `channel: OAP` | `200 {"first_name": str, "hashed_crn": str(64)}`; unknown card → non-200 (204/4xx) |
| List offers | `GET /wx/v1/csl/customers/offers`, headers `client_id`, `hashcrn`, `content-type: application/json`, `userlocaltime: <minutes east of UTC>` | `200 {"offers": [Offer]}` |
| Boost | `POST /wx/v1/csl/customers/offers/boost`, same headers, body `{"offerIds": [str]}` | `200 [{"success": bool, "offer": {"id": str}, "code": int, "isAlreadyBoosted"?: bool, "isCannotBeBoosted"?: bool}]` |
| Card balance | `GET /v1/oam/getCardBalance` with card-number headers | `204` — requires password login; **not used** |

Offer fields used: `id`, `status` (`NotActivated` = boostable, `Activated`, `Expired`),
`heading`, `rewardValue.points`, `activation.endDate`, `divisionPartnerIds`, `offerType`.

Risk: this path is unauthenticated and Woolworths may lock it down at any time. The client must
fail loudly (repair issue), not silently, when that happens.

Security: a card number or `hashed_crn` alone grants list/boost access to an account. Both are
secrets.

## Architecture

```
custom_components/everyday_rewards/
  __init__.py       setup/unload entry, register service
  api.py            EverydayRewardsClient (aiohttp, no HA imports)
  coordinator.py    EverydayRewardsCoordinator (DataUpdateCoordinator), one per config entry
  config_flow.py    user step (card number + name), options flow (interval, auto-boost)
  entity.py         shared base entity (device info)
  sensor.py         available, boosted, last-boost sensors
  button.py         boost-all button
  switch.py         auto-boost switch
  diagnostics.py    redacted diagnostics
  services.py       boost_all service registration
  const.py, manifest.json, translations/en.json, services.yaml
```

### `api.py` — `EverydayRewardsClient`

Constructed with an `aiohttp.ClientSession`. Pure async, HA-independent.

- `async resolve_account(card_number) -> Account(first_name, hashed_crn)`
- `async get_offers(hashed_crn) -> list[Offer]`
- `async boost(hashed_crn, offer_ids) -> list[BoostResult]` (no-op on empty list)

Exceptions: `InvalidCardError` (resolve returned non-200/no hash), `AccessDeniedError`
(401/403), `ApiError` (other non-2xx, malformed JSON), `CannotConnectError` (network/timeout).
`Offer` and `BoostResult` are frozen dataclasses parsed from the JSON above.

### Config flow

- User step: `name` (optional; defaults to API `first_name`) and `card_number` (13 digits,
  whitespace stripped). Calls `resolve_account`.
  Errors: `invalid_card`, `cannot_connect`, `unknown`.
- Unique ID: `hashed_crn` → `abort: already_configured` for duplicates. Each account is its own
  config entry, which is how multiple accounts are supported.
- Entry data: `card_number`, `hashed_crn`, `name`.
- Options flow: `scan_interval_hours` (1–24, default 6), `auto_boost` (bool, default true).

### Coordinator

One per entry, `update_interval = scan_interval_hours`. Each refresh:

1. `get_offers`.
2. If `auto_boost`: boost all `NotActivated` offer IDs in one call, then re-fetch offers.
3. Store `CoordinatorData(offers, last_run: RunResult | None)`, where
   `RunResult(time, boosted, failed, error)`.
4. If a boost was attempted, fire event `everyday_rewards_boosted` with
   `{entry_id, account, boosted, failed, offers: [headings]}`.

`async_boost_now()` (used by the button and the service) runs steps 1–4 regardless of
`auto_boost` and pushes the result via `async_set_updated_data`.

Boost result handling: `success` or `isAlreadyBoosted` → boosted; otherwise failed (logged at
info with offer heading, never IDs/hashes).

### Entities (per account device)

| Entity | Platform | State | Attributes |
|---|---|---|---|
| Available offers | sensor | count `NotActivated` | `offers`: list of {heading, points, ends} |
| Boosted offers | sensor | count `Activated` | `offers`: list of {heading, points, ends} |
| Last boost | sensor (timestamp) | `last_run.time` | `boosted`, `failed`, `last_error` |
| Boost all | button | — | — |
| Auto-boost | switch | options `auto_boost` | — (toggling updates entry options) |

Device name = entry `name`. No card numbers, hashes or offer IDs in states or attributes.

### Service

`everyday_rewards.boost_all` — optional `device_id` target list; with none, boosts all accounts.

### Error handling

| Condition | Behaviour |
|---|---|
| `CannotConnectError`, `ApiError` during refresh | `UpdateFailed`; retried next interval |
| `AccessDeniedError` during refresh | create repair issue `api_access_denied`, raise `ConfigEntryError` |
| Boost call fails entirely | record `RunResult(error=...)`, offers still updated |
| Partial boost failure | counted in `failed`, run continues |

### Diagnostics

`async_redact_data` on entry data and coordinator data, redacting `card_number`, `hashed_crn`,
`name`, `first_name`.

## Testing

`pytest-homeassistant-custom-component` with its `aioclient_mock` fixture; no live network in tests.

- Fixtures in `tests/fixtures/` derived from captured responses with identifiers replaced
  by fakes: `offers_mixed.json`, `boost_success.json`, `boost_already.json`,
  `first_name.json`.
- `test_api.py`: parsing, each exception mapping, empty boost no-op, headers sent.
- `test_config_flow.py`: happy path, invalid card, cannot connect, duplicate, options.
- `test_coordinator.py`: auto-boost on/off, partial failure, access denied → repair issue,
  event fired.
- `test_entities.py`: two accounts side-by-side with independent devices/states; button and
  switch behaviour; service targeting.
- `test_diagnostics.py`: secrets redacted.

## Repo & tooling

- `hacs.json`, `README.md` (install via HACS custom repo, add account, security note about card
  numbers), `CLAUDE.md`, `.gitignore` (includes `.playwright-mcp/`).
- `requirements_test.txt`, `pyproject.toml` (ruff, pytest config).
- GitHub Actions: hassfest, HACS action, pytest.
- Raw captures in `.playwright-mcp/` and the session scratchpad are deleted once fixtures exist.
