"""Capteurs Calendrier Tempo EDF."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    FORECAST_HORIZONS,
    INDICATIVE_HORIZONS,
    PERIOD_OFF_PEAK,
    PERIOD_PEAK,
)
from .coordinator import PARIS_TZ, TempoConfigEntry, TempoCoordinator
from .entity import TempoEntity
from .parsing import (
    COLOR_BLANC,
    COLOR_ROUGE,
    COLORS,
    FIABILITE_OFFICIELLE,
    DayColor,
    ForecastDay,
    TempoData,
    fiabilite_for,
    period_for,
)

# Une seule source de données : pas de parallélisme à limiter côté plateforme.
PARALLEL_UPDATES = 0

StateValue = str | int | float | date | None

# Unité acceptée par le tableau de bord Énergie (« entité avec le prix actuel ») :
# elle doit se terminer par « /kWh ». Pas de device_class MONETARY, qui exige une
# devise seule comme unité.
PRICE_UNIT = f"EUR/{UnitOfEnergy.KILO_WATT_HOUR}"


@dataclass(frozen=True, kw_only=True)
class TempoSensorDescription(SensorEntityDescription):
    """Description d'un capteur : valeur et attributs calculés depuis TempoData."""

    value_fn: Callable[[TempoData], StateValue]
    attrs_fn: Callable[[TempoData], dict[str, Any]] = lambda _data: {}
    # Valeur calculée sur l'heure seule : disponible même si l'API ne répond pas.
    always_available: bool = False


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _day_attrs(data: TempoData, day: DayColor) -> dict[str, Any]:
    tariff = data.day_tariff(day)
    return {
        "date": _iso(day.date),
        "code": day.code,
        "officielle": day.color is not None,
        "fiabilite": FIABILITE_OFFICIELLE if day.color is not None else None,
        "prix_hp": tariff.hp if tariff else None,
        "prix_hc": tariff.hc if tariff else None,
    }


def _now_paris() -> datetime:
    return dt_util.now(PARIS_TZ)


def _current_attrs(data: TempoData) -> dict[str, Any]:
    attrs = _day_attrs(data, data.current_day(_now_paris()))
    attrs.pop("code", None)
    return attrs


def _price_attrs(data: TempoData) -> dict[str, Any]:
    now = _now_paris()
    day = data.current_day(now)
    grid = data.tarifs
    return {
        "periode": period_for(now),
        "couleur": day.color,
        "date": _iso(day.date),
        "grille": grid.as_dict() if grid else None,
        "date_effet": _iso(grid.date_effet) if grid else None,
    }


def _forecast_attrs(data: TempoData, days: int) -> dict[str, Any]:
    day = data.day_for_offset(days)
    attrs: dict[str, Any] = {
        "date": (data.reference_date + timedelta(days=days)).isoformat(),
        "officielle": day.official if day else False,
        "fiabilite": day.fiabilite if day else fiabilite_for(days, official=False),
    }
    if day is not None:
        attrs.update(day.attributes)
        # Ajouts 0.3.1, comme sur le site : l'état (la couleur prévue) ne change pas.
        second = day.second_color()
        attrs["hesitation"] = second is not None
        attrs["seconde_couleur"] = second
        attrs["libelle"] = day.libelle
    return attrs


def _next_attrs(day: ForecastDay | None, flag: str) -> dict[str, Any]:
    if day is None:
        return {flag: False}
    attrs: dict[str, Any] = {
        flag: True,
        "jours_avant": day.offset,
        "officielle": day.official,
        "fiabilite": day.fiabilite,
    }
    attrs.update(day.attributes)
    return attrs


def _count(data: TempoData, color: str) -> int | None:
    if not data.days:
        return None
    return sum(1 for d in data.days if d.color == color)


def _horizon_attrs(data: TempoData) -> dict[str, Any]:
    return {
        "horizon_jours": data.horizon_jours,
        "jours_blancs": _count(data, COLOR_BLANC),
        "jours_rouges_officiels": sum(
            1 for d in data.days if d.color == COLOR_ROUGE and d.official
        ),
        "generee_le": data.generated_at,
        "previsions": [d.as_dict() for d in data.days],
    }


def _forecast_description(days: int, enabled: bool) -> TempoSensorDescription:
    return TempoSensorDescription(
        key=f"prevision_j{days}",
        translation_key=f"prevision_j{days}",
        device_class=SensorDeviceClass.ENUM,
        options=list(COLORS),
        entity_registry_enabled_default=enabled,
        value_fn=lambda data: (d.color if (d := data.day_for_offset(days)) else None),
        attrs_fn=lambda data: _forecast_attrs(data, days),
    )


