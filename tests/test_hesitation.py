"""Hésitation entre deux couleurs (0.3.1) : même règle et mêmes textes que le site."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.calendrier_tempo.calendar import build_event
from custom_components.calendrier_tempo.const import API_BASE_URL, DOMAIN, NAME
from custom_components.calendrier_tempo.parsing import (
    ForecastDay,
    build_tempo_data,
    hesitates,
    percent,
)

from .conftest import BLEU_PROBAS, REMAINING, TODAY, TOMORROW, prediction

NBSP = " "  # espace insécable (U+00A0), comme le site
REF = date(2026, 12, 7)
# Blanc 50 %, bleu 45 % : le cas du site (« Blanc ou bleu ? »).
HESITANT = {"probabilite_bleu": 0.45, "probabilite_blanc": 0.5, "probabilite_rouge": 0.05}
NET = {"probabilite_bleu": 0.15, "probabilite_blanc": 0.8, "probabilite_rouge": 0.05}


def _day(
    offset: int,
    color: str,
    probas: dict[str, float],
    official: bool = False,
    uncertainty: dict[str, Any] | None = None,
    **extra: Any,
) -> ForecastDay:
    return ForecastDay(
        date=REF + timedelta(days=offset),
        offset=offset,
        color=color,
        official=official,
        attributes={**probas, **extra},
        uncertainty=uncertainty or {},
    )


# --- Règle et arrondi (identiques à incertitude.py du site) -------------------------


def test_percent_rounds_half_up() -> None:
    assert [percent(v) for v in (0.505, 0.285, 0.125, 0.5, 0.494)] == [51, 29, 13, 50, 49]


def test_hesitation_thresholds() -> None:
    assert hesitates(0.69, 0.40) is True
    # 0,70 - 0,40 vaut exactement 0,30 : pas d'hésitation, malgré les flottants.
    assert hesitates(0.70, 0.40) is False
    # Seconde couleur à 15 % tout juste : pas d'hésitation.
    assert hesitates(0.40, 0.15) is False
    assert hesitates(0.40, 0.16) is True
    assert hesitates(None, 0.4) is False


# --- Calcul de secours (réponse sans les champs ajoutés le 26/10) -------------------


def test_fallback_without_api_fields() -> None:
    day = _day(3, "blanc", HESITANT)
    assert day.second_color() == "bleu"
    assert day.hesitation is True
    assert day.tendance is False
    assert day.libelle == f"Blanc ou bleu{NBSP}?"


def test_fallback_net_day() -> None:
    day = _day(3, "blanc", NET)
    assert day.second_color() is None
    assert day.hesitation is False
    assert day.libelle == "Blanc"


def test_fallback_tie_keeps_site_order() -> None:
    # Égalité bleu/rouge derrière le blanc : ordre stable bleu, blanc, rouge.
    day = _day(2, "blanc", {"probabilite_bleu": 0.3, "probabilite_blanc": 0.4, "probabilite_rouge": 0.3})
    assert day.second_color() == "bleu"


def test_fallback_without_probabilities() -> None:
    day = ForecastDay(date=REF, offset=3, color="rouge", official=False)
    assert day.second_color() is None
    assert day.libelle == "Rouge"


# --- Champs de l'API prioritaires ----------------------------------------------------


def test_api_fields_win_over_local_rule() -> None:
    api = {"hesitation": True, "seconde_couleur": "BLEU", "tendance": False, "libelle": "Blanc ou bleu ?"}
    day = _day(3, "blanc", NET, uncertainty=api)
    assert day.second_color() == "bleu"
    assert day.libelle == "Blanc ou bleu ?"

    api = {"hesitation": False, "seconde_couleur": None, "tendance": False, "libelle": "Blanc"}
    day = _day(3, "blanc", HESITANT, uncertainty=api)
    assert day.second_color() is None
    assert day.libelle == "Blanc"


def test_inconsistent_api_fields_fall_back() -> None:
    # Hésitation annoncée sans seconde couleur lisible : calcul local.
    day = _day(3, "blanc", HESITANT, uncertainty={"hesitation": True, "seconde_couleur": None})
    assert day.second_color() == "bleu"
    day = _day(3, "blanc", NET, uncertainty={"hesitation": "oui", "libelle": "Blanc ou bleu ?"})
    assert day.second_color() is None
    assert day.libelle == "Blanc"
    # Libellé de l'API calculé avant le passage sous J+6 (réponse gardée en cache).
    stale = {"hesitation": False, "tendance": True, "libelle": "Tendance blanc"}
    day = _day(5, "blanc", NET, uncertainty=stale)
    assert day.libelle == "Blanc"


def test_confirmed_day_never_hesitates() -> None:
    api = {"hesitation": True, "seconde_couleur": "BLEU", "libelle": "Blanc ou bleu ?"}
    day = _day(2, "blanc", HESITANT, official=True, uncertainty=api)
    assert day.second_color() is None
    assert day.hesitation is False
    assert day.libelle == "Blanc"


def test_official_color_from_edf_removes_hesitation() -> None:
    api_fields = {
        "hesitation": True, "seconde_couleur": "BLEU", "tendance": False, "libelle": "Blanc ou bleu ?"
    }
    predictions = {
        "status": "ok",
        "predictions": [prediction("2026-12-08", "BLANC", **HESITANT, **api_fields)],
    }
    data = build_tempo_data(TODAY, TOMORROW, REMAINING, predictions, REF)
    tomorrow = data.day_for_offset(1)
    assert tomorrow.official is True
    assert tomorrow.color == "bleu"
    assert tomorrow.hesitation is False
    assert tomorrow.libelle == "Bleu"


def test_parse_keeps_api_fields_out_of_attributes() -> None:
    api_fields = {"hesitation": True, "seconde_couleur": "BLEU", "tendance": True, "libelle": "x"}
    predictions = {"status": "ok", "predictions": [prediction("2026-12-15", "BLANC", **api_fields)]}
    data = build_tempo_data(TODAY, TOMORROW, REMAINING, predictions, REF)
    day = data.day_for_offset(8)
    assert day.uncertainty == api_fields
    assert not set(api_fields) & set(day.attributes)


def test_trend_labels() -> None:
    assert _day(8, "blanc", HESITANT).libelle == f"Tendance{NBSP}: blanc ou bleu{NBSP}?"
    assert _day(8, "blanc", NET).libelle == "Tendance blanc"
    assert _day(8, "blanc", NET).tendance is True
    assert _day(5, "blanc", NET).tendance is False


# --- Agenda --------------------------------------------------------------------------


def test_event_net_forecast_unchanged() -> None:
    event = build_event(_day(3, "blanc", NET, temp_moy_prevue=1.1))
    assert event.summary == "Jour blanc prévu (probabilité 80 %)"
    assert event.description.splitlines() == [
        "Prévision calendrier-tempo.fr à J+3, dans la zone la plus fiable (J+2 à J+5).",
        "Probabilités : bleu 15 %, blanc 80 %, rouge 5 %.",
        "Température moyenne prévue : 1,1 °C.",
        "Seule la couleur publiée par EDF fait foi.",
    ]


def test_event_hesitation() -> None:
    event = build_event(_day(3, "blanc", HESITANT))
    assert event.summary == "Jour blanc ou bleu ? (50 %)"
    assert event.description.splitlines() == [
        "Prévision calendrier-tempo.fr à J+3, dans la zone la plus fiable (J+2 à J+5).",
        "Hésitation entre blanc (50 %) et bleu (45 %) : les deux restent possibles.",
        "Probabilités : bleu 45 %, blanc 50 %, rouge 5 %.",
        "Seule la couleur publiée par EDF fait foi.",
    ]


def test_event_trend_net_and_trend_hesitation() -> None:
    probas = {"probabilite_bleu": 0.1, "probabilite_blanc": 0.2, "probabilite_rouge": 0.7}
    net = build_event(_day(8, "rouge", probas))
    assert net.summary == "Jour rouge prévu (probabilité 70 %)"
    assert "Hésitation" not in net.description
    assert net.description.splitlines()[0] == (
        "Prévision calendrier-tempo.fr à J+8 : tendance indicative (6 à 15 jours)."
    )
    probas = {"probabilite_bleu": 0.2, "probabilite_blanc": 0.385, "probabilite_rouge": 0.415}
    hes = build_event(_day(8, "rouge", probas))
    assert hes.summary == "Jour rouge ou blanc ? (42 %)"
    assert hes.description.splitlines()[:2] == [
        "Prévision calendrier-tempo.fr à J+8 : tendance indicative (6 à 15 jours).",
        "Hésitation entre rouge (42 %) et blanc (39 %) : les deux restent possibles.",
    ]


def test_event_hesitation_from_api_without_probabilities() -> None:
    day = ForecastDay(
        date=REF + timedelta(days=4),
        offset=4,
        color="rouge",
        official=False,
        uncertainty={"hesitation": True, "seconde_couleur": "BLANC"},
    )
    event = build_event(day)
    assert event.summary == "Jour rouge ou blanc ?"
    assert "Hésitation entre rouge et blanc : les deux restent possibles." in event.description


def test_event_official_never_hesitates() -> None:
    api = {"hesitation": True, "seconde_couleur": "BLEU"}
    event = build_event(_day(0, "blanc", HESITANT, official=True, uncertainty=api))
    assert event.summary == "Jour blanc (officiel)"
    assert event.description == "Couleur officielle publiée par EDF."


def test_event_hesitation_english() -> None:
    event = build_event(_day(3, "blanc", HESITANT), "en")
    assert event.summary == "White or blue day? (50%)"
    assert "Hesitation between white (50%) and blue (45%): both remain possible." in event.description


# --- Capteurs et agenda dans Home Assistant --------------------------------------------

API_HESITANT = {
    "hesitation": True, "seconde_couleur": "BLEU", "tendance": False, "libelle": f"Blanc ou bleu{NBSP}?"
}
API_NET = {"hesitation": False, "seconde_couleur": None, "tendance": False, "libelle": "Rouge"}
PREDICTIONS_V031: dict[str, Any] = {
    "status": "ok",
    "generated_at": "2026-12-07T07:30:00+01:00",
    "predictions": [
        prediction("2026-12-09", "BLANC", **HESITANT, **API_HESITANT),
        prediction("2026-12-10", "ROUGE", probabilite_bleu=0.05, probabilite_blanc=0.15,
                   probabilite_rouge=0.8, **API_NET),
        # Ancien format (sans les 4 champs) : calcul de secours.
        prediction("2026-12-11", "BLANC", **HESITANT),
        prediction("2026-12-12", "BLEU", **BLEU_PROBAS),
        prediction("2026-12-15", "BLANC", **HESITANT,
                   hesitation=True, seconde_couleur="BLEU", tendance=True,
                   libelle=f"Tendance{NBSP}: blanc ou bleu{NBSP}?"),
    ],
}


async def _setup_v031(hass: HomeAssistant, aioclient_mock: Any) -> None:
    await hass.config.async_set_time_zone("Europe/Paris")
    hass.config.language = "fr"
    aioclient_mock.get(f"{API_BASE_URL}/today", json=TODAY)
    aioclient_mock.get(f"{API_BASE_URL}/tomorrow", json=TOMORROW)
    aioclient_mock.get(f"{API_BASE_URL}/remaining", json=REMAINING)
    aioclient_mock.get(f"{API_BASE_URL}/predictions", json=PREDICTIONS_V031)
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, title=NAME)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_forecast_sensors_attributes(hass: HomeAssistant, aioclient_mock: Any) -> None:
    await _setup_v031(hass, aioclient_mock)
    j2 = hass.states.get("sensor.calendrier_tempo_prevision_j2")
    # État inchangé : la couleur prévue, jamais « blanc ou bleu ».
    assert j2.state == "blanc"
    assert j2.attributes["hesitation"] is True
    assert j2.attributes["seconde_couleur"] == "bleu"
    assert j2.attributes["libelle"] == f"Blanc ou bleu{NBSP}?"
    # Attributs existants conservés.
    for key in ("date", "officielle", "fiabilite", "probabilite_bleu", "probabilite_blanc",
                "probabilite_rouge", "score_risque", "temp_moy_prevue", "raison", "confirmed"):
        assert key in j2.attributes
    assert j2.attributes["fiabilite"] == "fiable"
    for key in ("tendance", "horizon", "simulated"):
        assert key not in j2.attributes

    j3 = hass.states.get("sensor.calendrier_tempo_prevision_j3")
    assert j3.state == "rouge"
    assert (j3.attributes["hesitation"], j3.attributes["seconde_couleur"], j3.attributes["libelle"]) == (
        False, None, "Rouge"
    )
    j4 = hass.states.get("sensor.calendrier_tempo_prevision_j4")
    assert j4.state == "blanc"
    assert (j4.attributes["hesitation"], j4.attributes["seconde_couleur"]) == (True, "bleu")
    j5 = hass.states.get("sensor.calendrier_tempo_prevision_j5")
    assert (j5.state, j5.attributes["hesitation"], j5.attributes["libelle"]) == ("bleu", False, "Bleu")
    # Jour officiel (demain) : capteur « Couleur demain » inchangé, sans hésitation.
    demain = hass.states.get("sensor.calendrier_tempo_couleur_demain")
    assert demain.state == "bleu"
    assert "hesitation" not in demain.attributes


async def test_calendar_events_with_hesitation(hass: HomeAssistant, aioclient_mock: Any) -> None:
    await _setup_v031(hass, aioclient_mock)
    paris = ZoneInfo("Europe/Paris")
    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {"start_date_time": datetime(2026, 12, 1, tzinfo=paris),
         "end_date_time": datetime(2027, 1, 1, tzinfo=paris)},
        target={"entity_id": "calendar.calendrier_tempo"},
        blocking=True,
        return_response=True,
    )
    events = response["calendar.calendrier_tempo"]["events"]
    assert [(e["start"], e["summary"]) for e in events] == [
        ("2026-12-07", "Jour blanc (officiel)"),
        ("2026-12-09", "Jour blanc ou bleu ? (50 %)"),
        ("2026-12-10", "Jour rouge prévu (probabilité 80 %)"),
        ("2026-12-11", "Jour blanc ou bleu ? (50 %)"),
        ("2026-12-15", "Jour blanc ou bleu ? (50 %)"),
    ]
    assert "tendance indicative" in events[-1]["description"]
    assert "Hésitation entre blanc (50 %) et bleu (45 %)" in events[-1]["description"]
