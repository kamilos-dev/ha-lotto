"""Summary sensor for Lotto coupons."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, STATUS_ACTIVE
from .coordinator import LottoCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: LottoCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([LottoActiveCouponsSensor(coordinator, entry)])


class LottoActiveCouponsSensor(CoordinatorEntity[LottoCoordinator], SensorEntity):
    """Number of currently active coupons, with a summary in the attributes."""

    _attr_has_entity_name = True
    _attr_name = "Aktywne kupony"
    _attr_icon = "mdi:ticket-confirmation-outline"

    def __init__(self, coordinator: LottoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_active_coupons"

    @property
    def native_value(self) -> int:
        return sum(1 for c in self.coordinator.data or [] if c["status"] == STATUS_ACTIVE)

    @property
    def extra_state_attributes(self) -> dict:
        coupons = self.coordinator.data or []
        return {
            "total_coupons": len(coupons),
            "won_coupons": sum(
                1 for c in coupons if any(d["is_win"] for d in c["checked_draws"])
            ),
            "coupons": coupons,
        }
