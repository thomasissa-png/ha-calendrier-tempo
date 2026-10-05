"""Intégration Calendrier Tempo EDF (API publique de calendrier-tempo.fr)."""

from __future__ import annotations

from datetime import datetime

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change

from .const import DOMAIN
from .coordinator import TempoConfigEntry, TempoCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: TempoConfigEntry) -> bool:
    """Configure l'intégration à partir de l'entrée créée par l'assistant."""
    coordinator = TempoCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    @callback
    def _refresh_after_midnight(_now: datetime) -> None:
        # Changement de jour : « aujourd'hui », « demain » et J+2..J+5 glissent.
        entry.async_create_background_task(
            hass, coordinator.async_request_refresh(), f"{DOMAIN}_refresh_after_midnight"
        )

    entry.async_on_unload(
        async_track_time_change(hass, _refresh_after_midnight, hour=0, minute=1, second=0)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TempoConfigEntry) -> bool:
    """Décharge l'intégration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
