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
