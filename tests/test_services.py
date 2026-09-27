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
    assert registry.async_get_device_by_identifier(
        (DOMAIN, alex.entry_id), alex.entry_id
    )
    assert registry.async_get_device_by_identifier((DOMAIN, sam.entry_id), sam.entry_id)
    assert hass.states.get("sensor.alex_available_offers").state == "2"
    assert hass.states.get("sensor.sam_available_offers").state == "2"


async def test_boost_all_targets_one_account(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Targeting a device boosts only that account."""
    _, sam = await _setup_two(hass, aioclient_mock)
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, sam.entry_id), sam.entry_id
    )

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
