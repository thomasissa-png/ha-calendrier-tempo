"""Robustesse : pannes partielles, relance unique, réponses en retard, heure de Paris."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.calendrier_tempo import next_paris_time
from custom_components.calendrier_tempo.const import (
    API_BASE_URL,
    DOMAIN,
    NAME,
    RETRY_INTERVAL,
    SCAN_INTERVAL,
    STALE_PAYLOAD_MAX_AGE,
)

from .conftest import PARIS, PREDICTIONS, REMAINING, TODAY, TOMORROW

SENSOR = "sensor.calendrier_tempo_"


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, title=NAME)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _register(aioclient_mock: Any, **overrides: Any) -> None:
    """Les 4 endpoints ; `name=None` pour un 503, sinon la réponse à servir."""
    payloads = {
        "today": TODAY,
        "tomorrow": TOMORROW,
        "remaining": REMAINING,
        "predictions": PREDICTIONS,
    }
    payloads.update(overrides)
    for name, payload in payloads.items():
        if payload is None:
            aioclient_mock.get(f"{API_BASE_URL}/{name}", status=503)
        else:
            aioclient_mock.get(f"{API_BASE_URL}/{name}", json=payload)


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta) -> None:
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _state(hass: HomeAssistant, key: str) -> str:
    return hass.states.get(f"{SENSOR}{key}").state


async def test_predictions_down_keeps_official_colors(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    _register(aioclient_mock)
    await _setup(hass)
    assert _state(hass, "prevision_j3") == "rouge"

    aioclient_mock.clear_requests()
    _register(aioclient_mock, predictions=None, remaining=None)
    await _tick(hass, freezer, SCAN_INTERVAL)
    # Couleurs officielles à jour, prévisions et jours restants du cycle précédent.
    assert _state(hass, "couleur_aujourd_hui") == "blanc"
    assert _state(hass, "prevision_j3") == "rouge"
    assert _state(hass, "jours_rouges_restants") == "18"


async def test_kept_predictions_expire_after_24_hours(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    """/api/predictions en panne pendant 25 h : les anciennes prévisions disparaissent."""
    _register(aioclient_mock)
    await _setup(hass)
    assert _state(hass, "prevision_j2") == "blanc"

    aioclient_mock.clear_requests()
    _register(aioclient_mock, predictions=None)
    await _tick(hass, freezer, SCAN_INTERVAL)
    assert _state(hass, "prevision_j2") == "blanc"
    await _tick(hass, freezer, STALE_PAYLOAD_MAX_AGE + timedelta(hours=1))
    assert _state(hass, "prevision_j2") == STATE_UNKNOWN
    # Couleur officielle toujours lue (journée suivante : réponse du 7 en retard,
    # sa réponse « demain » du 8 sert de couleur du jour).
    assert _state(hass, "couleur_aujourd_hui") == "bleu"


async def test_partial_outage_logged_once(
    hass: HomeAssistant,
    aioclient_mock: Any,
    freezer: FrozenDateTimeFactory,
    caplog: Any,
) -> None:
    _register(aioclient_mock)
    await _setup(hass)
    aioclient_mock.clear_requests()
    _register(aioclient_mock, predictions=None)
    caplog.set_level(logging.INFO, logger="custom_components.calendrier_tempo")
    await _tick(hass, freezer, SCAN_INTERVAL)
    await _tick(hass, freezer, SCAN_INTERVAL)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "/api/predictions" in r.getMessage()]
    assert len(warnings) == 1

    aioclient_mock.clear_requests()
    _register(aioclient_mock)
    await _tick(hass, freezer, SCAN_INTERVAL)
    infos = [r for r in caplog.records if r.getMessage() == "/api/predictions de nouveau disponible"]
    assert len(infos) == 1


async def test_predictions_down_at_startup(hass: HomeAssistant, aioclient_mock: Any) -> None:
    _register(aioclient_mock, predictions=None)
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert _state(hass, "couleur_aujourd_hui") == "blanc"
    assert _state(hass, "prevision_j3") == STATE_UNKNOWN


async def test_single_short_retry_after_failure(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    _register(aioclient_mock)
    await _setup(hass)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API_BASE_URL}/today", status=503)

    await _tick(hass, freezer, SCAN_INTERVAL)
    assert aioclient_mock.call_count == 1
    assert _state(hass, "couleur_aujourd_hui") == STATE_UNAVAILABLE
    # Une seule relance rapide, 5 minutes plus tard.
    await _tick(hass, freezer, RETRY_INTERVAL)
    assert aioclient_mock.call_count == 2
    # Puis retour au cycle de 30 minutes, sans rafale.
    await _tick(hass, freezer, RETRY_INTERVAL)
    assert aioclient_mock.call_count == 2
    await _tick(hass, freezer, SCAN_INTERVAL)
    assert aioclient_mock.call_count == 3


async def test_stale_today_just_after_midnight(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    """0 h 06 : /api/today renvoie encore la veille, /api/tomorrow le jour même."""
    freezer.move_to(datetime(2026, 12, 8, 0, 6, tzinfo=PARIS))
    _register(aioclient_mock)
    await _setup(hass)
    # Le 8 décembre est bleu (réponse « demain » d'hier) ; demain inconnu.
    assert _state(hass, "couleur_aujourd_hui") == "bleu"
    assert hass.states.get(f"{SENSOR}couleur_aujourd_hui").attributes["date"] == "2026-12-08"
    assert _state(hass, "couleur_demain") == STATE_UNKNOWN
    # Avant 6 h, la journée Tempo du 7 (blanc) s'applique encore.
    assert _state(hass, "couleur_actuelle") == "blanc"
    assert _state(hass, "periode") == "hc"
    # J+2 compté depuis le 8 : 10 décembre.
    assert hass.states.get(f"{SENSOR}prevision_j2").attributes["date"] == "2026-12-10"

    calls = aioclient_mock.call_count
    await _tick(hass, freezer, RETRY_INTERVAL)
    assert aioclient_mock.call_count == calls + 4


async def test_backup_copy_several_days_old(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    """Copie de secours vieille de 7 jours : aucune couleur périmée n'est affichée."""
    freezer.move_to(datetime(2026, 12, 14, 9, 0, tzinfo=PARIS))
    _register(aioclient_mock)
    await _setup(hass)
    assert _state(hass, "couleur_aujourd_hui") == STATE_UNKNOWN
    assert _state(hass, "couleur_demain") == STATE_UNKNOWN
    assert hass.states.get(f"{SENSOR}prevision_j2").attributes["date"] == "2026-12-16"
    assert _state(hass, "prevision_j2") == "bleu"


