"""Tests des capteurs et de la gestion des erreurs."""

from __future__ import annotations

from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.calendrier_tempo.const import API_BASE_URL, DOMAIN, NAME, SCAN_INTERVAL

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
    assert hass.states.get("sensor.calendrier_tempo_prevision_j4").state == "rouge"
    assert hass.states.get("sensor.calendrier_tempo_prevision_j5").state == "blanc"

    red = hass.states.get("sensor.calendrier_tempo_prochain_jour_rouge")
    assert red.state == "2026-12-10"
    assert red.attributes["jours_avant"] == 3
    assert red.attributes["rouge_prevu"] is True

    rouges = hass.states.get("sensor.calendrier_tempo_jours_rouges_restants")
    assert rouges.state == "18"
    assert rouges.attributes["total_saison"] == 22
    assert hass.states.get("sensor.calendrier_tempo_jours_blancs_restants").state == "35"

    # Requêtes identifiées par le User-Agent de l'intégration.
    _method, _url, _data, headers = mock_api.mock_calls[0]
    assert headers["User-Agent"] == "ha-calendrier-tempo/0.1.0"


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
