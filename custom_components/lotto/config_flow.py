"""Config flow for the Lotto integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_POLL_INTERVAL_HOURS,
    DEFAULT_POLL_INTERVAL_HOURS,
    DOMAIN,
    MAX_POLL_INTERVAL_HOURS,
    MIN_POLL_INTERVAL_HOURS,
)
from .lotto_api import LottoApiAuthError, LottoApiClient, LottoApiError

_LOGGER = logging.getLogger(__name__)


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_API_KEY, default=defaults.get(CONF_API_KEY, "")): str,
            vol.Optional(
                CONF_POLL_INTERVAL_HOURS,
                default=defaults.get(CONF_POLL_INTERVAL_HOURS, DEFAULT_POLL_INTERVAL_HOURS),
            ): vol.All(int, vol.Range(min=MIN_POLL_INTERVAL_HOURS, max=MAX_POLL_INTERVAL_HOURS)),
        }
    )


class LottoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance config flow: asks for the Lotto Open API key."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_validate(user_input)
            if not errors:
                return self.async_create_entry(title="Lotto", data=user_input)

        return self.async_show_form(step_id="user", data_schema=_schema(user_input), errors=errors)

    async def _async_validate(self, user_input: dict[str, Any]) -> dict[str, str]:
        session = async_get_clientsession(self.hass)
        client = LottoApiClient(session, user_input[CONF_API_KEY])
        try:
            await client.async_verify_api_key()
        except LottoApiAuthError:
            return {"base": "invalid_auth"}
        except LottoApiError:
            return {"base": "cannot_connect"}
        return {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> LottoOptionsFlow:
        return LottoOptionsFlow(config_entry)


class LottoOptionsFlow(OptionsFlow):
    """Lets the user update the API key / poll interval later."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        errors: dict[str, str] = {}
        current = {**self._config_entry.data, **self._config_entry.options}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = LottoApiClient(session, user_input[CONF_API_KEY])
            try:
                await client.async_verify_api_key()
            except LottoApiAuthError:
                errors["base"] = "invalid_auth"
            except LottoApiError:
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init", data_schema=_schema(user_input or current), errors=errors
        )
