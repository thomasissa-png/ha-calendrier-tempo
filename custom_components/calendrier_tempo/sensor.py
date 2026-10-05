"""Capteurs Calendrier Tempo EDF."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, FORECAST_HORIZONS, NAME, SITE_URL, VERSION
from .coordinator import TempoConfigEntry, TempoCoordinator
from .parsing import COLORS, DayColor, Prediction, TempoData

# Une seule source de données : pas de parallélisme à limiter côté plateforme.
PARALLEL_UPDATES = 0

StateValue = str | int | date | None


@dataclass(frozen=True, kw_only=True)
class TempoSensorDescription(SensorEntityDescription):
    """Description d'un capteur : valeur et attributs calculés depuis TempoData."""

    value_fn: Callable[[TempoData], StateValue]
    attrs_fn: Callable[[TempoData], dict[str, Any]] = lambda _data: {}


def _day_attrs(day: DayColor) -> dict[str, Any]:
    return {
        "date": day.date.isoformat() if day.date else None,
        "code": day.code,
        "officielle": day.color is not None,
    }


def _prediction_attrs(prediction: Prediction | None, data: TempoData, days: int) -> dict[str, Any]:
    target = data.reference_date.toordinal() + days
    attrs: dict[str, Any] = {"date": date.fromordinal(target).isoformat()}
    if prediction is not None:
        attrs.update(prediction.attributes)
    return attrs


def _next_red_attrs(data: TempoData) -> dict[str, Any]:
    red = data.next_red()
    if red is None:
        return {"rouge_prevu": False}
    attrs: dict[str, Any] = {
        "rouge_prevu": True,
        "jours_avant": (red.date - data.reference_date).days,
    }
    attrs.update(red.attributes)
    return attrs


def _forecast_description(days: int) -> TempoSensorDescription:
    return TempoSensorDescription(
        key=f"prevision_j{days}",
        translation_key=f"prevision_j{days}",
        device_class=SensorDeviceClass.ENUM,
        options=list(COLORS),
        icon="mdi:calendar-question",
        value_fn=lambda data: (p.color if (p := data.prediction_for_offset(days)) else None),
        attrs_fn=lambda data: _prediction_attrs(data.prediction_for_offset(days), data, days),
    )


SENSORS: tuple[TempoSensorDescription, ...] = (
    TempoSensorDescription(
        key="couleur_aujourd_hui",
        translation_key="couleur_aujourd_hui",
        device_class=SensorDeviceClass.ENUM,
        options=list(COLORS),
        icon="mdi:calendar-today",
        value_fn=lambda data: data.today.color,
        attrs_fn=lambda data: _day_attrs(data.today),
    ),
    TempoSensorDescription(
        key="couleur_demain",
        translation_key="couleur_demain",
        device_class=SensorDeviceClass.ENUM,
        options=list(COLORS),
        icon="mdi:calendar-arrow-right",
        value_fn=lambda data: data.tomorrow.color,
        attrs_fn=lambda data: _day_attrs(data.tomorrow),
    ),
    *(_forecast_description(days) for days in FORECAST_HORIZONS),
    TempoSensorDescription(
        key="prochain_jour_rouge",
        translation_key="prochain_jour_rouge",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar-alert",
        value_fn=lambda data: (red.date if (red := data.next_red()) else None),
        attrs_fn=_next_red_attrs,
    ),
    TempoSensorDescription(
        key="jours_rouges_restants",
        translation_key="jours_rouges_restants",
        icon="mdi:calendar-remove",
        value_fn=lambda data: data.remaining.rouge,
        attrs_fn=lambda data: {
            "total_saison": data.remaining.total_rouge,
            "debut_saison": _iso(data.remaining.season_start),
            "fin_saison": _iso(data.remaining.season_end),
        },
    ),
    TempoSensorDescription(
        key="jours_blancs_restants",
        translation_key="jours_blancs_restants",
        icon="mdi:calendar-blank",
        value_fn=lambda data: data.remaining.blanc,
        attrs_fn=lambda data: {
            "total_saison": data.remaining.total_blanc,
            "debut_saison": _iso(data.remaining.season_start),
            "fin_saison": _iso(data.remaining.season_end),
        },
    ),
)


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TempoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crée les capteurs."""
    coordinator = entry.runtime_data
    async_add_entities(TempoSensor(coordinator, description) for description in SENSORS)


class TempoSensor(CoordinatorEntity[TempoCoordinator], SensorEntity):
    """Capteur alimenté par le coordinateur."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    entity_description: TempoSensorDescription

    def __init__(self, coordinator: TempoCoordinator, description: TempoSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{description.key}"
        # entity_id stable et identique quelle que soit la langue de Home Assistant.
        self.entity_id = f"sensor.{DOMAIN}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=NAME,
            manufacturer=NAME,
            model="API publique",
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=SITE_URL,
        )

    @property
    def native_value(self) -> StateValue:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.entity_description.attrs_fn(self.coordinator.data)
