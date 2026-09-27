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
