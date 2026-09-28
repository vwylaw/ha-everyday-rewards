"""Sensors for Everyday Rewards."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .api import Offer
from .coordinator import (
    CoordinatorData,
    EverydayRewardsConfigEntry,
    EverydayRewardsCoordinator,
)
from .entity import EverydayRewardsEntity


@dataclass(frozen=True, kw_only=True)
class EverydayRewardsSensorDescription(SensorEntityDescription):
    """Describes an Everyday Rewards sensor."""

    value_fn: Callable[[CoordinatorData], StateType | datetime]
    attrs_fn: Callable[[CoordinatorData], dict[str, Any]]


def _offer_list(offers: Iterable[Offer]) -> dict[str, Any]:
    return {
        "offers": [
            {
                "name": offer.name,
                "heading": offer.heading,
                "points": offer.points,
                "ends": offer.ends.isoformat() if offer.ends else None,
            }
            for offer in offers
        ]
    }


def _last_run_attrs(data: CoordinatorData) -> dict[str, Any]:
    run = data.last_run
    if run is None:
        return {}
    return {
        "boosted": len(run.boosted),
        "failed": len(run.failed),
        "last_error": run.error,
    }


SENSORS: tuple[EverydayRewardsSensorDescription, ...] = (
    EverydayRewardsSensorDescription(
        key="available_offers",
        value_fn=lambda data: len(data.available),
        attrs_fn=lambda data: _offer_list(data.available),
    ),
    EverydayRewardsSensorDescription(
        key="boosted_offers",
        value_fn=lambda data: len(data.boosted),
        attrs_fn=lambda data: _offer_list(data.boosted),
    ),
    EverydayRewardsSensorDescription(
        key="last_boost",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.last_run.time if data.last_run else None,
        attrs_fn=_last_run_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EverydayRewardsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create sensors for one account."""
    coordinator = entry.runtime_data
    async_add_entities(
        EverydayRewardsSensor(coordinator, description) for description in SENSORS
    )


class EverydayRewardsSensor(EverydayRewardsEntity, SensorEntity):
    """A sensor backed by the account coordinator."""

    _unrecorded_attributes = frozenset({"offers"})
    entity_description: EverydayRewardsSensorDescription

    def __init__(
        self,
        coordinator: EverydayRewardsCoordinator,
        description: EverydayRewardsSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return offer details or last-run details."""
        return self.entity_description.attrs_fn(self.coordinator.data)
