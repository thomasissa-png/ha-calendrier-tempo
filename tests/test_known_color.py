"""Couleur officielle déjà lue : jamais effacée par une réponse « unavailable ».

Recette du 2026-10-17, point 3.12 : /api/today « unavailable » + `source_indisponible`
(`code: 0`, sans date) faisait passer la couleur du jour, la couleur actuelle et le
prix à « inconnu » alors que la couleur de ce même jour avait déjà été lue.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.calendrier_tempo.const import API_BASE_URL, DOMAIN, NAME
from custom_components.calendrier_tempo.parsing import Tariff, build_tempo_data, parse_day

from .conftest import PARIS, PREDICTIONS, REMAINING, TODAY, TOMORROW

SENSOR = "sensor.calendrier_tempo_"
PRICE = f"{SENSOR}prix_kwh_actuel"
TODAY_DATE = datetime(2026, 12, 7, tzinfo=PARIS).date()

# Prix du jour distinct de la grille : prouve que c'est le `tarif` du jour qui est repris.
DAY_TARIF = {"hp": 0.2500, "hc": 0.2100}
GRID = {
    "BLEU": {"hp": 0.1111, "hc": 0.1011},
    "BLANC": {"hp": 0.2222, "hc": 0.2022},
    "ROUGE": {"hp": 0.3333, "hc": 0.3033},
}
TODAY_OK: dict[str, Any] = {
    **TODAY,
    "tarif": DAY_TARIF,
    "tarifs": {"date_effet": "2026-08-01", "couleurs": GRID},
}
TOMORROW_OK: dict[str, Any] = {**TOMORROW, "tarif": GRID["BLEU"]}
# Format servi depuis 6444892 : `code: 0`, pas de date, pas de couleur.
SOURCE_DOWN: dict[str, Any] = {
    "status": "unavailable",
    "code": 0,
    "source_indisponible": True,
    "message": "Source officielle EDF momentanément indisponible",
}


def _register(aioclient_mock: Any, today: Any, tomorrow: Any) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API_BASE_URL}/today", json=today)
    aioclient_mock.get(f"{API_BASE_URL}/tomorrow", json=tomorrow)
    aioclient_mock.get(f"{API_BASE_URL}/remaining", json=REMAINING)
    aioclient_mock.get(f"{API_BASE_URL}/predictions", json=PREDICTIONS)


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, title=NAME)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _refresh_at(
    hass: HomeAssistant, entry: MockConfigEntry, freezer: FrozenDateTimeFactory, when: datetime
) -> None:
    freezer.move_to(when)
    async_fire_time_changed(hass, dt_util.utcnow())
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


def _state(hass: HomeAssistant, key: str) -> str:
    return hass.states.get(f"{SENSOR}{key}").state


async def test_unavailable_after_ok_keeps_known_color_and_price(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    _register(aioclient_mock, TODAY_OK, TOMORROW_OK)
    entry = await _setup(hass)
    assert _state(hass, "couleur_aujourd_hui") == "blanc"
    assert float(hass.states.get(PRICE).state) == 0.25

    _register(aioclient_mock, SOURCE_DOWN, SOURCE_DOWN)
    await _refresh_at(hass, entry, freezer, datetime(2026, 12, 7, 9, 30, tzinfo=PARIS))

    data = entry.runtime_data.data
    assert (data.today.color, data.today.code) == ("blanc", 2)
    assert data.today.tarif == Tariff(hp=0.25, hc=0.21)
    assert (data.tomorrow.color, data.tomorrow.code) == ("bleu", 1)
    assert _state(hass, "couleur_aujourd_hui") == "blanc"
    assert _state(hass, "couleur_actuelle") == "blanc"
    assert _state(hass, "couleur_demain") == "bleu"
    assert float(hass.states.get(PRICE).state) == 0.25
    today_attrs = hass.states.get(f"{SENSOR}couleur_aujourd_hui").attributes
    assert (today_attrs["prix_hp"], today_attrs["prix_hc"]) == (0.25, 0.21)
    # Horizon : le jour reste officiel (pas de retour à la prévision).
    assert data.day_for_offset(0).official and data.day_for_offset(0).color == "blanc"


async def test_day_change_carries_no_wrong_color(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    """Le 8 : « aujourd'hui » reprend la couleur lue pour le 8 (bleu), jamais celle du 7."""
    _register(aioclient_mock, TODAY_OK, TOMORROW_OK)
    entry = await _setup(hass)

    _register(aioclient_mock, SOURCE_DOWN, SOURCE_DOWN)
    # 8 décembre, 3 h : journée Tempo du 7 encore en cours.
    await _refresh_at(hass, entry, freezer, datetime(2026, 12, 8, 3, 0, tzinfo=PARIS))
    data = entry.runtime_data.data
    assert (data.yesterday.date.isoformat(), data.yesterday.color) == ("2026-12-07", "blanc")
    assert (data.today.date.isoformat(), data.today.color) == ("2026-12-08", "bleu")
    assert (data.tomorrow.date.isoformat(), data.tomorrow.color) == ("2026-12-09", None)
    assert _state(hass, "couleur_actuelle") == "blanc"
    assert _state(hass, "couleur_aujourd_hui") == "bleu"
    assert _state(hass, "couleur_demain") == STATE_UNKNOWN

    # 9 décembre, 9 h : rien de connu pour le 9 ni le 10, aucune couleur reportée.
    await _refresh_at(hass, entry, freezer, datetime(2026, 12, 9, 9, 0, tzinfo=PARIS))
    data = entry.runtime_data.data
    assert (data.today.date.isoformat(), data.today.color) == ("2026-12-09", None)
    assert data.tomorrow.color is None
    assert _state(hass, "couleur_aujourd_hui") == STATE_UNKNOWN
    assert _state(hass, "couleur_actuelle") == STATE_UNKNOWN
    assert _state(hass, "couleur_demain") == STATE_UNKNOWN


async def test_code_zero_never_a_color(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """Démarrage pendant la panne : `code: 0` ne devient ni une couleur ni un code."""
    _register(aioclient_mock, SOURCE_DOWN, SOURCE_DOWN)
    entry = await _setup(hass)
    data = entry.runtime_data.data
    assert (data.today.color, data.today.code) == (None, None)
    assert (data.tomorrow.color, data.tomorrow.code) == (None, None)
    assert _state(hass, "couleur_aujourd_hui") == STATE_UNKNOWN
    assert _state(hass, "couleur_demain") == STATE_UNKNOWN
    assert hass.states.get(f"{SENSOR}couleur_aujourd_hui").attributes["code"] is None


def test_parse_day_code_zero() -> None:
    assert parse_day(SOURCE_DOWN) == parse_day({"status": "unavailable"})
    day = parse_day({"status": "ok", "date": "2026-12-07", "couleur": None, "code": 0})
    assert (day.color, day.code) == (None, None)
    data = build_tempo_data(SOURCE_DOWN, SOURCE_DOWN, REMAINING, PREDICTIONS, TODAY_DATE)
    # Date attendue = calcul local, la réponse n'en donne pas : pas de « stale ».
    assert data.today.date == TODAY_DATE and not data.stale

