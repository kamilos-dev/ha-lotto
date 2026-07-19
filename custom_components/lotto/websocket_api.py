"""Websocket API used by the Lotto sidebar panel."""
from __future__ import annotations

import logging
import uuid
from datetime import date

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EVENT_UPDATED, GAME_TYPES, STATUS_ACTIVE
from .rules import GAME_RULES, validate_numbers as rules_validate_numbers

_LOGGER = logging.getLogger(__name__)


def _entry_data(hass: HomeAssistant) -> dict:
    """Return the (single) config entry's runtime data."""
    return next(iter(hass.data[DOMAIN].values()))


@callback
def async_register_websocket_api(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, websocket_get_rules)
    websocket_api.async_register_command(hass, websocket_list_coupons)
    websocket_api.async_register_command(hass, websocket_add_coupon)
    websocket_api.async_register_command(hass, websocket_delete_coupon)


@websocket_api.websocket_command({vol.Required("type"): "lotto/get_rules"})
@callback
def websocket_get_rules(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    connection.send_result(msg["id"], {game: GAME_RULES[game].as_dict() for game in GAME_TYPES})


@websocket_api.websocket_command({vol.Required("type"): "lotto/list_coupons"})
@callback
def websocket_list_coupons(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    store = _entry_data(hass)["store"]
    connection.send_result(msg["id"], {"coupons": store.coupons})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "lotto/add_coupon",
        vol.Required("game_type"): vol.In(GAME_TYPES),
        vol.Required("numbers"): [vol.Coerce(int)],
        vol.Optional("euro_numbers", default=[]): [vol.Coerce(int)],
        vol.Required("draws_total"): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
        vol.Required("first_draw_date"): str,
    }
)
@websocket_api.async_response
async def websocket_add_coupon(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    try:
        rules_validate_numbers(msg["game_type"], msg["numbers"], msg["euro_numbers"])
        first_draw_date = date.fromisoformat(msg["first_draw_date"])
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_coupon", str(err))
        return

    coupon = {
        "id": uuid.uuid4().hex,
        "game_type": msg["game_type"],
        "numbers": sorted(msg["numbers"]),
        "euro_numbers": sorted(msg["euro_numbers"]),
        "first_draw_date": first_draw_date.isoformat(),
        "draws_total": msg["draws_total"],
        "draws_remaining": msg["draws_total"],
        "status": STATUS_ACTIVE,
        "created_at": dt_util.utcnow().isoformat(),
        "checked_draws": [],
    }

    data = _entry_data(hass)
    await data["store"].async_add(coupon)
    connection.send_result(msg["id"], {"coupon": coupon})
    hass.bus.async_fire(EVENT_UPDATED, {})

    # Check immediately in case first_draw_date is already in the past.
    await data["coordinator"].async_request_refresh()


@websocket_api.websocket_command(
    {
        vol.Required("type"): "lotto/delete_coupon",
        vol.Required("coupon_id"): str,
    }
)
@websocket_api.async_response
async def websocket_delete_coupon(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    store = _entry_data(hass)["store"]
    removed = await store.async_remove(msg["coupon_id"])
    if not removed:
        connection.send_error(msg["id"], "not_found", "Nie znaleziono kuponu.")
        return
    connection.send_result(msg["id"], {})
    hass.bus.async_fire(EVENT_UPDATED, {})
