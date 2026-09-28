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