def _remaining_attrs(total: Callable[[TempoData], int | None]) -> Callable[[TempoData], dict[str, Any]]:
    return lambda data: {
        "total_saison": total(data),
        "debut_saison": _iso(data.remaining.season_start),
        "fin_saison": _iso(data.remaining.season_end),
        "source": data.remaining.source,
    }


SENSORS: tuple[TempoSensorDescription, ...] = (
    TempoSensorDescription(
        key="couleur_aujourd_hui",
        translation_key="couleur_aujourd_hui",
        device_class=SensorDeviceClass.ENUM,
        options=list(COLORS),
        value_fn=lambda data: data.today.color,
        attrs_fn=lambda data: _day_attrs(data, data.today),
    ),
    TempoSensorDescription(
        key="couleur_actuelle",
        translation_key="couleur_actuelle",
        device_class=SensorDeviceClass.ENUM,
        options=list(COLORS),
        value_fn=lambda data: data.current_day(_now_paris()).color,
        attrs_fn=_current_attrs,
    ),
    TempoSensorDescription(
        key="periode",
        translation_key="periode",
        device_class=SensorDeviceClass.ENUM,
        options=[PERIOD_PEAK, PERIOD_OFF_PEAK],
        value_fn=lambda _data: period_for(_now_paris()),
        always_available=True,
    ),
    TempoSensorDescription(
        key="prix_kwh_actuel",
        translation_key="prix_kwh_actuel",
        native_unit_of_measurement=PRICE_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        value_fn=lambda data: data.current_price(_now_paris()),
        attrs_fn=_price_attrs,
        # Calcul local (heure + couleurs et grille déjà reçues) : le prix reste
        # disponible pendant une panne de l'API, pour le tableau de bord Énergie.
        # Il devient inconnu dès que la couleur de la journée Tempo n'est pas connue.
        always_available=True,
    ),
    TempoSensorDescription(
        key="couleur_demain",
        translation_key="couleur_demain",
        device_class=SensorDeviceClass.ENUM,
        options=list(COLORS),
        value_fn=lambda data: data.tomorrow.color,
        attrs_fn=lambda data: _day_attrs(data, data.tomorrow),
    ),
    *(_forecast_description(days, enabled=True) for days in FORECAST_HORIZONS),
    *(_forecast_description(days, enabled=False) for days in INDICATIVE_HORIZONS),
    TempoSensorDescription(
        key="previsions_15_jours",
        translation_key="previsions_15_jours",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _count(data, COLOR_ROUGE),
        attrs_fn=_horizon_attrs,
    ),
    TempoSensorDescription(
        key="prochain_jour_rouge",
        translation_key="prochain_jour_rouge",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda data: (d.date if (d := data.next_red()) else None),
        attrs_fn=lambda data: _next_attrs(data.next_red(), "rouge_prevu"),
    ),
    TempoSensorDescription(
        key="prochain_jour_blanc",
        translation_key="prochain_jour_blanc",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda data: (d.date if (d := data.next_white()) else None),
        attrs_fn=lambda data: _next_attrs(data.next_white(), "blanc_prevu"),
    ),
    TempoSensorDescription(
        key="jours_rouges_restants",
        translation_key="jours_rouges_restants",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.remaining.rouge,
        attrs_fn=_remaining_attrs(lambda data: data.remaining.total_rouge),
    ),
    TempoSensorDescription(
        key="jours_blancs_restants",
        translation_key="jours_blancs_restants",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.remaining.blanc,
        attrs_fn=_remaining_attrs(lambda data: data.remaining.total_blanc),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TempoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crée les capteurs."""
    coordinator = entry.runtime_data
    async_add_entities(TempoSensor(coordinator, description) for description in SENSORS)


class TempoSensor(TempoEntity, SensorEntity):
    """Capteur alimenté par le coordinateur."""

    entity_description: TempoSensorDescription
    # La liste complète de l'horizon change à chaque cycle : inutile de la
    # stocker dans l'historique (base de données allégée).
    _unrecorded_attributes = frozenset({"previsions"})

    def __init__(self, coordinator: TempoCoordinator, description: TempoSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        # entity_id stable et identique quelle que soit la langue de Home Assistant.
        self.entity_id = f"sensor.{DOMAIN}_{description.key}"

    @property
    def available(self) -> bool:
        return self.entity_description.always_available or super().available

    @property
    def native_value(self) -> StateValue:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.entity_description.attrs_fn(self.coordinator.data)
