# Everyday Rewards Auto-Boost Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A HACS-installable Home Assistant custom integration that automatically boosts every available Woolworths Everyday Rewards offer for one or more accounts.

**Architecture:** An HA-independent `aiohttp` client (`api.py`) talks to the unofficial card-number-based boost API. One `DataUpdateCoordinator` per config entry (one entry per account) fetches offers on an interval and boosts `NotActivated` ones when auto-boost is on. Sensors, a button, a switch, a `boost_all` service and redacted diagnostics sit on top of the coordinator.

**Tech Stack:** Python 3.14, Home Assistant 2026.9, aiohttp, voluptuous, pytest + `pytest-homeassistant-custom-component` (`aioclient_mock`), ruff, GitHub Actions (hassfest, HACS).

**Spec:** `docs/superpowers/specs/2026-09-27-everyday-rewards-integration-design.md` — read it before starting; the API contract table there is the source of truth.

## Global Constraints

- Python `>=3.14.2` (required by `homeassistant==2026.9.4`). Dev venv lives at `.venv/` and is created with `/opt/homebrew/bin/python3.14`.
- Test dependency pin: `pytest-homeassistant-custom-component==0.13.367` (pins `homeassistant==2026.9.4`).
- Integration domain: `everyday_rewards`. Package path: `custom_components/everyday_rewards/`.
- API base `https://prod.api-wr.com`, client ID `i0U7OrzMGFD16vPaIaCRvGZDZ0YIeGGQ`.
- Card numbers and `hashed_crn` values are secrets: never in entity states, attributes, unique IDs, log messages or diagnostics output. Entity/device IDs are derived from `entry.entry_id`.
- Tests never touch the network. All HTTP goes through `aioclient_mock`. Test identifiers are fakes: cards `9300000000001` / `9300000000002`, hashes `"a" * 64` / `"b" * 64`. Never commit the real card number or anything from `.playwright-mcp/`.
- `hacs.json` minimum HA version: `2026.9.0` (the only version tested).
- Repo URL used in manifest/README: `https://github.com/vwylaw/ha-everyday-rewards`.
- Every commit message ends with a blank line then `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- All commands run from the repo root `/Users/vincent/woolies-boost`.

## File Map

| File | Responsibility | Task |
|---|---|---|
| `pyproject.toml`, `requirements_test.txt` | pytest/ruff config, test deps | 1 |
| `custom_components/__init__.py` | namespace marker | 1 |
| `custom_components/everyday_rewards/const.py` | domain + config keys + defaults | 1 |
| `custom_components/everyday_rewards/api.py` | HTTP client, dataclasses, exceptions | 1 |
| `tests/conftest.py`, `tests/helpers.py`, `tests/fixtures/*.json` | shared test setup | 1 |
| `custom_components/everyday_rewards/coordinator.py` | refresh/boost cycle, run results, repair issue | 2 |
| `custom_components/everyday_rewards/__init__.py` | entry setup/unload, options listener, service setup | 2, 4, 5 |
| `custom_components/everyday_rewards/manifest.json`, `translations/en.json` | HA metadata + all UI strings | 2 |
| `custom_components/everyday_rewards/config_flow.py` | add-account flow, options flow | 3 |
| `custom_components/everyday_rewards/entity.py`, `sensor.py`, `button.py`, `switch.py` | entities | 4 |
| `custom_components/everyday_rewards/services.py`, `services.yaml` | `boost_all` service | 5 |
| `custom_components/everyday_rewards/diagnostics.py` | redacted diagnostics | 6 |
| `README.md`, `CLAUDE.md`, `hacs.json`, `.github/workflows/validate.yml` | docs, HACS, CI | 7 |

---

### Task 1: Project scaffold and API client

**Files:**
- Create: `requirements_test.txt`, `pyproject.toml`, `custom_components/__init__.py`, `custom_components/everyday_rewards/__init__.py`, `custom_components/everyday_rewards/const.py`, `custom_components/everyday_rewards/api.py`
- Create: `tests/__init__.py`, `tests/conftest.py`, `tests/helpers.py`, `tests/fixtures/first_name.json`, `tests/fixtures/offers_mixed.json`, `tests/fixtures/boost_success.json`, `tests/fixtures/boost_mixed.json`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: nothing.
- Produces (`custom_components.everyday_rewards.api`):
  - Constants `API_BASE`, `CLIENT_ID`, `FIRST_NAME_PATH`, `OFFERS_PATH`, `BOOST_PATH`, `STATUS_NOT_ACTIVATED = "NotActivated"`, `STATUS_ACTIVATED = "Activated"`.
  - Exceptions `EverydayRewardsError` (base) → `CannotConnectError`, `InvalidCardError`, `AccessDeniedError`, `ApiError`.
  - `@dataclass(frozen=True) Account(first_name: str, hashed_crn: str)`
  - `@dataclass(frozen=True) Offer(id: str, status: str, heading: str, points: int | None, ends: datetime | None, partners: tuple[str, ...], offer_type: str)` with properties `boostable: bool`, `boosted: bool` and classmethod `from_json(data: dict) -> Offer`.
  - `@dataclass(frozen=True) BoostResult(offer_id: str, success: bool)` with classmethod `from_json`.
  - `class EverydayRewardsClient(session: aiohttp.ClientSession, timeout: float = 30)` with `async resolve_account(card_number: str) -> Account`, `async get_offers(hashed_crn: str) -> list[Offer]`, `async boost(hashed_crn: str, offer_ids: Iterable[str]) -> list[BoostResult]`.
- Produces (`custom_components.everyday_rewards.const`): `DOMAIN`, `CONF_CARD_NUMBER`, `CONF_HASHED_CRN`, `CONF_SCAN_INTERVAL_HOURS`, `CONF_AUTO_BOOST`, `DEFAULT_SCAN_INTERVAL_HOURS = 6`, `DEFAULT_AUTO_BOOST = True`, `EVENT_BOOSTED`, `SERVICE_BOOST_ALL`, `ISSUE_ACCESS_DENIED`.
- Produces (`tests.helpers`): `FIRST_NAME_URL`, `OFFERS_URL`, `BOOST_URL`, `CARD`, `CARD_2`, `HASH`, `HASH_2`, `load_json(name) -> Any`, `make_entry(hass, *, title="Alex", card=CARD, hashed_crn=HASH, auto_boost=False) -> MockConfigEntry`, `async setup_entry(hass, entry) -> None`, `methods(aioclient_mock) -> list[str]`.

- [ ] **Step 1: Create the Python 3.14 venv and install test deps**

`requirements_test.txt`:

```
pytest-homeassistant-custom-component==0.13.367
ruff
```

Run:

```bash
brew list python@3.14 >/dev/null 2>&1 || brew install python@3.14
/opt/homebrew/bin/python3.14 -m venv .venv
.venv/bin/python --version
.venv/bin/pip install -q -r requirements_test.txt
```

Expected: `Python 3.14.x` with x ≥ 2, and pip finishes without errors (it installs Home Assistant; this takes a few minutes).

- [ ] **Step 2: Add pytest/ruff config and package skeleton**

`pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff]
target-version = "py314"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "BLE"]

[tool.ruff.lint.isort]
force-sort-within-sections = true
known-first-party = ["custom_components", "tests"]
combine-as-imports = true
```

`custom_components/__init__.py`:

```python
"""Custom integrations."""
```

`custom_components/everyday_rewards/__init__.py` (filled in by Task 2):

```python
"""The Everyday Rewards Auto-Boost integration."""
```

`custom_components/everyday_rewards/const.py`:

```python
"""Constants for the Everyday Rewards integration."""

DOMAIN = "everyday_rewards"

CONF_CARD_NUMBER = "card_number"
CONF_HASHED_CRN = "hashed_crn"
CONF_SCAN_INTERVAL_HOURS = "scan_interval_hours"
CONF_AUTO_BOOST = "auto_boost"

DEFAULT_SCAN_INTERVAL_HOURS = 6
DEFAULT_AUTO_BOOST = True

EVENT_BOOSTED = "everyday_rewards_boosted"
SERVICE_BOOST_ALL = "boost_all"
ISSUE_ACCESS_DENIED = "api_access_denied"
```

`tests/__init__.py`:

```python
"""Tests for the Everyday Rewards integration."""
```

`tests/conftest.py`:

```python
"""Pytest fixtures for Everyday Rewards tests."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow Home Assistant to load custom_components in every test."""
```

- [ ] **Step 3: Add test fixtures and helpers**

Fixture JSON mirrors the shapes captured from the live API on 2026-09-27 (identifiers replaced). The `isCannotBeBoosted` failure shape in `boost_mixed.json` comes from the widget's JS, not a live capture.

`tests/fixtures/first_name.json`:

```json
{"first_name": "Alex", "hashed_crn": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
```

`tests/fixtures/offers_mixed.json`:

```json
{
  "offers": [
    {
      "offerType": "OTHER",
      "id": "1001",
      "status": "NotActivated",
      "offerStatus": "NotActivated",
      "utcUserBoostedAt": null,
      "campaignId": "90000001",
      "divisionPartnerIds": ["1060"],
      "rewardValue": {"points": 3000, "value": 3000, "type": "points_fixed", "limitType": "EXACT", "display": "3000"},
      "activation": {"startDate": "2026-09-14T00:00:00+10:00", "endDate": "2026-10-04T23:59:59+10:00"},
      "cta": {"dateMessage": "Ends 4 Oct", "label": "Boost"},
      "minimumSpend": 6000,
      "heading": "Collect 3000 points"
    },
    {
      "offerType": "OTHER",
      "id": "1002",
      "status": "NotActivated",
      "offerStatus": "NotActivated",
      "utcUserBoostedAt": null,
      "campaignId": "90000002",
      "divisionPartnerIds": ["2010"],
      "rewardValue": {"points": 600, "value": 600, "type": "points_fixed", "limitType": "EXACT", "display": "600"},
      "activation": {"startDate": "2026-09-21T00:00:00+10:00", "endDate": "2026-10-04T23:59:59+10:00"},
      "cta": {"dateMessage": "Ends 4 Oct", "label": "Boost"},
      "minimumSpend": 6000,
      "heading": "Collect 600 points"
    },
    {
      "offerType": "TIGER",
      "id": "1003",
      "status": "Activated",
      "offerStatus": "Activated",
      "utcUserBoostedAt": "2026-09-22T23:23:29.962Z",
      "campaignId": "90000003",
      "divisionPartnerIds": ["1005", "1030"],
      "rewardValue": {"points": 100, "value": 100, "type": "points_fixed", "limitType": "EXACT", "display": "100"},
      "activation": {"startDate": "2026-09-23T00:00:00+10:00", "endDate": "2026-09-29T23:59:59+10:00"},
      "cta": {"dateMessage": "Ends 29 Sep", "label": "Shop"},
      "minimumSpend": 0,
      "heading": "Collect 100 points"
    },
    {
      "offerType": "TIGER",
      "id": "1004",
      "status": "Expired",
      "offerStatus": "Expired",
      "utcUserBoostedAt": null,
      "campaignId": "90000004",
      "divisionPartnerIds": ["1005"],
      "rewardValue": {"points": 80, "value": 80, "type": "points_fixed", "limitType": "EXACT", "display": "80"},
      "activation": {"startDate": "2026-09-09T00:00:00+10:00", "endDate": "2026-09-20T23:59:59+10:00"},
      "cta": {"dateMessage": "Ended", "label": "Ended"},
      "minimumSpend": 0,
      "heading": "Collect 80 points"
    }
  ]
}
```

`tests/fixtures/boost_success.json`:

```json
[
  {"success": true, "offer": {"id": "1001"}, "code": 200},
  {"success": true, "offer": {"id": "1002"}, "code": 200}
]
```

`tests/fixtures/boost_mixed.json`:

```json
[
  {"success": true, "offer": {"id": "1001"}, "code": 200},
  {"success": false, "offer": {"id": "1002"}, "code": 400, "isCannotBeBoosted": true}
]
```

`tests/helpers.py`:

```python
"""Shared helpers for Everyday Rewards tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.everyday_rewards.api import (
    API_BASE,
    BOOST_PATH,
    FIRST_NAME_PATH,
    OFFERS_PATH,
)
from custom_components.everyday_rewards.const import (
    CONF_AUTO_BOOST,
    CONF_CARD_NUMBER,
    CONF_HASHED_CRN,
    CONF_SCAN_INTERVAL_HOURS,
    DOMAIN,
)

FIRST_NAME_URL = f"{API_BASE}{FIRST_NAME_PATH}"
OFFERS_URL = f"{API_BASE}{OFFERS_PATH}"
BOOST_URL = f"{API_BASE}{BOOST_PATH}"

CARD = "9300000000001"
CARD_2 = "9300000000002"
HASH = "a" * 64
HASH_2 = "b" * 64

FIXTURES = Path(__file__).parent / "fixtures"


def load_json(name: str) -> Any:
    """Load a JSON fixture by file name."""
    return json.loads((FIXTURES / name).read_text())


def make_entry(
    hass: HomeAssistant,
    *,
    title: str = "Alex",
    card: str = CARD,
    hashed_crn: str = HASH,
    auto_boost: bool = False,
) -> MockConfigEntry:
    """Create and register a config entry for one account."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=title,
        unique_id=hashed_crn,
        data={CONF_CARD_NUMBER: card, CONF_HASHED_CRN: hashed_crn, CONF_NAME: title},
        options={CONF_SCAN_INTERVAL_HOURS: 6, CONF_AUTO_BOOST: auto_boost},
    )
    entry.add_to_hass(hass)
    return entry


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up a single config entry and wait for it to settle."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def methods(aioclient_mock: AiohttpClientMocker) -> list[str]:
    """Return the HTTP methods of recorded calls, upper-cased, in order."""
    return [call[0].upper() for call in aioclient_mock.mock_calls]
```

- [ ] **Step 4: Write the failing API tests**

`tests/test_api.py`:

```python
"""Tests for the Everyday Rewards API client."""

from datetime import datetime, timedelta, timezone

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.everyday_rewards.api import (
    CLIENT_ID,
    AccessDeniedError,
    Account,
    ApiError,
    BoostResult,
    CannotConnectError,
    EverydayRewardsClient,
    InvalidCardError,
    Offer,
)

from .helpers import BOOST_URL, CARD, FIRST_NAME_URL, HASH, OFFERS_URL, load_json

AEST = timezone(timedelta(hours=10))


@pytest.fixture
def client(hass: HomeAssistant) -> EverydayRewardsClient:
    """Return a client using Home Assistant's mocked session."""
    return EverydayRewardsClient(async_get_clientsession(hass))


async def test_resolve_account(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A known card resolves to its first name and hashed CRN."""
    aioclient_mock.get(FIRST_NAME_URL, json=load_json("first_name.json"))

    account = await client.resolve_account(CARD)

    assert account == Account(first_name="Alex", hashed_crn=HASH)
    headers = aioclient_mock.mock_calls[0][3]
    assert headers["loyalty_card_number"] == CARD
    assert headers["client_id"] == CLIENT_ID
    assert headers["channel"] == "OAP"


@pytest.mark.parametrize("status", [204, 404])
async def test_resolve_account_unknown_card(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker, status: int
) -> None:
    """A non-200 lookup means the card is not recognised."""
    aioclient_mock.get(FIRST_NAME_URL, status=status)

    with pytest.raises(InvalidCardError):
        await client.resolve_account(CARD)


async def test_resolve_account_server_error(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 5xx lookup is an API error, not a bad card."""
    aioclient_mock.get(FIRST_NAME_URL, status=500)

    with pytest.raises(ApiError):
        await client.resolve_account(CARD)


async def test_get_offers(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Offers are parsed and requested with the account's hashed CRN."""
    aioclient_mock.get(OFFERS_URL, json=load_json("offers_mixed.json"))

    offers = await client.get_offers(HASH)

    assert [offer.id for offer in offers] == ["1001", "1002", "1003", "1004"]
    assert offers[0] == Offer(
        id="1001",
        status="NotActivated",
        heading="Collect 3000 points",
        points=3000,
        ends=datetime(2026, 10, 4, 23, 59, 59, tzinfo=AEST),
        partners=("1060",),
        offer_type="OTHER",
    )
    assert [offer.boostable for offer in offers] == [True, True, False, False]
    assert [offer.boosted for offer in offers] == [False, False, True, False]
    headers = aioclient_mock.mock_calls[0][3]
    assert headers["hashcrn"] == HASH
    assert headers["client_id"] == CLIENT_ID


@pytest.mark.parametrize("status", [401, 403])
async def test_get_offers_access_denied(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker, status: int
) -> None:
    """401/403 means the API has refused us."""
    aioclient_mock.get(OFFERS_URL, status=status)

    with pytest.raises(AccessDeniedError):
        await client.get_offers(HASH)


async def test_get_offers_not_json(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A non-JSON body is an API error."""
    aioclient_mock.get(OFFERS_URL, text="<html>maintenance</html>")

    with pytest.raises(ApiError):
        await client.get_offers(HASH)


async def test_get_offers_unexpected_shape(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """JSON without an offers list is an API error."""
    aioclient_mock.get(OFFERS_URL, json={"unexpected": True})

    with pytest.raises(ApiError):
        await client.get_offers(HASH)


@pytest.mark.parametrize("exc", [aiohttp.ClientError(), TimeoutError()])
async def test_get_offers_cannot_connect(
    client: EverydayRewardsClient,
    aioclient_mock: AiohttpClientMocker,
    exc: Exception,
) -> None:
    """Network failures and timeouts become CannotConnectError."""
    aioclient_mock.get(OFFERS_URL, exc=exc)

    with pytest.raises(CannotConnectError):
        await client.get_offers(HASH)


async def test_boost(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Boost posts all IDs in one request and reports per-offer results."""
    aioclient_mock.post(BOOST_URL, json=load_json("boost_mixed.json"))

    results = await client.boost(HASH, ["1001", "1002"])

    assert results == [
        BoostResult(offer_id="1001", success=True),
        BoostResult(offer_id="1002", success=False),
    ]
    _, _, body, headers = aioclient_mock.mock_calls[0]
    assert body == {"offerIds": ["1001", "1002"]}
    assert headers["hashcrn"] == HASH


async def test_boost_already_boosted_counts_as_success(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """An offer that was already boosted is treated as a success."""
    aioclient_mock.post(
        BOOST_URL,
        json=[
            {
                "success": False,
                "offer": {"id": "1001"},
                "code": 409,
                "isAlreadyBoosted": True,
            }
        ],
    )

    assert await client.boost(HASH, ["1001"]) == [
        BoostResult(offer_id="1001", success=True)
    ]


async def test_boost_nothing_is_a_noop(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Boosting no offers makes no request."""
    assert await client.boost(HASH, []) == []
    assert aioclient_mock.call_count == 0


async def test_boost_server_error(
    client: EverydayRewardsClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A failed boost request is an API error."""
    aioclient_mock.post(BOOST_URL, status=500)

    with pytest.raises(ApiError):
        await client.boost(HASH, ["1001"])
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'custom_components.everyday_rewards.api'`.

- [ ] **Step 6: Implement the API client**

`custom_components/everyday_rewards/api.py`:

```python
"""Client for the unofficial Everyday Rewards boost API.

This module has no Home Assistant imports so it can be tested and reused on its own.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiohttp

API_BASE = "https://prod.api-wr.com"
CLIENT_ID = "i0U7OrzMGFD16vPaIaCRvGZDZ0YIeGGQ"
FIRST_NAME_PATH = "/v1/oam/getFirstName"
OFFERS_PATH = "/wx/v1/csl/customers/offers"
BOOST_PATH = "/wx/v1/csl/customers/offers/boost"

STATUS_NOT_ACTIVATED = "NotActivated"
STATUS_ACTIVATED = "Activated"


class EverydayRewardsError(Exception):
    """Base error for the Everyday Rewards client."""


class CannotConnectError(EverydayRewardsError):
    """Network failure or timeout."""


class InvalidCardError(EverydayRewardsError):
    """The card number was not recognised."""


class AccessDeniedError(EverydayRewardsError):
    """The API refused the request (HTTP 401/403)."""


class ApiError(EverydayRewardsError):
    """Unexpected status code or response body."""


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _utc_offset_minutes() -> int:
    offset = datetime.now().astimezone().utcoffset()
    return int(offset.total_seconds() // 60) if offset else 0


@dataclass(frozen=True)
class Account:
    """An Everyday Rewards account resolved from a card number."""

    first_name: str
    hashed_crn: str


@dataclass(frozen=True)
class Offer:
    """A single booster offer."""

    id: str
    status: str
    heading: str
    points: int | None
    ends: datetime | None
    partners: tuple[str, ...]
    offer_type: str

    @property
    def boostable(self) -> bool:
        """Return True if the offer can still be boosted."""
        return self.status == STATUS_NOT_ACTIVATED

    @property
    def boosted(self) -> bool:
        """Return True if the offer has been boosted and is still running."""
        return self.status == STATUS_ACTIVATED

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Offer:
        """Build an offer from an API offer object."""
        reward = data.get("rewardValue") or {}
        activation = data.get("activation") or {}
        return cls(
            id=str(data["id"]),
            status=str(data.get("status", "")),
            heading=str(data.get("heading", "")),
            points=reward.get("points"),
            ends=_parse_datetime(activation.get("endDate")),
            partners=tuple(str(p) for p in data.get("divisionPartnerIds") or ()),
            offer_type=str(data.get("offerType", "")),
        )


@dataclass(frozen=True)
class BoostResult:
    """The outcome of boosting one offer."""

    offer_id: str
    success: bool

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> BoostResult:
        """Build a result from one element of the boost response."""
        return cls(
            offer_id=str((data.get("offer") or {}).get("id", "")),
            success=bool(data.get("success") or data.get("isAlreadyBoosted")),
        )


class EverydayRewardsClient:
    """Async client for the Everyday Rewards boost API."""

    def __init__(self, session: aiohttp.ClientSession, timeout: float = 30) -> None:
        """Initialise the client with a shared aiohttp session."""
        self._session = session
        self._timeout = timeout

    async def resolve_account(self, card_number: str) -> Account:
        """Look up the account for a card number."""
        status, data = await self._request(
            "GET",
            FIRST_NAME_PATH,
            {"loyalty_card_number": card_number, "channel": "OAP"},
        )
        if status >= 500:
            raise ApiError(f"Unexpected status {status} resolving card")
        if status != 200 or not isinstance(data, dict) or not data.get("hashed_crn"):
            raise InvalidCardError("Card number not recognised")
        return Account(
            first_name=str(data.get("first_name") or ""),
            hashed_crn=str(data["hashed_crn"]),
        )

    async def get_offers(self, hashed_crn: str) -> list[Offer]:
        """Return every offer on the account."""
        status, data = await self._request(
            "GET", OFFERS_PATH, self._account_headers(hashed_crn)
        )
        if (
            status != 200
            or not isinstance(data, dict)
            or not isinstance(data.get("offers"), list)
        ):
            raise ApiError(f"Unexpected offers response (HTTP {status})")
        return [Offer.from_json(item) for item in data["offers"]]

    async def boost(
        self, hashed_crn: str, offer_ids: Iterable[str]
    ) -> list[BoostResult]:
        """Boost the given offers in a single request."""
        ids = list(offer_ids)
        if not ids:
            return []
        status, data = await self._request(
            "POST",
            BOOST_PATH,
            self._account_headers(hashed_crn),
            {"offerIds": ids},
        )
        if status != 200 or not isinstance(data, list):
            raise ApiError(f"Unexpected boost response (HTTP {status})")
        return [BoostResult.from_json(item) for item in data]

    @staticmethod
    def _account_headers(hashed_crn: str) -> dict[str, str]:
        return {
            "hashcrn": hashed_crn,
            "content-type": "application/json",
            "userlocaltime": str(_utc_offset_minutes()),
        }

    async def _request(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        json_body: Any = None,
    ) -> tuple[int, Any]:
        """Return (status, parsed JSON body or None for non-200 responses)."""
        try:
            async with (
                asyncio.timeout(self._timeout),
                self._session.request(
                    method,
                    f"{API_BASE}{path}",
                    headers={
                        "client_id": CLIENT_ID,
                        "accept": "application/json",
                        **headers,
                    },
                    json=json_body,
                ) as resp,
            ):
                if resp.status in (401, 403):
                    raise AccessDeniedError(f"Access denied (HTTP {resp.status})")
                if resp.status != 200:
                    return resp.status, None
                try:
                    return resp.status, await resp.json(content_type=None)
                except ValueError as err:
                    raise ApiError("Response was not valid JSON") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnectError(
                f"Error talking to Everyday Rewards: {err!r}"
            ) from err
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: all 15 tests PASS.

- [ ] **Step 8: Lint and commit**

```bash
.venv/bin/ruff check . --fix && .venv/bin/ruff format .
.venv/bin/pytest tests/test_api.py -q
git add requirements_test.txt pyproject.toml custom_components tests
git commit -m "Add Everyday Rewards API client

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Coordinator and integration setup

**Files:**
- Create: `custom_components/everyday_rewards/coordinator.py`, `custom_components/everyday_rewards/manifest.json`, `custom_components/everyday_rewards/translations/en.json`
- Modify: `custom_components/everyday_rewards/__init__.py` (replace the docstring-only file)
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: everything `api.py`, `const.py` and `tests/helpers.py` produce (Task 1).
- Produces (`custom_components.everyday_rewards.coordinator`):
  - `type EverydayRewardsConfigEntry = ConfigEntry[EverydayRewardsCoordinator]` (`entry.runtime_data` is the coordinator).
  - `@dataclass(frozen=True) RunResult(time: datetime, boosted: tuple[str, ...], failed: tuple[str, ...], error: str | None = None)` — tuples hold offer headings.
  - `@dataclass(frozen=True) CoordinatorData(offers: tuple[Offer, ...], last_run: RunResult | None)` with properties `available: list[Offer]` and `boosted: list[Offer]`.
  - `class EverydayRewardsCoordinator(DataUpdateCoordinator[CoordinatorData])` with attribute `client`, property `auto_boost: bool`, and `async async_boost_now() -> None` (raises `HomeAssistantError` on failure).
  - `scan_interval(entry: ConfigEntry) -> timedelta`.
- Produces (`custom_components.everyday_rewards`): `PLATFORMS: list[Platform]` (empty in this task), `async_setup_entry`, `async_unload_entry`.

- [ ] **Step 1: Write the failing coordinator tests**

`tests/test_coordinator.py`:

```python
"""Tests for the Everyday Rewards coordinator."""

import aiohttp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import async_capture_events
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.everyday_rewards.const import (
    DOMAIN,
    EVENT_BOOSTED,
    ISSUE_ACCESS_DENIED,
)

from .helpers import BOOST_URL, OFFERS_URL, load_json, make_entry, methods, setup_entry


async def test_auto_boost_boosts_available_offers(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """With auto-boost on, setup boosts every NotActivated offer and re-fetches."""
    aioclient_mock.get(OFFERS_URL, json=load_json("offers_mixed.json"))
    aioclient_mock.post(BOOST_URL, json=load_json("boost_success.json"))
    events = async_capture_events(hass, EVENT_BOOSTED)
    entry = make_entry(hass, auto_boost=True)

    await setup_entry(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert methods(aioclient_mock) == ["GET", "POST", "GET"]
    assert aioclient_mock.mock_calls[1][2] == {"offerIds": ["1001", "1002"]}
    run = entry.runtime_data.data.last_run
    assert run.boosted == ("Collect 3000 points", "Collect 600 points")
    assert run.failed == ()
    assert run.error is None
    assert len(events) == 1
    assert events[0].data == {
        "entry_id": entry.entry_id,
        "account": "Alex",
        "boosted": 2,
        "failed": 0,
        "offers": ["Collect 3000 points", "Collect 600 points"],
    }


async def test_auto_boost_disabled(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """With auto-boost off, setup only reads offers."""
    aioclient_mock.get(OFFERS_URL, json=load_json("offers_mixed.json"))
    entry = make_entry(hass, auto_boost=False)

    await setup_entry(hass, entry)

    assert methods(aioclient_mock) == ["GET"]
    data = entry.runtime_data.data
    assert data.last_run is None
    assert [offer.id for offer in data.available] == ["1001", "1002"]
    assert [offer.id for offer in data.boosted] == ["1003"]


async def test_partial_boost_failure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Offers that fail to boost are counted as failed; the rest succeed."""
    aioclient_mock.get(OFFERS_URL, json=load_json("offers_mixed.json"))
    aioclient_mock.post(BOOST_URL, json=load_json("boost_mixed.json"))
    entry = make_entry(hass, auto_boost=True)

    await setup_entry(hass, entry)

    run = entry.runtime_data.data.last_run
    assert run.boosted == ("Collect 3000 points",)
    assert run.failed == ("Collect 600 points",)


async def test_boost_request_fails(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A failed boost call is recorded but does not fail the refresh."""
    aioclient_mock.get(OFFERS_URL, json=load_json("offers_mixed.json"))
    aioclient_mock.post(BOOST_URL, status=500)
    entry = make_entry(hass, auto_boost=True)

    await setup_entry(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert methods(aioclient_mock) == ["GET", "POST"]
    run = entry.runtime_data.data.last_run
    assert run.boosted == ()
    assert run.failed == ("Collect 3000 points", "Collect 600 points")
    assert run.error is not None


async def test_nothing_to_boost(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """With nothing available, no boost call is made and no event fires."""
    aioclient_mock.get(OFFERS_URL, json={"offers": []})
    events = async_capture_events(hass, EVENT_BOOSTED)
    entry = make_entry(hass, auto_boost=True)

    await setup_entry(hass, entry)

    assert methods(aioclient_mock) == ["GET"]
    assert entry.runtime_data.data.last_run.boosted == ()
    assert events == []


async def test_access_denied_creates_repair_issue(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 403 fails setup permanently and raises a repair issue."""
    aioclient_mock.get(OFFERS_URL, status=403)
    entry = make_entry(hass)

    await setup_entry(hass, entry)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ACCESS_DENIED)


async def test_connection_error_retries(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A network error at setup is retried later."""
    aioclient_mock.get(OFFERS_URL, exc=aiohttp.ClientError())
    entry = make_entry(hass)

    await setup_entry(hass, entry)

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """The entry unloads cleanly."""
    aioclient_mock.get(OFFERS_URL, json=load_json("offers_mixed.json"))
    entry = make_entry(hass)
    await setup_entry(hass, entry)

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_coordinator.py -v`
Expected: FAIL — setup fails because the integration has no `manifest.json` / `async_setup_entry` (errors mention `Integration 'everyday_rewards' not found` or `entry.runtime_data` missing).

- [ ] **Step 3: Add manifest and translations**

`custom_components/everyday_rewards/manifest.json`:

```json
{
  "domain": "everyday_rewards",
  "name": "Everyday Rewards Auto-Boost",
  "codeowners": ["@vwylaw"],
  "config_flow": true,
  "documentation": "https://github.com/vwylaw/ha-everyday-rewards",
  "integration_type": "service",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/vwylaw/ha-everyday-rewards/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

`custom_components/everyday_rewards/translations/en.json` (complete; later tasks rely on these keys):

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Add Everyday Rewards account",
        "description": "Enter the 13-digit Everyday Rewards card number. Anyone with this number can boost offers on the account, so treat it like a password.",
        "data": {
          "card_number": "Card number",
          "name": "Name"
        },
        "data_description": {
          "name": "Optional. Defaults to the first name on the account."
        }
      }
    },
    "error": {
      "invalid_card_format": "The card number must be 13 digits.",
      "invalid_card": "Everyday Rewards did not recognise this card number.",
      "cannot_connect": "Could not connect to Everyday Rewards.",
      "unknown": "Unexpected error."
    },
    "abort": {
      "already_configured": "This account is already configured."
    }
  },
  "options": {
    "step": {
      "init": {
        "data": {
          "scan_interval_hours": "Check for new offers every (hours)",
          "auto_boost": "Automatically boost new offers"
        }
      }
    }
  },
  "entity": {
    "sensor": {
      "available_offers": { "name": "Available offers" },
      "boosted_offers": { "name": "Boosted offers" },
      "last_boost": { "name": "Last boost" }
    },
    "button": {
      "boost_all": { "name": "Boost all" }
    },
    "switch": {
      "auto_boost": { "name": "Auto-boost" }
    }
  },
  "issues": {
    "api_access_denied": {
      "title": "Everyday Rewards blocked access",
      "description": "Everyday Rewards rejected the integration's requests. The unofficial API it relies on may have changed. Check for an update to the integration."
    }
  },
  "services": {
    "boost_all": {
      "name": "Boost all offers",
      "description": "Boost every available offer for the selected accounts, or for all accounts if none are selected.",
      "fields": {
        "device_id": {
          "name": "Accounts",
          "description": "Everyday Rewards account devices to boost."
        }
      }
    }
  }
}
```

- [ ] **Step 4: Implement the coordinator**

`custom_components/everyday_rewards/coordinator.py`:

```python
"""Data update coordinator for Everyday Rewards."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AccessDeniedError, EverydayRewardsClient, EverydayRewardsError, Offer
from .const import (
    CONF_AUTO_BOOST,
    CONF_HASHED_CRN,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_AUTO_BOOST,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    EVENT_BOOSTED,
    ISSUE_ACCESS_DENIED,
)

_LOGGER = logging.getLogger(__name__)

ACCESS_DENIED_MESSAGE = (
    "Everyday Rewards denied access; the unofficial API may have changed"
)

type EverydayRewardsConfigEntry = ConfigEntry[EverydayRewardsCoordinator]


def scan_interval(entry: ConfigEntry) -> timedelta:
    """Return the configured polling interval for an entry."""
    return timedelta(
        hours=entry.options.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS)
    )


@dataclass(frozen=True)
class RunResult:
    """Outcome of one boost pass. Tuples hold offer headings."""

    time: datetime
    boosted: tuple[str, ...]
    failed: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True)
class CoordinatorData:
    """Everything the entities need for one account."""

    offers: tuple[Offer, ...]
    last_run: RunResult | None

    @property
    def available(self) -> list[Offer]:
        """Offers that can still be boosted."""
        return [offer for offer in self.offers if offer.boostable]

    @property
    def boosted(self) -> list[Offer]:
        """Offers that are boosted and still running."""
        return [offer for offer in self.offers if offer.boosted]


class EverydayRewardsCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Fetches offers for one account and boosts them."""

    config_entry: EverydayRewardsConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: EverydayRewardsConfigEntry,
        client: EverydayRewardsClient,
    ) -> None:
        """Initialise the coordinator for one config entry."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=scan_interval(entry),
        )
        self.client = client
        self._last_run: RunResult | None = None

    @property
    def auto_boost(self) -> bool:
        """Return whether scheduled refreshes should boost offers."""
        return self.config_entry.options.get(CONF_AUTO_BOOST, DEFAULT_AUTO_BOOST)

    async def _async_update_data(self) -> CoordinatorData:
        try:
            return await self._refresh(boost=self.auto_boost)
        except AccessDeniedError as err:
            self._report_access_denied()
            raise ConfigEntryError(ACCESS_DENIED_MESSAGE) from err
        except EverydayRewardsError as err:
            raise UpdateFailed(str(err)) from err

    async def async_boost_now(self) -> None:
        """Fetch and boost immediately, regardless of the auto-boost setting."""
        try:
            data = await self._refresh(boost=True)
        except AccessDeniedError as err:
            self._report_access_denied()
            raise HomeAssistantError(ACCESS_DENIED_MESSAGE) from err
        except EverydayRewardsError as err:
            raise HomeAssistantError(f"Could not boost offers: {err}") from err
        self.async_set_updated_data(data)

    async def _refresh(self, *, boost: bool) -> CoordinatorData:
        hashed_crn = self.config_entry.data[CONF_HASHED_CRN]
        offers = await self.client.get_offers(hashed_crn)
        if boost:
            self._last_run = await self._boost(hashed_crn, offers)
            if self._last_run.boosted:
                offers = await self.client.get_offers(hashed_crn)
        ir.async_delete_issue(self.hass, DOMAIN, ISSUE_ACCESS_DENIED)
        return CoordinatorData(offers=tuple(offers), last_run=self._last_run)

    async def _boost(self, hashed_crn: str, offers: list[Offer]) -> RunResult:
        boostable = {offer.id: offer for offer in offers if offer.boostable}
        now = dt_util.utcnow()
        if not boostable:
            return RunResult(time=now, boosted=(), failed=())

        try:
            results = await self.client.boost(hashed_crn, boostable)
        except AccessDeniedError:
            raise
        except EverydayRewardsError as err:
            _LOGGER.warning(
                "Boosting offers for %s failed: %s", self.config_entry.title, err
            )
            run = RunResult(
                time=now,
                boosted=(),
                failed=tuple(offer.heading for offer in boostable.values()),
                error=str(err),
            )
        else:
            succeeded = {result.offer_id for result in results if result.success}
            run = RunResult(
                time=now,
                boosted=tuple(
                    offer.heading
                    for offer_id, offer in boostable.items()
                    if offer_id in succeeded
                ),
                failed=tuple(
                    offer.heading
                    for offer_id, offer in boostable.items()
                    if offer_id not in succeeded
                ),
            )
            for heading in run.failed:
                _LOGGER.info(
                    "Could not boost '%s' for %s", heading, self.config_entry.title
                )

        self.hass.bus.async_fire(
            EVENT_BOOSTED,
            {
                "entry_id": self.config_entry.entry_id,
                "account": self.config_entry.title,
                "boosted": len(run.boosted),
                "failed": len(run.failed),
                "offers": list(run.boosted),
            },
        )
        return run

    def _report_access_denied(self) -> None:
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            ISSUE_ACCESS_DENIED,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=ISSUE_ACCESS_DENIED,
        )
```

- [ ] **Step 5: Implement entry setup**

Replace `custom_components/everyday_rewards/__init__.py` with:

```python
"""The Everyday Rewards Auto-Boost integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EverydayRewardsClient
from .coordinator import (
    EverydayRewardsConfigEntry,
    EverydayRewardsCoordinator,
    scan_interval,
)

PLATFORMS: list[Platform] = []


async def async_setup_entry(
    hass: HomeAssistant, entry: EverydayRewardsConfigEntry
) -> bool:
    """Set up one Everyday Rewards account."""
    client = EverydayRewardsClient(async_get_clientsession(hass))
    coordinator = EverydayRewardsCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: EverydayRewardsConfigEntry
) -> bool:
    """Unload an account."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(
    hass: HomeAssistant, entry: EverydayRewardsConfigEntry
) -> None:
    """Apply option changes without reloading (reloading would trigger a boost)."""
    coordinator = entry.runtime_data
    coordinator.update_interval = scan_interval(entry)
    coordinator.async_update_listeners()
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_coordinator.py tests/test_api.py -v`
Expected: all PASS.

- [ ] **Step 7: Lint and commit**

```bash
.venv/bin/ruff check . --fix && .venv/bin/ruff format .
.venv/bin/pytest -q
git add custom_components tests
git commit -m "Add coordinator and config entry setup

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Config flow and options flow

**Files:**
- Create: `custom_components/everyday_rewards/config_flow.py`
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `EverydayRewardsClient.resolve_account`, `InvalidCardError`, `EverydayRewardsError` (Task 1); `const` keys; `scan_interval` behaviour via the options listener (Task 2); helpers `FIRST_NAME_URL`, `OFFERS_URL`, `CARD`, `HASH`, `load_json`, `make_entry`, `setup_entry`.
- Produces: `EverydayRewardsConfigFlow` (user step creates an entry with `data={card_number, hashed_crn, name}`, `options={scan_interval_hours: 6, auto_boost: True}`, `unique_id=hashed_crn`, `title=name`); `EverydayRewardsOptionsFlow` (step `init`, fields `scan_interval_hours` 1–24 and `auto_boost`).

- [ ] **Step 1: Write the failing config flow tests**

`tests/test_config_flow.py`:

```python
"""Tests for the Everyday Rewards config and options flows."""

from datetime import timedelta
from unittest.mock import patch

import aiohttp
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.everyday_rewards.const import (
    CONF_AUTO_BOOST,
    CONF_CARD_NUMBER,
    CONF_HASHED_CRN,
    CONF_SCAN_INTERVAL_HOURS,
    DOMAIN,
)

from .helpers import (
    CARD,
    FIRST_NAME_URL,
    HASH,
    OFFERS_URL,
    load_json,
    make_entry,
    setup_entry,
)

SETUP_ENTRY = "custom_components.everyday_rewards.async_setup_entry"


async def _start(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def test_user_flow_creates_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A valid card creates an entry named after the account holder."""
    aioclient_mock.get(FIRST_NAME_URL, json=load_json("first_name.json"))
    result = await _start(hass)

    with patch(SETUP_ENTRY, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CARD_NUMBER: "9300 0000 00001", CONF_NAME: ""}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Alex"
    assert result["data"] == {
        CONF_CARD_NUMBER: CARD,
        CONF_HASHED_CRN: HASH,
        CONF_NAME: "Alex",
    }
    assert result["options"] == {CONF_SCAN_INTERVAL_HOURS: 6, CONF_AUTO_BOOST: True}
    assert result["result"].unique_id == HASH


async def test_user_flow_custom_name(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A supplied name overrides the account's first name."""
    aioclient_mock.get(FIRST_NAME_URL, json=load_json("first_name.json"))
    result = await _start(hass)

    with patch(SETUP_ENTRY, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CARD_NUMBER: CARD, CONF_NAME: "Mum"}
        )

    assert result["title"] == "Mum"
    assert result["data"][CONF_NAME] == "Mum"


async def test_user_flow_bad_format(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A card number that is not 13 digits is rejected without an API call."""
    result = await _start(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CARD_NUMBER: "12345"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_CARD_NUMBER: "invalid_card_format"}
    assert aioclient_mock.call_count == 0


async def test_user_flow_unknown_card(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An unrecognised card shows invalid_card."""
    aioclient_mock.get(FIRST_NAME_URL, status=204)
    result = await _start(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CARD_NUMBER: CARD}
    )

    assert result["errors"] == {"base": "invalid_card"}


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A network failure shows cannot_connect and the user can retry."""
    aioclient_mock.get(FIRST_NAME_URL, exc=aiohttp.ClientError())
    result = await _start(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CARD_NUMBER: CARD}
    )

    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_duplicate(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Adding the same account twice aborts."""
    make_entry(hass)
    aioclient_mock.get(FIRST_NAME_URL, json=load_json("first_name.json"))
    result = await _start(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CARD_NUMBER: CARD}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Options update the entry and the coordinator's interval without a boost."""
    aioclient_mock.get(OFFERS_URL, json=load_json("offers_mixed.json"))
    entry = make_entry(hass)
    await setup_entry(hass, entry)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL_HOURS: 12, CONF_AUTO_BOOST: True}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_SCAN_INTERVAL_HOURS: 12, CONF_AUTO_BOOST: True}
    assert entry.runtime_data.update_interval == timedelta(hours=12)
    assert all(call[0].upper() == "GET" for call in aioclient_mock.mock_calls)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config_flow.py -v`
Expected: FAIL — `async_init` returns an abort/`UnknownHandler` because no config flow is registered for `everyday_rewards`.

- [ ] **Step 3: Implement the flows**

`custom_components/everyday_rewards/config_flow.py`:

```python
"""Config flow for Everyday Rewards."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .api import EverydayRewardsClient, EverydayRewardsError, InvalidCardError
from .const import (
    CONF_AUTO_BOOST,
    CONF_CARD_NUMBER,
    CONF_HASHED_CRN,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_AUTO_BOOST,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

CARD_NUMBER_RE = re.compile(r"\d{13}")

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CARD_NUMBER): str,
        vol.Optional(CONF_NAME): str,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL_HOURS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=24)
        ),
        vol.Required(CONF_AUTO_BOOST): bool,
    }
)


class EverydayRewardsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add an Everyday Rewards account by card number."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a card number and resolve it to an account."""
        errors: dict[str, str] = {}
        if user_input is not None:
            card_number = re.sub(r"\s", "", user_input[CONF_CARD_NUMBER])
            if not CARD_NUMBER_RE.fullmatch(card_number):
                errors[CONF_CARD_NUMBER] = "invalid_card_format"
            else:
                client = EverydayRewardsClient(async_get_clientsession(self.hass))
                try:
                    account = await client.resolve_account(card_number)
                except InvalidCardError:
                    errors["base"] = "invalid_card"
                except EverydayRewardsError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Unexpected error resolving card")
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(account.hashed_crn)
                    self._abort_if_unique_id_configured()
                    name = (
                        user_input.get(CONF_NAME)
                        or account.first_name
                        or "Everyday Rewards"
                    )
                    return self.async_create_entry(
                        title=name,
                        data={
                            CONF_CARD_NUMBER: card_number,
                            CONF_HASHED_CRN: account.hashed_crn,
                            CONF_NAME: name,
                        },
                        options={
                            CONF_SCAN_INTERVAL_HOURS: DEFAULT_SCAN_INTERVAL_HOURS,
                            CONF_AUTO_BOOST: DEFAULT_AUTO_BOOST,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return EverydayRewardsOptionsFlow()


class EverydayRewardsOptionsFlow(OptionsFlow):
    """Change polling interval and auto-boost."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and save the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config_flow.py -v`
Expected: all 7 PASS.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check . --fix && .venv/bin/ruff format .
.venv/bin/pytest -q
git add custom_components tests
git commit -m "Add config and options flows

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Sensors, button and switch

**Files:**
- Create: `custom_components/everyday_rewards/entity.py`, `custom_components/everyday_rewards/sensor.py`, `custom_components/everyday_rewards/button.py`, `custom_components/everyday_rewards/switch.py`
- Modify: `custom_components/everyday_rewards/__init__.py` — the `PLATFORMS` line
- Test: `tests/test_entities.py`

**Interfaces:**
- Consumes: `EverydayRewardsCoordinator` (`data`, `auto_boost`, `async_boost_now()`, `config_entry`), `CoordinatorData.available/boosted/last_run`, `RunResult`, `EverydayRewardsConfigEntry` (Task 2); translation keys `available_offers`, `boosted_offers`, `last_boost`, `boost_all`, `auto_boost` (Task 2 `en.json`).
- Produces: `EverydayRewardsEntity(coordinator, key)` base class (unique ID `f"{entry.entry_id}_{key}"`, device identifiers `{(DOMAIN, entry.entry_id)}`, device name `entry.title`). Entity IDs for an entry titled "Alex": `sensor.alex_available_offers`, `sensor.alex_boosted_offers`, `sensor.alex_last_boost`, `button.alex_boost_all`, `switch.alex_auto_boost`.

- [ ] **Step 1: Write the failing entity tests**

`tests/test_entities.py`:

```python
"""Tests for Everyday Rewards entities."""

from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.everyday_rewards.const import CONF_AUTO_BOOST, DOMAIN

from .helpers import (
    BOOST_URL,
    CARD,
    HASH,
    OFFERS_URL,
    load_json,
    make_entry,
    methods,
    setup_entry,
)


async def _setup(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    aioclient_mock.get(OFFERS_URL, json=load_json("offers_mixed.json"))
    aioclient_mock.post(BOOST_URL, json=load_json("boost_success.json"))
    entry = make_entry(hass, auto_boost=False)
    await setup_entry(hass, entry)
    return entry


async def test_offer_sensors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Offer counts and lists are exposed without secrets."""
    await _setup(hass, aioclient_mock)

    available = hass.states.get("sensor.alex_available_offers")
    assert available.state == "2"
    assert available.attributes["offers"] == [
        {
            "heading": "Collect 3000 points",
            "points": 3000,
            "ends": "2026-10-04T23:59:59+10:00",
        },
        {
            "heading": "Collect 600 points",
            "points": 600,
            "ends": "2026-10-04T23:59:59+10:00",
        },
    ]
    assert hass.states.get("sensor.alex_boosted_offers").state == "1"
    assert hass.states.get("sensor.alex_last_boost").state == STATE_UNKNOWN

    for state in hass.states.async_all():
        assert CARD not in str(state.as_dict())
        assert HASH not in str(state.as_dict())


async def test_device(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Each account is one service device named after the entry."""
    entry = await _setup(hass, aioclient_mock)

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    assert device.name == "Alex"
    assert device.entry_type is dr.DeviceEntryType.SERVICE


async def test_boost_all_button(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Pressing the button boosts now and updates the last-boost sensor."""
    await _setup(hass, aioclient_mock)

    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: "button.alex_boost_all"}, blocking=True
    )

    assert "POST" in methods(aioclient_mock)
    last = hass.states.get("sensor.alex_last_boost")
    assert last.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
    assert last.attributes["boosted"] == 2
    assert last.attributes["failed"] == 0
    assert last.attributes["last_error"] is None


async def test_auto_boost_switch(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The switch reflects and updates the auto-boost option without boosting."""
    entry = await _setup(hass, aioclient_mock)
    assert hass.states.get("switch.alex_auto_boost").state == STATE_OFF

    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: "switch.alex_auto_boost"}, blocking=True
    )
    await hass.async_block_till_done()

    assert entry.options[CONF_AUTO_BOOST] is True
    assert hass.states.get("switch.alex_auto_boost").state == STATE_ON
    assert "POST" not in methods(aioclient_mock)

    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: "switch.alex_auto_boost"}, blocking=True
    )
    await hass.async_block_till_done()

    assert entry.options[CONF_AUTO_BOOST] is False
    assert hass.states.get("switch.alex_auto_boost").state == STATE_OFF
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_entities.py -v`
Expected: FAIL — `hass.states.get("sensor.alex_available_offers")` is `None` (`AttributeError: 'NoneType' object has no attribute 'state'`).

- [ ] **Step 3: Implement the base entity**

`custom_components/everyday_rewards/entity.py`:

```python
"""Base entity for Everyday Rewards."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EverydayRewardsCoordinator


class EverydayRewardsEntity(CoordinatorEntity[EverydayRewardsCoordinator]):
    """An entity belonging to one Everyday Rewards account."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EverydayRewardsCoordinator, key: str) -> None:
        """Initialise the entity; key is also the translation key."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Woolworths",
            model="Everyday Rewards",
            entry_type=DeviceEntryType.SERVICE,
        )
```

- [ ] **Step 4: Implement the sensors**

`custom_components/everyday_rewards/sensor.py`:

```python
"""Sensors for Everyday Rewards."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .api import Offer
from .coordinator import (
    CoordinatorData,
    EverydayRewardsConfigEntry,
    EverydayRewardsCoordinator,
)
from .entity import EverydayRewardsEntity


@dataclass(frozen=True, kw_only=True)
class EverydayRewardsSensorDescription(SensorEntityDescription):
    """Describes an Everyday Rewards sensor."""

    value_fn: Callable[[CoordinatorData], StateType | datetime]
    attrs_fn: Callable[[CoordinatorData], dict[str, Any]]


def _offer_list(offers: Iterable[Offer]) -> dict[str, Any]:
    return {
        "offers": [
            {
                "heading": offer.heading,
                "points": offer.points,
                "ends": offer.ends.isoformat() if offer.ends else None,
            }
            for offer in offers
        ]
    }


def _last_run_attrs(data: CoordinatorData) -> dict[str, Any]:
    run = data.last_run
    if run is None:
        return {}
    return {
        "boosted": len(run.boosted),
        "failed": len(run.failed),
        "last_error": run.error,
    }


SENSORS: tuple[EverydayRewardsSensorDescription, ...] = (
    EverydayRewardsSensorDescription(
        key="available_offers",
        value_fn=lambda data: len(data.available),
        attrs_fn=lambda data: _offer_list(data.available),
    ),
    EverydayRewardsSensorDescription(
        key="boosted_offers",
        value_fn=lambda data: len(data.boosted),
        attrs_fn=lambda data: _offer_list(data.boosted),
    ),
    EverydayRewardsSensorDescription(
        key="last_boost",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.last_run.time if data.last_run else None,
        attrs_fn=_last_run_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EverydayRewardsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create sensors for one account."""
    coordinator = entry.runtime_data
    async_add_entities(
        EverydayRewardsSensor(coordinator, description) for description in SENSORS
    )


class EverydayRewardsSensor(EverydayRewardsEntity, SensorEntity):
    """A sensor backed by the account coordinator."""

    _unrecorded_attributes = frozenset({"offers"})
    entity_description: EverydayRewardsSensorDescription

    def __init__(
        self,
        coordinator: EverydayRewardsCoordinator,
        description: EverydayRewardsSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return offer details or last-run details."""
        return self.entity_description.attrs_fn(self.coordinator.data)
```

- [ ] **Step 5: Implement the button and switch**

`custom_components/everyday_rewards/button.py`:

```python
"""Boost-all button for Everyday Rewards."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EverydayRewardsConfigEntry, EverydayRewardsCoordinator
from .entity import EverydayRewardsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EverydayRewardsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the boost-all button for one account."""
    async_add_entities([BoostAllButton(entry.runtime_data)])


class BoostAllButton(EverydayRewardsEntity, ButtonEntity):
    """Boost every available offer now."""

    def __init__(self, coordinator: EverydayRewardsCoordinator) -> None:
        """Initialise the button."""
        super().__init__(coordinator, "boost_all")

    async def async_press(self) -> None:
        """Boost now."""
        await self.coordinator.async_boost_now()
```

`custom_components/everyday_rewards/switch.py`:

```python
"""Auto-boost switch for Everyday Rewards."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_AUTO_BOOST
from .coordinator import EverydayRewardsConfigEntry, EverydayRewardsCoordinator
from .entity import EverydayRewardsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EverydayRewardsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the auto-boost switch for one account."""
    async_add_entities([AutoBoostSwitch(entry.runtime_data)])


class AutoBoostSwitch(EverydayRewardsEntity, SwitchEntity):
    """Turns scheduled boosting on or off (stored in entry options)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EverydayRewardsCoordinator) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, "auto_boost")

    @property
    def is_on(self) -> bool:
        """Return whether auto-boost is enabled."""
        return self.coordinator.auto_boost

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable auto-boost."""
        self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable auto-boost."""
        self._set(False)

    def _set(self, value: bool) -> None:
        entry = self.coordinator.config_entry
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_AUTO_BOOST: value}
        )
        self.async_write_ha_state()
```

- [ ] **Step 6: Register the platforms**

In `custom_components/everyday_rewards/__init__.py`, replace:

```python
PLATFORMS: list[Platform] = []
```

with:

```python
PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_entities.py -v`
Expected: all 4 PASS.

- [ ] **Step 8: Lint and commit**

```bash
.venv/bin/ruff check . --fix && .venv/bin/ruff format .
.venv/bin/pytest -q
git add custom_components tests
git commit -m "Add offer sensors, boost button and auto-boost switch

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `boost_all` service and multi-account behaviour

**Files:**
- Create: `custom_components/everyday_rewards/services.py`, `custom_components/everyday_rewards/services.yaml`
- Modify: `custom_components/everyday_rewards/__init__.py` — add `CONFIG_SCHEMA` and `async_setup`
- Test: `tests/test_services.py`

**Interfaces:**
- Consumes: `EverydayRewardsCoordinator.async_boost_now()`, `EverydayRewardsConfigEntry` (Task 2); `SERVICE_BOOST_ALL`, `DOMAIN` (Task 1); entity IDs from Task 4; helpers `make_entry`, `CARD_2`, `HASH`, `HASH_2`.
- Produces: service `everyday_rewards.boost_all` with optional `device_id` (string or list). No device → all loaded accounts. Unknown device → `ServiceValidationError`.

- [ ] **Step 1: Write the failing service tests**

`tests/test_services.py`:

```python
"""Tests for the boost_all service and multiple accounts."""

from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.everyday_rewards.const import DOMAIN, SERVICE_BOOST_ALL

from .helpers import (
    BOOST_URL,
    CARD_2,
    HASH,
    HASH_2,
    OFFERS_URL,
    load_json,
    make_entry,
)


async def _setup_two(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> tuple[MockConfigEntry, MockConfigEntry]:
    aioclient_mock.get(OFFERS_URL, json=load_json("offers_mixed.json"))
    aioclient_mock.post(BOOST_URL, json=load_json("boost_success.json"))
    alex = make_entry(hass)
    sam = make_entry(hass, title="Sam", card=CARD_2, hashed_crn=HASH_2)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    return alex, sam


def _boosted_hashes(aioclient_mock: AiohttpClientMocker) -> list[str]:
    return [
        call[3]["hashcrn"]
        for call in aioclient_mock.mock_calls
        if call[0].upper() == "POST"
    ]


async def test_two_accounts_have_separate_entities(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Each account gets its own device and entities."""
    alex, sam = await _setup_two(hass, aioclient_mock)

    registry = dr.async_get(hass)
    assert registry.async_get_device(identifiers={(DOMAIN, alex.entry_id)})
    assert registry.async_get_device(identifiers={(DOMAIN, sam.entry_id)})
    assert hass.states.get("sensor.alex_available_offers").state == "2"
    assert hass.states.get("sensor.sam_available_offers").state == "2"


async def test_boost_all_targets_one_account(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Targeting a device boosts only that account."""
    _, sam = await _setup_two(hass, aioclient_mock)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, sam.entry_id)})

    await hass.services.async_call(
        DOMAIN, SERVICE_BOOST_ALL, {ATTR_DEVICE_ID: device.id}, blocking=True
    )

    assert _boosted_hashes(aioclient_mock) == [HASH_2]
    assert hass.states.get("sensor.sam_last_boost").attributes["boosted"] == 2
    assert "boosted" not in hass.states.get("sensor.alex_last_boost").attributes


async def test_boost_all_without_target_boosts_everyone(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """No target boosts every loaded account."""
    await _setup_two(hass, aioclient_mock)

    await hass.services.async_call(DOMAIN, SERVICE_BOOST_ALL, {}, blocking=True)

    assert sorted(_boosted_hashes(aioclient_mock)) == [HASH, HASH_2]


async def test_boost_all_unknown_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An unknown device ID is a validation error."""
    await _setup_two(hass, aioclient_mock)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, SERVICE_BOOST_ALL, {ATTR_DEVICE_ID: "nope"}, blocking=True
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_services.py -v`
Expected: `test_two_accounts_have_separate_entities` PASSES (Task 4 already supports it); the other three FAIL with `ServiceNotFound: Action everyday_rewards.boost_all not found`.

- [ ] **Step 3: Implement the service**

`custom_components/everyday_rewards/services.py`:

```python
"""Services for Everyday Rewards."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
)
import voluptuous as vol

from .const import DOMAIN, SERVICE_BOOST_ALL
from .coordinator import EverydayRewardsConfigEntry

BOOST_ALL_SCHEMA = vol.Schema(
    {vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string])}
)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services."""
    hass.services.async_register(
        DOMAIN, SERVICE_BOOST_ALL, _async_boost_all, schema=BOOST_ALL_SCHEMA
    )


async def _async_boost_all(call: ServiceCall) -> None:
    entries: list[EverydayRewardsConfigEntry] = [
        entry
        for entry in call.hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if device_ids := call.data.get(ATTR_DEVICE_ID):
        registry = dr.async_get(call.hass)
        wanted: set[str] = set()
        for device_id in device_ids:
            if (device := registry.async_get(device_id)) is None:
                raise ServiceValidationError(f"Unknown device: {device_id}")
            wanted.update(device.config_entries)
        entries = [entry for entry in entries if entry.entry_id in wanted]

    for entry in entries:
        await entry.runtime_data.async_boost_now()
```

`custom_components/everyday_rewards/services.yaml`:

```yaml
boost_all:
  fields:
    device_id:
      required: false
      selector:
        device:
          integration: everyday_rewards
          multiple: true
```

- [ ] **Step 4: Register the service at integration setup**

In `custom_components/everyday_rewards/__init__.py`:

Replace the import block:

```python
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EverydayRewardsClient
from .coordinator import (
    EverydayRewardsConfigEntry,
    EverydayRewardsCoordinator,
    scan_interval,
)
```

with:

```python
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import EverydayRewardsClient
from .const import DOMAIN
from .coordinator import (
    EverydayRewardsConfigEntry,
    EverydayRewardsCoordinator,
    scan_interval,
)
from .services import async_setup_services
```

and directly after the `PLATFORMS` line add:

```python

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services once for all accounts."""
    async_setup_services(hass)
    return True
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_services.py -v`
Expected: all 4 PASS.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check . --fix && .venv/bin/ruff format .
.venv/bin/pytest -q
git add custom_components tests
git commit -m "Add boost_all service with per-account targeting

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Redacted diagnostics

**Files:**
- Create: `custom_components/everyday_rewards/diagnostics.py`
- Test: `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: `EverydayRewardsConfigEntry`, `CoordinatorData` (Task 2); `CONF_CARD_NUMBER`, `CONF_HASHED_CRN` (Task 1).
- Produces: `async_get_config_entry_diagnostics(hass, entry) -> dict[str, Any]` returning `{"entry": {"title", "data", "options"}, "offers": [...], "last_run": {...} | None}` with `card_number`, `hashed_crn`, `name`, `title` redacted.

- [ ] **Step 1: Write the failing diagnostics test**

`tests/test_diagnostics.py`:

```python
"""Tests for Everyday Rewards diagnostics."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.everyday_rewards.const import (
    CONF_AUTO_BOOST,
    CONF_CARD_NUMBER,
    CONF_HASHED_CRN,
)
from custom_components.everyday_rewards.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .helpers import (
    BOOST_URL,
    CARD,
    HASH,
    OFFERS_URL,
    load_json,
    make_entry,
    setup_entry,
)

REDACTED = "**REDACTED**"


async def test_diagnostics_redacts_secrets(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Diagnostics include offers and run state but no identifying data."""
    aioclient_mock.get(OFFERS_URL, json=load_json("offers_mixed.json"))
    aioclient_mock.post(BOOST_URL, json=load_json("boost_success.json"))
    entry = make_entry(hass, auto_boost=True)
    await setup_entry(hass, entry)

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry"]["title"] == REDACTED
    assert result["entry"]["data"][CONF_CARD_NUMBER] == REDACTED
    assert result["entry"]["data"][CONF_HASHED_CRN] == REDACTED
    assert result["entry"]["data"]["name"] == REDACTED
    assert result["entry"]["options"][CONF_AUTO_BOOST] is True
    assert len(result["offers"]) == 4
    assert result["last_run"]["boosted"] == ("Collect 3000 points", "Collect 600 points")
    dumped = str(result)
    assert CARD not in dumped
    assert HASH not in dumped
    assert "Alex" not in dumped
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_diagnostics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.everyday_rewards.diagnostics'`.

- [ ] **Step 3: Implement diagnostics**

`custom_components/everyday_rewards/diagnostics.py`:

```python
"""Diagnostics for Everyday Rewards."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant

from .const import CONF_CARD_NUMBER, CONF_HASHED_CRN
from .coordinator import EverydayRewardsConfigEntry

TO_REDACT = {CONF_CARD_NUMBER, CONF_HASHED_CRN, CONF_NAME, "title"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EverydayRewardsConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with account identifiers removed."""
    data = entry.runtime_data.data
    return async_redact_data(
        {
            "entry": {
                "title": entry.title,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            "offers": [asdict(offer) for offer in data.offers],
            "last_run": asdict(data.last_run) if data.last_run else None,
        },
        TO_REDACT,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_diagnostics.py -v`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check . --fix && .venv/bin/ruff format .
.venv/bin/pytest -q
git add custom_components tests
git commit -m "Add redacted diagnostics

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: HACS packaging, CI, docs and capture cleanup

**Files:**
- Create: `hacs.json`, `README.md`, `CLAUDE.md`, `.github/workflows/validate.yml`
- Delete: `.playwright-mcp/` (local browser captures containing real account data; gitignored, never committed)

**Interfaces:**
- Consumes: the whole integration (Tasks 1–6).
- Produces: a repo that passes `pytest`, `ruff check`, and is structured for hassfest/HACS validation in CI.

- [ ] **Step 1: Add HACS metadata**

`hacs.json`:

```json
{
  "name": "Everyday Rewards Auto-Boost",
  "homeassistant": "2026.9.0",
  "render_readme": true
}
```

- [ ] **Step 2: Add the CI workflow**

`.github/workflows/validate.yml`:

```yaml
name: Validate

on:
  push:
  pull_request:

jobs:
  hassfest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: home-assistant/actions/hassfest@master

  hacs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hacs/action@main
        with:
          category: integration
          ignore: brands

  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
      - run: pip install -r requirements_test.txt
      - run: ruff check .
      - run: ruff format --check .
      - run: pytest
```

- [ ] **Step 3: Write the README**

`README.md`:

````markdown
# Everyday Rewards Auto-Boost for Home Assistant

Automatically boosts every available Woolworths Everyday Rewards offer, for as many accounts as you like.

> **Unofficial.** This integration uses the same undocumented API as the Everyday Rewards "boost" web widget. Woolworths can change or block it at any time. If that happens, Home Assistant shows a repair issue and the integration stops until it is updated.

## Install

1. In HACS, open **Integrations → ⋮ → Custom repositories** and add `https://github.com/vwylaw/ha-everyday-rewards` as an **Integration**.
2. Install **Everyday Rewards Auto-Boost** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → Everyday Rewards Auto-Boost**.
4. Enter the 13-digit card number (on the card or in the app under **Card**). Optionally give the account a name.

Repeat step 3 for each account.

**Treat card numbers like passwords.** With this API, anyone who has a card number can boost offers on that account. The integration stores the number in Home Assistant's config storage and keeps it out of entity states, logs and diagnostics.

## What you get (per account)

| Entity | What it shows |
|---|---|
| `sensor.<name>_available_offers` | Offers not yet boosted; the `offers` attribute lists heading, points and end date |
| `sensor.<name>_boosted_offers` | Boosted offers that are still running |
| `sensor.<name>_last_boost` | When the last boost ran; attributes `boosted`, `failed`, `last_error` |
| `button.<name>_boost_all` | Boost everything now |
| `switch.<name>_auto_boost` | Turn scheduled boosting on or off |

Options (**Configure** on the integration): how often to check for new offers (1–24 hours, default 6) and whether to boost automatically (default on).

Points balance is not available: the API only returns it after a full password login.

## Service

`everyday_rewards.boost_all` boosts every available offer. Pass `device_id` to limit it to particular accounts; with no target it boosts all accounts.

## Event and automation example

After each boost the integration fires `everyday_rewards_boosted` with `entry_id`, `account`, `boosted`, `failed` and `offers` (headings).

```yaml
automation:
  - alias: Tell me what got boosted
    triggers:
      - trigger: event
        event_type: everyday_rewards_boosted
    conditions:
      - condition: template
        value_template: "{{ trigger.event.data.boosted > 0 }}"
    actions:
      - action: notify.notify
        data:
          message: >
            Boosted {{ trigger.event.data.boosted }} offers for
            {{ trigger.event.data.account }}:
            {{ trigger.event.data.offers | join(', ') }}
```

## Development

```bash
/opt/homebrew/bin/python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```
````

- [ ] **Step 4: Write CLAUDE.md**

`CLAUDE.md`:

````markdown
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
- Tests use `aioclient_mock` with fake IDs (`tests/helpers.py`). Never use real card numbers or real captured responses. `.playwright-mcp/` is gitignored because it holds live browser captures.
````

- [ ] **Step 5: Delete the raw browser captures**

These hold the real card's `hashed_crn` and offer data and are no longer needed now that sanitised fixtures exist.

```bash
ls .playwright-mcp | head
rm -rf .playwright-mcp
git status --short
```

Expected: `git status` shows only the new files from this task (`.playwright-mcp/` was never tracked).

- [ ] **Step 6: Full verification**

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest -v
grep -rnoE "\b93[0-9]{11}\b" custom_components tests README.md CLAUDE.md docs | grep -vE ":930000000000[12]$" || echo "only fake card numbers in repo"
```

Expected: ruff reports no issues; every test passes (API 15, coordinator 8, config flow 7, entities 4, services 4, diagnostics 1 = 39); the grep prints `only fake card numbers in repo`.

- [ ] **Step 7: Commit**

```bash
git add hacs.json README.md CLAUDE.md .github
git commit -m "Add HACS metadata, CI workflow, README and CLAUDE.md

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
