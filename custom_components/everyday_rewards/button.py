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
