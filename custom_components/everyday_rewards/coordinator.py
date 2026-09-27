"""Data update coordinator for Everyday Rewards."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AccessDeniedError, EverydayRewardsClient, EverydayRewardsError, Offer
from .const import (
    CONF_AUTO_BOOST,
    CONF_HASHED_CRN,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_AUTO_BOOST,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    EVENT_BOOSTED,
    ISSUE_ACCESS_DENIED,
)

_LOGGER = logging.getLogger(__name__)

ACCESS_DENIED_MESSAGE = (
    "Everyday Rewards denied access; the unofficial API may have changed"
)

type EverydayRewardsConfigEntry = ConfigEntry[EverydayRewardsCoordinator]


def scan_interval(entry: ConfigEntry) -> timedelta:
    """Return the configured polling interval for an entry."""
    return timedelta(
        hours=entry.options.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS)
    )


@dataclass(frozen=True)
class RunResult:
    """Outcome of one boost pass. Tuples hold offer headings."""

    time: datetime
    boosted: tuple[str, ...]
    failed: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True)
class CoordinatorData:
    """Everything the entities need for one account."""

    offers: tuple[Offer, ...]
    last_run: RunResult | None

    @property
    def available(self) -> list[Offer]:
        """Offers that can still be boosted."""
        return [offer for offer in self.offers if offer.boostable]

    @property
    def boosted(self) -> list[Offer]:
        """Offers that are boosted and still running."""
        return [offer for offer in self.offers if offer.boosted]


class EverydayRewardsCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Fetches offers for one account and boosts them."""

    config_entry: EverydayRewardsConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: EverydayRewardsConfigEntry,
        client: EverydayRewardsClient,
    ) -> None:
        """Initialise the coordinator for one config entry."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=scan_interval(entry),
        )
        self.client = client
        self._last_run: RunResult | None = None

    @property
    def auto_boost(self) -> bool:
        """Return whether scheduled refreshes should boost offers."""
        return self.config_entry.options.get(CONF_AUTO_BOOST, DEFAULT_AUTO_BOOST)

    async def _async_update_data(self) -> CoordinatorData:
        try:
            return await self._refresh(boost=self.auto_boost)
        except AccessDeniedError as err:
            self._report_access_denied()
            raise ConfigEntryError(ACCESS_DENIED_MESSAGE) from err
        except EverydayRewardsError as err:
            raise UpdateFailed(str(err)) from err

    async def async_boost_now(self) -> None:
        """Fetch and boost immediately, regardless of the auto-boost setting."""
        try:
            data = await self._refresh(boost=True)
        except AccessDeniedError as err:
            self._report_access_denied()
            raise HomeAssistantError(ACCESS_DENIED_MESSAGE) from err
        except EverydayRewardsError as err:
            raise HomeAssistantError(f"Could not boost offers: {err}") from err
        self.async_set_updated_data(data)

    async def _refresh(self, *, boost: bool) -> CoordinatorData:
        hashed_crn = self.config_entry.data[CONF_HASHED_CRN]
        offers = await self.client.get_offers(hashed_crn)
        if boost:
            self._last_run = await self._boost(hashed_crn, offers)
            if self._last_run.boosted:
                offers = await self.client.get_offers(hashed_crn)
        ir.async_delete_issue(self.hass, DOMAIN, ISSUE_ACCESS_DENIED)
        return CoordinatorData(offers=tuple(offers), last_run=self._last_run)

    async def _boost(self, hashed_crn: str, offers: list[Offer]) -> RunResult:
        boostable = {offer.id: offer for offer in offers if offer.boostable}
        now = dt_util.utcnow()
        if not boostable:
            return RunResult(time=now, boosted=(), failed=())

        try:
            results = await self.client.boost(hashed_crn, boostable)
        except AccessDeniedError:
            raise
        except EverydayRewardsError as err:
            _LOGGER.warning(
                "Boosting offers for %s failed: %s", self.config_entry.title, err
            )
            run = RunResult(
                time=now,
                boosted=(),
                failed=tuple(offer.heading for offer in boostable.values()),
                error=str(err),
            )
        else:
            succeeded = {result.offer_id for result in results if result.success}
            run = RunResult(
                time=now,
                boosted=tuple(
                    offer.heading
                    for offer_id, offer in boostable.items()
                    if offer_id in succeeded
                ),
                failed=tuple(
                    offer.heading
                    for offer_id, offer in boostable.items()
                    if offer_id not in succeeded
                ),
            )
            for heading in run.failed:
                _LOGGER.info(
                    "Could not boost '%s' for %s", heading, self.config_entry.title
                )

        self.hass.bus.async_fire(
            EVENT_BOOSTED,
            {
                "entry_id": self.config_entry.entry_id,
                "account": self.config_entry.title,
                "boosted": len(run.boosted),
                "failed": len(run.failed),
                "offers": list(run.boosted),
            },
        )
        return run

    def _report_access_denied(self) -> None:
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            ISSUE_ACCESS_DENIED,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=ISSUE_ACCESS_DENIED,
        )
