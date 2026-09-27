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
