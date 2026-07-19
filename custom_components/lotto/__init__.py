"""The Lotto integration: sidebar panel to track lottery coupons and results."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_POLL_INTERVAL_HOURS,
    DEFAULT_POLL_INTERVAL_HOURS,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import LottoCoordinator
from .lotto_api import create_client
from .panel import async_setup_panel, async_unload_panel
from .store import LottoStore
from .websocket_api import async_register_websocket_api


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    settings = {**entry.data, **entry.options}

    store = LottoStore(hass)
    await store.async_load()

    session = async_get_clientsession(hass)
    api_client = create_client(session, settings.get(CONF_API_KEY) or None)

    coordinator = LottoCoordinator(
        hass,
        store,
        api_client,
        settings.get(CONF_POLL_INTERVAL_HOURS, DEFAULT_POLL_INTERVAL_HOURS),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "store": store,
        "coordinator": coordinator,
        "client": api_client,
    }

    async_register_websocket_api(hass)
    await async_setup_panel(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            async_unload_panel(hass)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
