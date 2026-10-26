"""Tests de l'entité calendrier (jours blancs et rouges sur tout l'horizon)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.calendrier_tempo.calendar import build_event
from custom_components.calendrier_tempo.const import API_BASE_URL, DOMAIN, NAME
from custom_components.calendrier_tempo.parsing import ForecastDay

from .conftest import REMAINING, TODAY, TOMORROW, prediction

PARIS = ZoneInfo("Europe/Paris")
ENTITY_ID = "calendar.calendrier_tempo"


async def _setup(hass: HomeAssistant, freezer: FrozenDateTimeFactory, lang: str = "fr") -> None:
    await hass.config.async_set_time_zone("Europe/Paris")
    hass.config.language = lang
    freezer.move_to(datetime(2026, 12, 7, 9, 0, tzinfo=PARIS))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, title=NAME)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _get_events(hass: HomeAssistant, start: datetime, end: datetime) -> list[dict[str, Any]]:
    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {"start_date_time": start, "end_date_time": end},
        target={"entity_id": ENTITY_ID},
        blocking=True,
        return_response=True,
    )
    return response[ENTITY_ID]["events"]


async def test_calendar_events_whole_horizon(
    hass: HomeAssistant, mock_api: Any, freezer: FrozenDateTimeFactory
) -> None:
    await _setup(hass, freezer)
    state = hass.states.get(ENTITY_ID)
    assert state.attributes["friendly_name"] == "Calendrier Tempo EDF"
    # Aujourd'hui est un jour blanc officiel : l'entité est « on ».
    assert state.state == "on"
    assert state.attributes["message"] == "Jour blanc (officiel)"

    events = await _get_events(
        hass,
        datetime(2026, 12, 1, tzinfo=PARIS),
        datetime(2027, 1, 1, tzinfo=PARIS),
    )
    # Jours bleus exclus : blanc 7 (officiel), blanc 9, rouges 10 et 11, blanc 12, rouge 15.
    # 0.3.1 : les probabilités de la fixture (bleu 20 %, blanc 30 %, rouge 50 %) sont une
    # hésitation selon la règle du site (écart < 30 points, seconde > 15 %).
    assert [(e["start"], e["summary"]) for e in events] == [
        ("2026-12-07", "Jour blanc (officiel)"),
        ("2026-12-09", "Jour blanc ou rouge ? (30 %)"),
        ("2026-12-10", "Jour rouge ou blanc ? (50 %)"),
        ("2026-12-11", "Jour rouge ou blanc ? (50 %)"),
        ("2026-12-12", "Jour blanc ou rouge ? (30 %)"),
        ("2026-12-15", "Jour rouge ou blanc ? (41 %)"),
    ]
    # Événements « journée entière » : fin = lendemain.
    for e in events:
        assert date.fromisoformat(e["end"]) - date.fromisoformat(e["start"]) == timedelta(days=1)

    official, j3, j8 = events[0], events[2], events[5]
    assert official["description"] == "Couleur officielle publiée par EDF."
    assert j3["description"].splitlines() == [
        "Prévision calendrier-tempo.fr à J+3, dans la zone la plus fiable (J+2 à J+5).",
        "Hésitation entre rouge (50 %) et blanc (30 %) : les deux restent possibles.",
        "Probabilités : bleu 20 %, blanc 30 %, rouge 50 %.",
        "Température moyenne prévue : 1,1 °C.",
        "Seule la couleur publiée par EDF fait foi.",
    ]
    assert "J+8 : tendance indicative (6 à 15 jours)" in j8["description"]


async def test_calendar_date_range(
    hass: HomeAssistant, mock_api: Any, freezer: FrozenDateTimeFactory
) -> None:
    await _setup(hass, freezer)
    events = await _get_events(
        hass,
        datetime(2026, 12, 10, 0, 0, tzinfo=PARIS),
        datetime(2026, 12, 11, 0, 0, tzinfo=PARIS),
    )
    assert [e["start"] for e in events] == ["2026-12-10"]

    # Une période qui commence en cours de journée inclut l'événement du jour.
    events = await _get_events(
        hass,
        datetime(2026, 12, 15, 18, 0, tzinfo=PARIS),
        datetime(2026, 12, 31, 0, 0, tzinfo=PARIS),
    )
    assert [e["start"] for e in events] == ["2026-12-15"]

    assert await _get_events(
        hass,
        datetime(2026, 12, 23, tzinfo=PARIS),
        datetime(2027, 1, 31, tzinfo=PARIS),
    ) == []


async def test_calendar_off_on_blue_day_shows_next_event(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    aioclient_mock.get(
        f"{API_BASE_URL}/today",
        json={"status": "ok", "date": "2026-12-07", "couleur": "BLEU", "code": 1},
    )
    aioclient_mock.get(f"{API_BASE_URL}/tomorrow", json=TOMORROW)
    aioclient_mock.get(f"{API_BASE_URL}/remaining", json=REMAINING)
    aioclient_mock.get(
        f"{API_BASE_URL}/predictions",
        json={"predictions": [prediction("2026-12-10", "ROUGE")]},
    )
    await _setup(hass, freezer)
    state = hass.states.get(ENTITY_ID)
    assert state.state == "off"
    assert state.attributes["message"] == "Jour rouge ou blanc ? (50 %)"
    assert state.attributes["all_day"] is True
    assert state.attributes["start_time"].startswith("2026-12-10")


async def test_calendar_official_tomorrow_wins(
    hass: HomeAssistant, aioclient_mock: Any, freezer: FrozenDateTimeFactory
) -> None:
    """EDF annonce demain rouge : l'événement devient officiel, sans probabilité."""
    aioclient_mock.get(f"{API_BASE_URL}/today", json=TODAY)
    aioclient_mock.get(
        f"{API_BASE_URL}/tomorrow",
        json={"status": "ok", "date": "2026-12-08", "couleur": "ROUGE", "code": 3},
    )
    aioclient_mock.get(f"{API_BASE_URL}/remaining", json=REMAINING)
    aioclient_mock.get(
        f"{API_BASE_URL}/predictions",
        json={"predictions": [prediction("2026-12-08", "BLANC")]},
    )
    await _setup(hass, freezer)
    events = await _get_events(
        hass,
        datetime(2026, 12, 8, tzinfo=PARIS),
        datetime(2026, 12, 9, tzinfo=PARIS),
    )
    assert [(e["summary"], e["description"]) for e in events] == [
        ("Jour rouge (officiel)", "Couleur officielle publiée par EDF.")
    ]


async def test_calendar_english(
    hass: HomeAssistant, mock_api: Any, freezer: FrozenDateTimeFactory
) -> None:
    await _setup(hass, freezer, lang="en")
    events = await _get_events(
        hass,
        datetime(2026, 12, 10, tzinfo=PARIS),
        datetime(2026, 12, 11, tzinfo=PARIS),
    )
    assert events[0]["summary"] == "Red or white day? (50%)"
    assert "Only the color published by EDF is authoritative." in events[0]["description"]
    assert hass.states.get(ENTITY_ID).attributes["message"] == "White day (official)"


def test_build_event_without_probability() -> None:
    day = ForecastDay(date=date(2026, 12, 20), offset=13, color="rouge", official=False)
    event = build_event(day, "fr")
    assert event.summary == "Jour rouge prévu"
    assert event.description == (
        "Prévision calendrier-tempo.fr à J+13 : tendance indicative (6 à 15 jours).\n"
        "Seule la couleur publiée par EDF fait foi."
    )
    assert event.uid == "calendrier_tempo_2026-12-20"
    assert (event.start, event.end) == (date(2026, 12, 20), date(2026, 12, 21))
