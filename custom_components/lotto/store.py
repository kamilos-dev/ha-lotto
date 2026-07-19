"""Persistence for Lotto coupons."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


class LottoStore:
    """Loads/saves the list of coupons to `.storage/lotto.coupons`."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._coupons: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        data = await self._store.async_load()
        coupons = (data or {}).get("coupons", [])
        self._coupons = {c["id"]: c for c in coupons}

    @property
    def coupons(self) -> list[dict[str, Any]]:
        return list(self._coupons.values())

    def get(self, coupon_id: str) -> dict[str, Any] | None:
        return self._coupons.get(coupon_id)

    async def async_add(self, coupon: dict[str, Any]) -> None:
        self._coupons[coupon["id"]] = coupon
        await self._async_save()

    async def async_update(self, coupon: dict[str, Any]) -> None:
        if coupon["id"] not in self._coupons:
            _LOGGER.warning("Tried to update unknown coupon %s", coupon["id"])
            return
        self._coupons[coupon["id"]] = coupon
        await self._async_save()

    async def async_remove(self, coupon_id: str) -> bool:
        if coupon_id not in self._coupons:
            return False
        del self._coupons[coupon_id]
        await self._async_save()
        return True

    async def _async_save(self) -> None:
        await self._store.async_save({"coupons": list(self._coupons.values())})
