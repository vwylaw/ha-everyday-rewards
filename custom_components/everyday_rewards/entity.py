"""Base entity for Everyday Rewards."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EverydayRewardsCoordinator


class EverydayRewardsEntity(CoordinatorEntity[EverydayRewardsCoordinator]):
    """An entity belonging to one Everyday Rewards account."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EverydayRewardsCoordinator, key: str) -> None:
        """Initialise the entity; key is also the translation key."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Woolworths",
            model="Everyday Rewards",
            entry_type=DeviceEntryType.SERVICE,
        )
