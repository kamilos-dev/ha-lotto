"""Registers the Lotto sidebar panel and its static frontend asset."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.frontend import async_remove_panel
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PANEL_ICON, PANEL_JS_VERSION, PANEL_TITLE, PANEL_URL_PATH

_LOGGER = logging.getLogger(__name__)

WWW_DIR = Path(__file__).parent / "www"
JS_URL_PATH = f"/lotto_panel/{PANEL_JS_VERSION}/lotto-panel.js"
_REGISTERED_KEY = f"{DOMAIN}_panel_registered"


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Serve the panel JS and add the sidebar entry (only once)."""
    if hass.data.get(_REGISTERED_KEY):
        return

    await hass.http.async_register_static_paths(
        [StaticPathConfig(JS_URL_PATH, str(WWW_DIR / "lotto-panel.js"), cache_headers=True)]
    )

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name="lotto-panel",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        module_url=JS_URL_PATH,
        embed_iframe=False,
        require_admin=False,
    )

    hass.data[_REGISTERED_KEY] = True


def async_unload_panel(hass: HomeAssistant) -> None:
    if not hass.data.get(_REGISTERED_KEY):
        return
    async_remove_panel(hass, PANEL_URL_PATH)
    hass.data[_REGISTERED_KEY] = False
