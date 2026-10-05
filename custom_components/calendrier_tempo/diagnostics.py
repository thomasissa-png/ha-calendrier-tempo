"""Diagnostics : état du coordinateur et dernières données lues (aucune donnée personnelle)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import VERSION
from .coordinator import TempoConfigEntry
from .parsing import DayColor


def _day(day: DayColor) -> dict[str, Any]:
    return {
        "date": day.date.isoformat() if day.date else None,
        "couleur": day.color,
        "code": day.code,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TempoConfigEntry
) -> dict[str, Any]:
    """Diagnostics téléchargeables depuis la page de l'intégration."""
    coordinator = entry.runtime_data
    data = coordinator.data
    remaining = data.remaining
    return {
        "version": VERSION,
        "derniere_mise_a_jour_reussie": coordinator.last_update_success,
        "derniere_erreur": str(coordinator.last_exception) if coordinator.last_exception else None,
        "intervalle": str(coordinator.update_interval),
        "date_reference": data.reference_date.isoformat(),
        "reponse_en_retard": data.stale,
        "hier": _day(data.yesterday),
        "aujourd_hui": _day(data.today),
        "demain": _day(data.tomorrow),
        "jours_restants": {
            "rouge": remaining.rouge,
            "blanc": remaining.blanc,
            "source": remaining.source,
        },
        "generee_le": data.generated_at,
        "previsions": [day.as_dict() for day in data.days],
    }
