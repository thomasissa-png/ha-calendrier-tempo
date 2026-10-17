"""Prix du kWh : capteur « Prix du kWh actuel » et prix HP/HC des couleurs."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.calendrier_tempo.const import (
    API_BASE_URL,
    DOMAIN,
    NAME,
    SCAN_INTERVAL,
    STALE_PAYLOAD_MAX_AGE,
)
from custom_components.calendrier_tempo.parsing import (
    Tariff,
    parse_day,
    parse_tariff,
    parse_tariff_grid,
)

from .conftest import PARIS, PREDICTIONS, REMAINING, TODAY, TOMORROW, TOMORROW_UNAVAILABLE

PRICE = "sensor.calendrier_tempo_prix_kwh_actuel"

# Valeurs de test (fictives, distinctes par couleur et par période) : le composant
# ne contient aucun prix, il recopie ceux de l'API.
GRID: dict[str, dict[str, float]] = {
    "BLEU": {"hp": 0.1111, "hc": 0.1011},
    "BLANC": {"hp": 0.2222, "hc": 0.2022},
    "ROUGE": {"hp": 0.3333, "hc": 0.3033},
}
TARIFS: dict[str, Any] = {
    "date_effet": "2026-08-01",
    "unite": "EUR/kWh TTC",
    "heures_pleines": "06:00-22:00",
    "heures_creuses": "22:00-06:00",
    "couleurs": GRID,
}


def today_with_prices(day: str = "2026-12-07", color: str = "BLANC") -> dict[str, Any]:
    """Réponse /api/today au contrat 0.3.0 (tarif du jour + grille)."""
    code = {"BLEU": 1, "BLANC": 2, "ROUGE": 3}[color]
    return {
        "status": "ok",
        "date": day,
        "couleur": color,
        "code": code,
        "tarif": GRID[color],
        "tarifs": TARIFS,
    }


TOMORROW_WITH_PRICE: dict[str, Any] = {**TOMORROW, "tarif": GRID["BLEU"]}


def _register(aioclient_mock: Any, today: Any, tomorrow: Any = TOMORROW_WITH_PRICE) -> None:
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


async def _move(hass: HomeAssistant, freezer: FrozenDateTimeFactory, when: datetime) -> None:
    freezer.move_to(when)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _price(hass: HomeAssistant) -> str:
    return hass.states.get(PRICE).state


async def test_price_peak_hours(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """9 h un jour blanc : prix HP blanc, unité et classe attendues par le tableau Énergie."""
    _register(aioclient_mock, today_with_prices())
    await _setup(hass)
    state = hass.states.get(PRICE)
    assert float(state.state) == 0.2222
    attrs = state.attributes
    assert attrs["unit_of_measurement"] == "EUR/kWh"
    assert attrs["unit_of_measurement"].endswith("/kWh")
    assert attrs["state_class"] == "measurement"
    assert "device_class" not in attrs
    assert attrs["periode"] == "hp"
    assert attrs["couleur"] == "blanc"
    assert attrs["date"] == "2026-12-07"
    assert attrs["date_effet"] == "2026-08-01"
    assert attrs["grille"] == {
        "bleu": {"hp": 0.1111, "hc": 0.1011},
        "blanc": {"hp": 0.2222, "hc": 0.2022},
        "rouge": {"hp": 0.3333, "hc": 0.3033},
    }
    assert attrs["friendly_name"] == "Calendrier Tempo EDF Current kWh price"

    today = hass.states.get("sensor.calendrier_tempo_couleur_aujourd_hui").attributes
    assert (today["prix_hp"], today["prix_hc"]) == (0.2222, 0.2022)
    tomorrow = hass.states.get("sensor.calendrier_tempo_couleur_demain").attributes
    assert (tomorrow["prix_hp"], tomorrow["prix_hc"]) == (0.1111, 0.1011)
    current = hass.states.get("sensor.calendrier_tempo_couleur_actuelle").attributes
    assert current["prix_hp"] == 0.2222


async def test_price_switches_at_22h_and_6h(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    """22 h : HC du jour blanc, minuit : toujours blanc HC, 6 h : HP bleu du lendemain."""
    freezer.move_to(datetime(2026, 12, 7, 21, 50, tzinfo=PARIS))
    _register(aioclient_mock, today_with_prices())
    await _setup(hass)
    assert float(_price(hass)) == 0.2222

    calls = aioclient_mock.call_count
    await _move(hass, freezer, datetime(2026, 12, 7, 22, 0, 1, tzinfo=PARIS))
    assert float(_price(hass)) == 0.2022
    assert hass.states.get(PRICE).attributes["periode"] == "hc"
    # Bascule calculée localement, sans requête.
    assert aioclient_mock.call_count == calls

    # Après minuit, l'API passe au 8 décembre (bleu) ; la journée Tempo du 7 continue.
    aioclient_mock.clear_requests()
    _register(aioclient_mock, today_with_prices("2026-12-08", "BLEU"), TOMORROW_UNAVAILABLE)
    await _move(hass, freezer, datetime(2026, 12, 8, 0, 6, tzinfo=PARIS))
    state = hass.states.get(PRICE)
    assert float(state.state) == 0.2022
    assert state.attributes["couleur"] == "blanc"
    assert state.attributes["date"] == "2026-12-07"

    await _move(hass, freezer, datetime(2026, 12, 8, 6, 0, 1, tzinfo=PARIS))
    state = hass.states.get(PRICE)
    assert float(state.state) == 0.1111
    assert state.attributes["couleur"] == "bleu"
    assert state.attributes["periode"] == "hp"


async def test_before_6h_uses_previous_tempo_day(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    """5 h 45 : la journée Tempo est celle de la veille (rouge, lue dans /api/history)."""
    freezer.move_to(datetime(2026, 12, 7, 5, 45, tzinfo=PARIS))
    _register(aioclient_mock, today_with_prices())
    aioclient_mock.get(
        f"{API_BASE_URL}/history?days=2",
        json={"status": "ok", "history": [{"date": "2026-12-06", "couleur_reelle": "ROUGE"}]},
    )
    await _setup(hass)
    state = hass.states.get(PRICE)
    assert float(state.state) == 0.3033
    assert state.attributes["couleur"] == "rouge"
    assert state.attributes["date"] == "2026-12-06"

    await _move(hass, freezer, datetime(2026, 12, 7, 6, 0, 1, tzinfo=PARIS))
    assert float(_price(hass)) == 0.2222


async def test_unknown_previous_day_gives_unknown_price(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    """Avant 6 h sans couleur de la veille : prix inconnu, jamais celui d'une autre couleur."""
    freezer.move_to(datetime(2026, 12, 7, 5, 45, tzinfo=PARIS))
    _register(aioclient_mock, today_with_prices())
    aioclient_mock.get(f"{API_BASE_URL}/history?days=2", status=503)
    await _setup(hass)
    assert _price(hass) == STATE_UNKNOWN


