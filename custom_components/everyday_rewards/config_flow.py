"""Config flow for Everyday Rewards."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .api import EverydayRewardsClient, EverydayRewardsError, InvalidCardError
from .const import (
    CONF_AUTO_BOOST,
    CONF_CARD_NUMBER,
    CONF_HASHED_CRN,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_AUTO_BOOST,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

CARD_NUMBER_RE = re.compile(r"\d{13}")

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CARD_NUMBER): str,
        vol.Optional(CONF_NAME): str,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL_HOURS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=24)
        ),
        vol.Required(CONF_AUTO_BOOST): bool,
    }
)


class EverydayRewardsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add an Everyday Rewards account by card number."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a card number and resolve it to an account."""
        errors: dict[str, str] = {}
        if user_input is not None:
            card_number = re.sub(r"\s", "", user_input[CONF_CARD_NUMBER])
            if not CARD_NUMBER_RE.fullmatch(card_number):
                errors[CONF_CARD_NUMBER] = "invalid_card_format"
            else:
                client = EverydayRewardsClient(async_get_clientsession(self.hass))
                try:
                    account = await client.resolve_account(card_number)
                except InvalidCardError:
                    errors["base"] = "invalid_card"
                except EverydayRewardsError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Unexpected error resolving card")
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(account.hashed_crn)
                    self._abort_if_unique_id_configured()
                    name = (
                        user_input.get(CONF_NAME)
                        or account.first_name
                        or "Everyday Rewards"
                    )
                    return self.async_create_entry(
                        title=name,
                        data={
                            CONF_CARD_NUMBER: card_number,
                            CONF_HASHED_CRN: account.hashed_crn,
                            CONF_NAME: name,
                        },
                        options={
                            CONF_SCAN_INTERVAL_HOURS: DEFAULT_SCAN_INTERVAL_HOURS,
                            CONF_AUTO_BOOST: DEFAULT_AUTO_BOOST,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return EverydayRewardsOptionsFlow()


class EverydayRewardsOptionsFlow(OptionsFlow):
    """Change polling interval and auto-boost."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and save the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
