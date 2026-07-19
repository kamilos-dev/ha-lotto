"""Config flow for the Lotto integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_API_KEY,
    CONF_POLL_INTERVAL_HOURS,
    DEFAULT_POLL_INTERVAL_HOURS,
    DOMAIN,
    MAX_POLL_INTERVAL_HOURS,
    MIN_POLL_INTERVAL_HOURS,
)
from .lotto_api import LottoApiAuthError, LottoApiError, create_client

_LOGGER = logging.getLogger(__name__)


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Optional(CONF_API_KEY, default=defaults.get(CONF_API_KEY, "")): str,
            vol.Optional(
                CONF_POLL_INTERVAL_HOURS,
                default=defaults.get(CONF_POLL_INTERVAL_HOURS, DEFAULT_POLL_INTERVAL_HOURS),
            ): vol.All(
                NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_POLL_INTERVAL_HOURS,
                        max=MAX_POLL_INTERVAL_HOURS,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Coerce(int),
            ),
        }
    )


async def _async_validate(hass: Any, user_input: dict[str, Any]) -> dict[str, str]:
    """Verify a configured Open API key works.

    The key-free public provider is deliberately NOT pre-verified here: it's
    known to be blocked by lotto.pl's Cloudflare protection on some networks
    (requires a browser-obtained cf_clearance cookie plus a per-page
    request-token that a background HTTP client cannot reproduce), and that
    can't be told apart from a merely transient failure at setup time. Rather
    than hard-blocking installation on a check we can't trust, setup is
    allowed to proceed; the coordinator retries on its own schedule and logs
    the real HTTP status/error on every attempt.
    """
    api_key = user_input.get(CONF_API_KEY) or None
    if not api_key:
        return {}

    session = async_get_clientsession(hass)
    client = create_client(session, api_key)
    try:
        await client.async_verify_connection()
    except LottoApiAuthError as err:
        _LOGGER.warning("Weryfikacja klucza API nie powiodła się: %s", err)
        return {"base": "invalid_auth"}
    except LottoApiError as err:
        _LOGGER.warning("Nie udało się połączyć z Lotto Open API: %s", err)
        return {"base": "cannot_connect"}
    return {}


class LottoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance config flow.

    The API key is optional: leave it blank to use the free, unofficial
    lotto.pl results endpoint immediately; fill it in to use the official
    Lotto Open API instead.
    """

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _async_validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(title="Lotto", data=user_input)

        return self.async_show_form(step_id="user", data_schema=_schema(user_input), errors=errors)

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
            errors = await _async_validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init", data_schema=_schema(user_input or current), errors=errors
        )
