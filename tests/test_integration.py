"""End-to-end tests for the lotto custom component, run against a real
in-memory Home Assistant instance via pytest-homeassistant-custom-component.

async_setup_panel/async_unload_panel are mocked out in every test that sets
up a config entry: registering a real panel needs hass.http, which the bare
`hass` test fixture leaves as None (the http component isn't loaded), so
panel registration is out of scope here and covered by manual verification
instead (see README's "Ograniczenia" section).
"""
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lotto import websocket_api as ws
from custom_components.lotto.const import DOMAIN
from custom_components.lotto.lotto_api import DrawResult, LottoApiAuthError, LottoPublicApiClient


@patch("custom_components.lotto.async_unload_panel")
@patch("custom_components.lotto.async_setup_panel", new_callable=AsyncMock)
async def test_full_flow(mock_setup_panel, mock_unload_panel, hass, ws_connection):
    entry = MockConfigEntry(domain=DOMAIN, data={"api_key": "test-key", "poll_interval_hours": 4})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.lotto.lotto_api.LottoOpenApiClient.async_get_last_results",
        new=AsyncMock(return_value=[]),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state.value == "loaded"
    assert mock_setup_panel.await_count == 1

    state = hass.states.get("sensor.aktywne_kupony")
    assert state is not None
    assert state.state == "0"

    data = hass.data[DOMAIN][entry.entry_id]
    store = data["store"]
    coordinator = data["coordinator"]

    # --- Add a coupon via the websocket API layer ---
    with patch.object(coordinator, "async_request_refresh", new=AsyncMock()):
        # websocket_add_coupon is wrapped by @websocket_api.async_response,
        # which schedules it as a background task and returns None rather
        # than a coroutine to await - so call it, then let the loop drain.
        ws.websocket_add_coupon(
            hass,
            ws_connection,
            {
                "id": 1,
                "game_type": "Lotto",
                "numbers": [1, 2, 3, 4, 5, 6],
                "euro_numbers": [],
                "draws_total": 2,
                "first_draw_date": "2026-01-01",
            },
        )
        await hass.async_block_till_done()

    assert not ws_connection.errors, ws_connection.errors
    assert len(store.coupons) == 1
    coupon_id = store.coupons[0]["id"]

    list_connection = type(ws_connection)()
    ws.websocket_list_coupons(hass, list_connection, {"id": 2})
    assert len(list_connection.results[0]["coupons"]) == 1

    # --- Simulate a poll cycle where the draw matches (a win) ---
    win_events = []
    hass.bus.async_listen("lotto_win", lambda event: win_events.append(event.data))

    from homeassistant.components import persistent_notification as pn
    from homeassistant.helpers.dispatcher import async_dispatcher_connect

    notifications = []
    async_dispatcher_connect(
        hass,
        pn.SIGNAL_PERSISTENT_NOTIFICATIONS_UPDATED,
        lambda update_type, data: notifications.append(data),
    )

    winning_result = DrawResult(
        game_type="Lotto", draw_date=date(2026, 1, 1), numbers=[1, 2, 3, 4, 5, 6], euro_numbers=[]
    )
    with patch.object(
        coordinator.api_client, "async_get_last_results", new=AsyncMock(return_value=[winning_result])
    ):
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(win_events) == 1
    assert win_events[0]["matched_numbers"] == 6
    assert win_events[0]["coupon_id"] == coupon_id

    updated_coupon = store.get(coupon_id)
    assert updated_coupon["draws_remaining"] == 1
    assert updated_coupon["checked_draws"][0]["is_win"] is True

    assert len(notifications) == 1
    sent_notification = next(iter(notifications[0].values()))
    assert "trafi" in sent_notification[pn.ATTR_MESSAGE]

    sensor_state = hass.states.get("sensor.aktywne_kupony")
    assert sensor_state.state == "1"
    assert sensor_state.attributes["won_coupons"] == 1

    # --- Delete the coupon ---
    delete_connection = type(ws_connection)()
    ws.websocket_delete_coupon(hass, delete_connection, {"id": 3, "coupon_id": coupon_id})
    await hass.async_block_till_done()
    assert not delete_connection.errors
    assert len(store.coupons) == 0

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert mock_unload_panel.call_count == 1


