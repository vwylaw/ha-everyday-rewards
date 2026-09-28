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
            "name": "when you spend $60 or more at BIG W.",
            "heading": "Collect 3000 points",
            "points": 3000,
            "ends": "2026-10-04T23:59:59+10:00",
        },
        {
            "name": "when you spend $60 or more at Ampol Foodary.",
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

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
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
