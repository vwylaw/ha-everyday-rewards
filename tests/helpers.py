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