async def test_config_flow_rejects_bad_api_key(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"

    with patch(
        "custom_components.lotto.lotto_api.LottoOpenApiClient.async_verify_connection",
        new=AsyncMock(side_effect=LottoApiAuthError("nope")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"api_key": "bad-key", "poll_interval_hours": 4}
        )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_config_flow_success_then_single_instance(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})

    with patch(
        "custom_components.lotto.lotto_api.LottoOpenApiClient.async_verify_connection",
        new=AsyncMock(return_value=None),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"api_key": "good-key", "poll_interval_hours": 6}
        )
    assert result["type"] == "create_entry"
    assert result["data"]["api_key"] == "good-key"

    # A second attempt should abort - this integration is single-instance.
    result2 = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result2["type"] == "abort"
    assert result2["reason"] == "already_configured"


@patch("custom_components.lotto.async_unload_panel")
@patch("custom_components.lotto.async_setup_panel", new_callable=AsyncMock)
async def test_add_coupon_rejects_invalid_numbers(mock_setup_panel, mock_unload_panel, hass, ws_connection):
    entry = MockConfigEntry(domain=DOMAIN, data={"api_key": "test-key", "poll_interval_hours": 4})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.lotto.lotto_api.LottoOpenApiClient.async_get_last_results",
        new=AsyncMock(return_value=[]),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    ws.websocket_add_coupon(
        hass,
        ws_connection,
        {
            "id": 1,
            "game_type": "Lotto",
            "numbers": [1, 2, 3],  # only 3 numbers - Lotto needs 6
            "euro_numbers": [],
            "draws_total": 1,
            "first_draw_date": "2026-01-01",
        },
    )
    await hass.async_block_till_done()

    assert ws_connection.errors and ws_connection.errors[0][0] == "invalid_coupon"
    store = hass.data[DOMAIN][entry.entry_id]["store"]
    assert len(store.coupons) == 0


@patch("custom_components.lotto.async_unload_panel")
@patch("custom_components.lotto.async_setup_panel", new_callable=AsyncMock)
async def test_no_api_key_uses_public_client_date_anchored_fetch(
    mock_setup_panel, mock_unload_panel, hass, ws_connection
):
    """No api_key configured -> LottoPublicApiClient, queried per-coupon by
    (first_draw_date, draws_total) via async_get_results_from rather than
    the Open API's batched "last N results" call."""
    entry = MockConfigEntry(domain=DOMAIN, data={"poll_interval_hours": 4})
    entry.add_to_hass(hass)

    with patch.object(
        LottoPublicApiClient, "async_get_results_from", new=AsyncMock(return_value=[])
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    data = hass.data[DOMAIN][entry.entry_id]
    assert isinstance(data["client"], LottoPublicApiClient)
    coordinator = data["coordinator"]
    assert hasattr(coordinator.api_client, "async_get_results_from")

    with patch.object(coordinator, "async_request_refresh", new=AsyncMock()):
        ws.websocket_add_coupon(
            hass,
            ws_connection,
            {
                "id": 1,
                "game_type": "Lotto",
                "numbers": [1, 2, 3, 4, 5, 6],
                "euro_numbers": [],
                "draws_total": 3,
                "first_draw_date": "2026-01-01",
            },
        )
        await hass.async_block_till_done()
    assert not ws_connection.errors, ws_connection.errors

    winning_result = DrawResult(
        game_type="Lotto", draw_date=date(2026, 1, 1), numbers=[1, 2, 3, 4, 5, 6], euro_numbers=[]
    )
    fetch_mock = AsyncMock(return_value=[winning_result])
    with patch.object(LottoPublicApiClient, "async_get_results_from", new=fetch_mock):
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Anchored exactly to the coupon's own (first_draw_date, draws_total) -
    # not a shared "last N results" batch call.
    fetch_mock.assert_awaited_once_with("Lotto", date(2026, 1, 1), 3)

    store = data["store"]
    coupon_id = store.coupons[0]["id"]
    assert store.get(coupon_id)["checked_draws"][0]["is_win"] is True
