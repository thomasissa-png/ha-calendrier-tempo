"""Intégration Calendrier Tempo EDF (API publique de calendrier-tempo.fr)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time, timedelta
import random

from homeassistant.const import Platform
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .const import (
    ANNOUNCEMENT_REFRESH_HOUR,
    ANNOUNCEMENT_REFRESH_MINUTE,
    DAY_REFRESH_HOUR,
    DAY_REFRESH_MINUTE,
    DOMAIN,
    PEAK_END_HOUR,
    TEMPO_DAY_START_HOUR,
)
from .coordinator import PARIS_TZ, TempoConfigEntry, TempoCoordinator

PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.SENSOR]


def next_paris_time(now: datetime, hour: int, minute: int, second: int = 0) -> datetime:
    """Prochain passage à hh:mm:ss heure de Paris (changements d'heure compris), en UTC."""
    local = now.astimezone(PARIS_TZ)
    day = local.date()
    while True:
        target = datetime.combine(day, time(hour, minute, second), tzinfo=PARIS_TZ)
        if target > local:
            return target.astimezone(dt_util.UTC)
        day += timedelta(days=1)


@callback
def _track_paris_time(
    hass: HomeAssistant,
    entry: TempoConfigEntry,
    action: Callable[[], None],
    hour: int,
    minute: int,
    second: int = 0,
) -> None:
    """Exécute `action` chaque jour à hh:mm:ss heure de Paris, quel que soit le
    fuseau configuré dans Home Assistant (souvent UTC sous Docker)."""
    unsub: CALLBACK_TYPE | None = None

    @callback
    def _schedule() -> None:
        nonlocal unsub
        point = next_paris_time(dt_util.utcnow(), hour, minute, second)
        unsub = async_track_point_in_utc_time(hass, _fire, point)

    @callback
    def _fire(_now: datetime) -> None:
        action()
        _schedule()

    @callback
    def _cancel() -> None:
        if unsub is not None:
            unsub()

    _schedule()
    entry.async_on_unload(_cancel)


async def async_setup_entry(hass: HomeAssistant, entry: TempoConfigEntry) -> bool:
    """Configure l'intégration à partir de l'entrée créée par l'assistant."""
    coordinator = TempoCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    @callback
    def _refresh() -> None:
        entry.async_create_background_task(
            hass, coordinator.async_request_refresh(), f"{DOMAIN}_scheduled_refresh"
        )

    # Changement de jour : « aujourd'hui », « demain » et tout l'horizon glissent.
    # Les secondes sont tirées au hasard pour ne pas faire arriver toutes les
    # installations ensemble.
    _track_paris_time(
        hass, entry, _refresh, DAY_REFRESH_HOUR, DAY_REFRESH_MINUTE, random.randint(0, 59)
    )
    # Juste après l'annonce par EDF de la couleur du lendemain.
    _track_paris_time(
        hass,
        entry,
        _refresh,
        ANNOUNCEMENT_REFRESH_HOUR,
        ANNOUNCEMENT_REFRESH_MINUTE,
        random.randint(0, 59),
    )
    # Début de la journée Tempo (6 h) et fin des heures pleines (22 h) : couleur
    # actuelle et période recalculées sans interroger l'API.
    for hour in (TEMPO_DAY_START_HOUR, PEAK_END_HOUR):
        _track_paris_time(hass, entry, coordinator.async_update_listeners, hour, 0)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TempoConfigEntry) -> bool:
    """Décharge l'intégration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
