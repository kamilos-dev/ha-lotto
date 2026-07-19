"""Periodically checks active coupons against fresh draw results."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import EVENT_UPDATED, EVENT_WIN, GAME_EUROJACKPOT, RESULTS_FETCH_SIZE, STATUS_ACTIVE, STATUS_EXPIRED
from .lotto_api import DrawResult, LottoApiClient, LottoApiError
from .rules import match_draw
from .store import LottoStore

_LOGGER = logging.getLogger(__name__)


class LottoCoordinator(DataUpdateCoordinator[list[dict]]):
    """Fetches results and updates coupon state on a fixed interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        store: LottoStore,
        api_client: LottoApiClient,
        update_interval_hours: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="lotto",
            update_interval=timedelta(hours=update_interval_hours),
        )
        self.store = store
        self.api_client = api_client

    async def _async_update_data(self) -> list[dict]:
        active_coupons = [c for c in self.store.coupons if c["status"] == STATUS_ACTIVE]
        if not active_coupons:
            return self.store.coupons

        results_by_game: dict[str, list[DrawResult]] = {}
        for game_type in {c["game_type"] for c in active_coupons}:
            try:
                results_by_game[game_type] = await self.api_client.async_get_last_results(
                    game_type, RESULTS_FETCH_SIZE
                )
            except LottoApiError as err:
                _LOGGER.warning("Nie udało się pobrać wyników dla %s: %s", game_type, err)
                results_by_game[game_type] = []

        any_changed = False
        for coupon in active_coupons:
            if self._async_check_coupon(coupon, results_by_game.get(coupon["game_type"], [])):
                any_changed = True
                await self.store.async_update(coupon)

        if any_changed:
            self.hass.bus.async_fire(EVENT_UPDATED, {})

        return self.store.coupons

    def _async_check_coupon(self, coupon: dict, results: list[DrawResult]) -> bool:
        """Check one coupon against newly fetched results, mutating it in place."""
        first_draw_date = date.fromisoformat(coupon["first_draw_date"])
        checked_dates = {c["draw_date"] for c in coupon["checked_draws"]}

        pending_draws = sorted(
            (r for r in results if r.draw_date >= first_draw_date and r.draw_date.isoformat() not in checked_dates),
            key=lambda r: r.draw_date,
        )

        changed = False
        for draw in pending_draws:
            if coupon["draws_remaining"] <= 0:
                break

            match = match_draw(
                coupon["game_type"],
                coupon["numbers"],
                coupon.get("euro_numbers", []),
                draw.numbers,
                draw.euro_numbers,
            )
            check_entry = {
                "draw_date": draw.draw_date.isoformat(),
                "matched_numbers": match["matched_numbers"],
                "matched_euro_numbers": match["matched_euro_numbers"],
                "is_win": match["is_win"],
                "prize_tier": match["prize_tier"],
                "checked_at": dt_util.utcnow().isoformat(),
            }
            coupon["checked_draws"].append(check_entry)
            coupon["draws_remaining"] -= 1
            changed = True

            if match["is_win"]:
                self._async_notify_win(coupon, check_entry)

        if coupon["draws_remaining"] <= 0 and coupon["status"] == STATUS_ACTIVE:
            coupon["status"] = STATUS_EXPIRED
            changed = True

        return changed

    def _async_notify_win(self, coupon: dict, check_entry: dict) -> None:
        numbers_text = ", ".join(str(n) for n in coupon["numbers"])
        if coupon["game_type"] == GAME_EUROJACKPOT:
            numbers_text += " + Euro: " + ", ".join(str(n) for n in coupon.get("euro_numbers", []))

        message = (
            f"Kupon {coupon['game_type']} ({numbers_text}) trafił w losowaniu "
            f"{check_entry['draw_date']}: {check_entry['matched_numbers']} trafień"
            + (
                f" + {check_entry['matched_euro_numbers']} Euro"
                if coupon["game_type"] == GAME_EUROJACKPOT
                else ""
            )
            + "!"
        )

        _LOGGER.info(message)
        persistent_notification.async_create(
            self.hass,
            message,
            title="Lotto: trafienie!",
            notification_id=f"lotto_win_{coupon['id']}_{check_entry['draw_date']}",
        )
        self.hass.bus.async_fire(
            EVENT_WIN,
            {
                "coupon_id": coupon["id"],
                "game_type": coupon["game_type"],
                "numbers": coupon["numbers"],
                "euro_numbers": coupon.get("euro_numbers", []),
                "draw_date": check_entry["draw_date"],
                "matched_numbers": check_entry["matched_numbers"],
                "matched_euro_numbers": check_entry["matched_euro_numbers"],
                "prize_tier": check_entry["prize_tier"],
            },
        )