async def test_tempo_day_and_period(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    """Entre 0 h et 6 h, couleur de la veille (lue une fois dans /api/history)."""
    freezer.move_to(datetime(2026, 12, 7, 5, 45, tzinfo=PARIS))
    _register(aioclient_mock)
    aioclient_mock.get(
        f"{API_BASE_URL}/history?days=2",
        json={"status": "ok", "history": [{"date": "2026-12-06", "couleur_reelle": "ROUGE"}]},
    )
    await _setup(hass)
    current = hass.states.get(f"{SENSOR}couleur_actuelle")
    assert current.state == "rouge"
    assert current.attributes["date"] == "2026-12-06"
    assert _state(hass, "periode") == "hc"

    calls = aioclient_mock.call_count
    freezer.move_to(datetime(2026, 12, 7, 6, 0, 1, tzinfo=PARIS))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _state(hass, "couleur_actuelle") == "blanc"
    assert _state(hass, "periode") == "hp"
    # Changement de journée Tempo sans nouvelle requête.
    assert aioclient_mock.call_count == calls

    freezer.move_to(datetime(2026, 12, 7, 22, 0, 1, tzinfo=PARIS))
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API_BASE_URL}/today", status=503)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    # Période calculée sur l'heure seule : disponible même si l'API ne répond pas.
    assert _state(hass, "periode") == "hc"
    assert _state(hass, "couleur_actuelle") == STATE_UNAVAILABLE


async def test_refresh_in_paris_time_when_home_assistant_is_utc(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to(datetime(2026, 12, 7, 11, 20, tzinfo=PARIS))
    _register(aioclient_mock)
    await _setup(hass)
    calls = aioclient_mock.call_count
    # 11 h 36 à Paris = 10 h 36 UTC : la mise à jour d'après annonce EDF a lieu.
    freezer.move_to(datetime(2026, 12, 7, 11, 36, 1, tzinfo=PARIS))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == calls + 4


def test_next_paris_time_across_daylight_saving() -> None:
    # Samedi 28 mars 2026, 12 h UTC : passage à l'heure d'été dans la nuit.
    now = datetime(2026, 3, 28, 12, 0, tzinfo=dt_util.UTC)
    assert next_paris_time(now, 0, 5) == datetime(2026, 3, 28, 23, 5, tzinfo=dt_util.UTC)
    after = datetime(2026, 3, 29, 0, 0, tzinfo=dt_util.UTC)
    assert next_paris_time(after, 11, 35) == datetime(2026, 3, 29, 9, 35, tzinfo=dt_util.UTC)
    assert next_paris_time(after, 6, 0) == datetime(2026, 3, 29, 4, 0, tzinfo=dt_util.UTC)
