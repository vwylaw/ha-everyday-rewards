"""Auto-boost switch for Everyday Rewards."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_AUTO_BOOST
from .coordinator import EverydayRewardsConfigEntry, EverydayRewardsCoordinator
from .entity import EverydayRewardsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EverydayRewardsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the auto-boost switch for one account."""
    async_add_entities([AutoBoostSwitch(entry.runtime_data)])


class AutoBoostSwitch(EverydayRewardsEntity, SwitchEntity):
    """Turns scheduled boosting on or off (stored in entry options)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EverydayRewardsCoordinator) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, "auto_boost")

    @property
    def is_on(self) -> bool:
        """Return whether auto-boost is enabled."""
        return self.coordinator.auto_boost

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable auto-boost."""
        self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable auto-boost."""
        self._set(False)

    def _set(self, value: bool) -> None:
        entry = self.coordinator.config_entry
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_AUTO_BOOST: value}
        )
        self.async_write_ha_state()
