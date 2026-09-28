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
    return {
        # Only the entry holds account identifiers; offer "name" fields are not
        # personal and must stay readable.
        "entry": async_redact_data(
            {
                "title": entry.title,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            TO_REDACT,
        ),
        "offers": [asdict(offer) for offer in data.offers],
        "last_run": asdict(data.last_run) if data.last_run else None,
    }
