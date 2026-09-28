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
    assert result["offers"][0]["name"] == "when you spend $60 or more at BIG W."
    assert result["last_run"]["boosted"] == (
        "when you spend $60 or more at BIG W.",
        "when you spend $60 or more at Ampol Foodary.",
    )
    dumped = str(result)
    assert CARD not in dumped
    assert HASH not in dumped
    assert "Alex" not in dumped