async def test_api_without_prices_gives_unknown(hass: HomeAssistant, mock_api: Any) -> None:
    """Ancienne réponse (sans `tarif` ni `tarifs`) : prix inconnu, rien en dur."""
    await _setup(hass)
    state = hass.states.get(PRICE)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["grille"] is None
    assert state.attributes["date_effet"] is None
    assert state.attributes["couleur"] == "blanc"
    today = hass.states.get("sensor.calendrier_tempo_couleur_aujourd_hui").attributes
    assert today["prix_hp"] is None and today["prix_hc"] is None


async def test_price_kept_during_api_outage(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    """API en panne : couleurs indisponibles, prix toujours calculé (tableau Énergie)."""
    _register(aioclient_mock, today_with_prices())
    await _setup(hass)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API_BASE_URL}/today", status=503)
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.calendrier_tempo_couleur_aujourd_hui").state == (
        STATE_UNAVAILABLE
    )
    assert float(_price(hass)) == 0.2222


async def test_grid_kept_24h_when_today_has_no_prices(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    """Réponse suivante sans grille : dernière grille reçue gardée 24 h au plus."""
    _register(aioclient_mock, today_with_prices())
    await _setup(hass)
    aioclient_mock.clear_requests()
    _register(aioclient_mock, TODAY, TOMORROW)
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert float(_price(hass)) == 0.2222

    freezer.tick(STALE_PAYLOAD_MAX_AGE + timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    # Le 8 décembre à 9 h 31 : couleur connue (bleu) mais grille périmée et
    # aucun champ `tarif` : prix inconnu.
    assert _price(hass) == STATE_UNKNOWN


def test_parse_tariff_rejects_invalid_values() -> None:
    assert parse_tariff({"hp": 0.2, "hc": 0.1}) == Tariff(hp=0.2, hc=0.1)
    assert parse_tariff({"hp": 0.2}) is None
    assert parse_tariff({"hp": True, "hc": 0.1}) is None
    assert parse_tariff({"hp": "0.2", "hc": 0.1}) is None
    assert parse_tariff({"hp": -0.2, "hc": 0.1}) is None
    assert parse_tariff({"hp": float("nan"), "hc": 0.1}) is None
    assert parse_tariff(None) is None


def test_parse_tariff_grid() -> None:
    grid = parse_tariff_grid(today_with_prices())
    assert grid is not None
    assert grid.colors["rouge"] == Tariff(hp=0.3333, hc=0.3033)
    assert grid.date_effet is not None and grid.date_effet.isoformat() == "2026-08-01"
    # Réponses en attente, en erreur ou anciennes : pas de grille.
    assert parse_tariff_grid(TODAY) is None
    assert parse_tariff_grid({**today_with_prices(), "status": "unavailable"}) is None
    unknown_color = {"status": "ok", "tarifs": {"couleurs": {"VERT": GRID["BLEU"]}}}
    assert parse_tariff_grid(unknown_color) is None
    partial = parse_tariff_grid({"status": "ok", "tarifs": {"couleurs": {"BLEU": GRID["BLEU"]}}})
    assert partial is not None and set(partial.colors) == {"bleu"}
    assert partial.date_effet is None


def test_parse_day_reads_tariff() -> None:
    assert parse_day(today_with_prices()).tarif == Tariff(hp=0.2222, hc=0.2022)
    assert parse_day(TODAY).tarif is None
    assert parse_day({**today_with_prices(), "status": "unavailable"}).tarif is None
