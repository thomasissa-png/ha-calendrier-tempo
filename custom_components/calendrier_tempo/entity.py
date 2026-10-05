"""Base commune des entités : appareil, attribution, identifiant unique."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, NAME, SITE_URL, VERSION
from .coordinator import TempoCoordinator


class TempoEntity(CoordinatorEntity[TempoCoordinator]):
    """Entité rattachée à l'appareil « Calendrier Tempo EDF »."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: TempoCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=NAME,
            manufacturer=NAME,
            model="API publique",
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=SITE_URL,
        )
