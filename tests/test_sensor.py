"""Tests des capteurs et de la gestion des erreurs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.calendrier_tempo.const import (
    API_BASE_URL,
    DOMAIN,
    INDICATIVE_HORIZONS,
    NAME,
    SCAN_INTERVAL,
)

from .conftest import PREDICTIONS, REMAINING, TODAY, TOMORROW_UNAVAILABLE, prediction


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, title=NAME)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _register(aioclient_mock: Any, tomorrow: Any, predictions: Any) -> None:
    aioclient_mock.get(f"{API_BASE_URL}/today", json=TODAY)
    aioclient_mock.get(f"{API_BASE_URL}/tomorrow", json=tomorrow)
    aioclient_mock.get(f"{API_BASE_URL}/remaining", json=REMAINING)
    aioclient_mock.get(f"{API_BASE_URL}/predictions", json=predictions)


async def test_sensors_ok(hass: HomeAssistant, mock_api: Any) -> None:
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED

    assert hass.states.get("sensor.calendrier_tempo_couleur_aujourd_hui").state == "blanc"
    assert hass.states.get("sensor.calendrier_tempo_couleur_demain").state == "bleu"
    assert hass.states.get("sensor.calendrier_tempo_prevision_j2").state == "blanc"
    j3 = hass.states.get("sensor.calendrier_tempo_prevision_j3")
    assert j3.state == "rouge"
    assert j3.attributes["date"] == "2026-12-10"
    assert j3.attributes["probabilite_rouge"] == 0.5
    assert "horizon" not in j3.attributes
    assert j3.attributes["fiabilite"] == "fiable"
    assert j3.attributes["officielle"] is False
    assert hass.states.get("sensor.calendrier_tempo_couleur_aujourd_hui").attributes[
        "fiabilite"
    ] == "officielle"
    assert hass.states.get("sensor.calendrier_tempo_prevision_j4").state == "rouge"
    assert hass.states.get("sensor.calendrier_tempo_prevision_j5").state == "blanc"

    red = hass.states.get("sensor.calendrier_tempo_prochain_jour_rouge")
    assert red.state == "2026-12-10"
    assert red.attributes["jours_avant"] == 3
    assert red.attributes["rouge_prevu"] is True
    assert red.attributes["fiabilite"] == "fiable"

    white = hass.states.get("sensor.calendrier_tempo_prochain_jour_blanc")
    assert white.state == "2026-12-07"
    assert white.attributes["blanc_prevu"] is True
    assert white.attributes["officielle"] is True
    assert white.attributes["jours_avant"] == 0

    rouges = hass.states.get("sensor.calendrier_tempo_jours_rouges_restants")
    assert rouges.state == "18"
    assert rouges.attributes["total_saison"] == 22
    assert rouges.attributes["unit_of_measurement"] == "days"
    assert rouges.attributes["state_class"] == "measurement"
    assert rouges.attributes["source"] == "calcul"
    assert hass.states.get("sensor.calendrier_tempo_jours_blancs_restants").state == "35"

    # Journée Tempo en cours (9 h) et période tarifaire.
    current = hass.states.get("sensor.calendrier_tempo_couleur_actuelle")
    assert current.state == "blanc"
    assert current.attributes["date"] == "2026-12-07"
    assert hass.states.get("sensor.calendrier_tempo_periode").state == "hp"

    # Requêtes identifiées par le User-Agent de l'intégration.
    _method, _url, _data, headers = mock_api.mock_calls[0]
    assert headers["User-Agent"] == "ha-calendrier-tempo/0.3.0"


async def test_tomorrow_unavailable_and_no_red(hass: HomeAssistant, aioclient_mock: Any) -> None:
    _register(
        aioclient_mock,
        TOMORROW_UNAVAILABLE,
        {"predictions": [prediction("2026-12-09", "BLEU"), prediction("2026-12-10", "BLANC")]},
    )
    await _setup(hass)
    assert hass.states.get("sensor.calendrier_tempo_couleur_demain").state == STATE_UNKNOWN
    red = hass.states.get("sensor.calendrier_tempo_prochain_jour_rouge")
    assert red.state == STATE_UNKNOWN
    assert red.attributes["rouge_prevu"] is False
    assert hass.states.get("sensor.calendrier_tempo_prevision_j5").state == STATE_UNKNOWN


async def test_empty_predictions(hass: HomeAssistant, aioclient_mock: Any) -> None:
    _register(aioclient_mock, TOMORROW_UNAVAILABLE, {"status": "ok", "predictions": []})
    await _setup(hass)
    assert hass.states.get("sensor.calendrier_tempo_couleur_aujourd_hui").state == "blanc"
    for days in (2, 3, 4, 5):
        state = hass.states.get(f"sensor.calendrier_tempo_prevision_j{days}")
        assert state.state == STATE_UNKNOWN
    assert hass.states.get("sensor.calendrier_tempo_prochain_jour_rouge").state == STATE_UNKNOWN


async def test_network_error_at_startup_retries_later(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    aioclient_mock.get(f"{API_BASE_URL}/today", exc=TimeoutError())
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_network_error_after_startup_marks_unavailable(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    _register(aioclient_mock, TOMORROW_UNAVAILABLE, PREDICTIONS)
    await _setup(hass)
    assert hass.states.get("sensor.calendrier_tempo_couleur_aujourd_hui").state == "blanc"

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API_BASE_URL}/today", status=503)
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.calendrier_tempo_couleur_aujourd_hui").state == STATE_UNAVAILABLE
    # Une seule requête : pas de relance en rafale sur les autres endpoints.
    assert aioclient_mock.call_count == 1


async def test_unload(hass: HomeAssistant, mock_api: Any) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_horizon_sensor(hass: HomeAssistant, mock_api: Any) -> None:
    await _setup(hass)
    state = hass.states.get("sensor.calendrier_tempo_previsions_15_jours")
    # Rouges prévus sur l'horizon : 10, 11 et 15 décembre.
    assert state.state == "3"
    assert state.attributes["unit_of_measurement"] == "days"
    assert state.attributes["friendly_name"] == "Calendrier Tempo EDF Red days in the next 15 days"
    attrs = state.attributes
    assert attrs["horizon_jours"] == 15
    assert attrs["jours_blancs"] == 3
    assert attrs["jours_rouges_officiels"] == 0
    assert attrs["generee_le"] == "2026-12-07T07:30:00+01:00"
    previsions = attrs["previsions"]
    assert len(previsions) == 16
    assert previsions[0] == {
        "date": "2026-12-07",
        "jour": 0,
        "couleur": "blanc",
        "officielle": True,
        "fiabilite": "officielle",
        "probabilite_bleu": 0.0,
        "probabilite_blanc": 1.0,
        "probabilite_rouge": 0.0,
    }
    assert previsions[3]["fiabilite"] == "fiable"
    assert previsions[8]["couleur"] == "rouge"
    assert previsions[8]["fiabilite"] == "indicative"
    assert previsions[15]["date"] == "2026-12-22"


async def test_horizon_sensor_empty(hass: HomeAssistant, aioclient_mock: Any) -> None:
    _register(
        aioclient_mock,
        TOMORROW_UNAVAILABLE,
        {"status": "ok", "predictions": []},
    )
    await _setup(hass)
    state = hass.states.get("sensor.calendrier_tempo_previsions_15_jours")
    # Seul aujourd'hui (officiel, blanc) est connu : 0 rouge, pas « inconnu ».
    assert state.state == "0"
    assert state.attributes["horizon_jours"] == 0
    assert len(state.attributes["previsions"]) == 1


async def test_indicative_sensors_disabled_by_default(
    hass: HomeAssistant, mock_api: Any
) -> None:
    entry = await _setup(hass)
    registry = er.async_get(hass)
    for days in INDICATIVE_HORIZONS:
        entity_id = f"sensor.calendrier_tempo_prevision_j{days}"
        reg = registry.async_get(entity_id)
        assert reg is not None, entity_id
        assert reg.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(entity_id) is None
    for days in (2, 3, 4, 5):
        reg = registry.async_get(f"sensor.calendrier_tempo_prevision_j{days}")
        assert reg is not None and reg.disabled_by is None

    # Activé par l'utilisateur : la prévision J+8 est marquée indicative.
    registry.async_update_entity("sensor.calendrier_tempo_prevision_j8", disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    j8 = hass.states.get("sensor.calendrier_tempo_prevision_j8")
    assert j8.state == "rouge"
    assert j8.attributes["date"] == "2026-12-15"
    assert j8.attributes["fiabilite"] == "indicative"
    assert j8.attributes["probabilite_rouge"] == 0.41


async def test_refresh_after_edf_announcement(
    hass: HomeAssistant, mock_api: Any, freezer: FrozenDateTimeFactory
) -> None:
    await hass.config.async_set_time_zone("Europe/Paris")
    freezer.move_to(datetime(2026, 12, 7, 11, 20, tzinfo=ZoneInfo("Europe/Paris")))
    await _setup(hass)
    calls = mock_api.call_count

    # 11 h 36 : moins de 30 minutes après le dernier cycle, seule la mise à jour
    # de 11 h 35 (annonce EDF de la couleur du lendemain) peut se déclencher.
    freezer.move_to(datetime(2026, 12, 7, 11, 36, 1, tzinfo=ZoneInfo("Europe/Paris")))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_api.call_count == calls + 4
