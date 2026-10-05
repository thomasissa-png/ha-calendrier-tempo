"""Tests de la lecture des réponses de l'API (fonctions pures)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.calendrier_tempo.parsing import (
    ApiDataError,
    build_forecast_days,
    build_tempo_data,
    fiabilite_for,
    normalize_color,
    parse_day,
    parse_history,
    parse_predictions,
    parse_remaining,
    period_for,
    tempo_day,
)

from .conftest import PREDICTIONS, REMAINING, TODAY, TOMORROW, TOMORROW_UNAVAILABLE, prediction

FALLBACK = date(2026, 12, 7)


def test_normalize_color() -> None:
    assert normalize_color("ROUGE") == "rouge"
    assert normalize_color(" Blanc ") == "blanc"
    assert normalize_color("VERT") is None
    assert normalize_color(None) is None
    assert normalize_color(3) is None


def test_parse_day_ok() -> None:
    day = parse_day(TODAY)
    assert day.date == date(2026, 12, 7)
    assert day.color == "blanc"
    assert day.code == 2


def test_parse_day_unavailable() -> None:
    day = parse_day(TOMORROW_UNAVAILABLE, "tomorrow")
    assert day.color is None
    assert day.date is None
    assert day.code is None


def test_parse_day_rejects_non_object() -> None:
    with pytest.raises(ApiDataError):
        parse_day(["not", "an", "object"])


def test_parse_remaining() -> None:
    remaining = parse_remaining(REMAINING)
    assert (remaining.rouge, remaining.blanc) == (18, 35)
    assert (remaining.total_rouge, remaining.total_blanc) == (22, 43)
    assert remaining.season_end == date(2027, 8, 31)


def test_parse_remaining_unavailable() -> None:
    remaining = parse_remaining({"status": "unavailable"})
    assert remaining.rouge is None
    assert remaining.blanc is None


def test_parse_predictions_keeps_only_existing_fields() -> None:
    result = parse_predictions(
        {"predictions": [{"date": "2026-12-09", "couleur_predite": "ROUGE", "raison": "Froid"}]}
    )
    assert len(result) == 1
    assert result[0].color == "rouge"
    assert result[0].attributes == {"raison": "Froid"}


def test_parse_predictions_skips_invalid_and_simulated() -> None:
    result = parse_predictions(
        {
            "predictions": [
                prediction("2026-12-10", "ROUGE", simulated=True),
                {"date": "pas une date", "couleur_predite": "BLEU"},
                {"date": "2026-12-11", "couleur_predite": "VIOLET"},
                "texte",
                prediction("2026-12-09", "BLEU"),
            ]
        }
    )
    assert [p.date for p in result] == [date(2026, 12, 9)]


def test_parse_predictions_empty() -> None:
    assert parse_predictions({"predictions": []}) == ()
    assert parse_predictions({"status": "ok"}) == ()


def test_build_tempo_data_offsets_and_next_red() -> None:
    data = build_tempo_data(TODAY, TOMORROW, REMAINING, PREDICTIONS, FALLBACK)
    assert data.reference_date == date(2026, 12, 7)
    j2 = data.prediction_for_offset(2)
    assert j2 is not None and j2.color == "blanc"
    j3 = data.prediction_for_offset(3)
    assert j3 is not None and j3.attributes["probabilite_rouge"] == 0.5
    red = data.next_red()
    assert red is not None and red.date == date(2026, 12, 10)


def test_next_red_absent() -> None:
    preds = {"predictions": [prediction("2026-12-09", "BLEU"), prediction("2026-12-10", "BLANC")]}
    data = build_tempo_data(TODAY, TOMORROW, REMAINING, preds, FALLBACK)
    assert data.next_red() is None


def test_next_red_official_tomorrow_wins_over_forecast() -> None:
    tomorrow_red = {"status": "ok", "date": "2026-12-08", "couleur": "ROUGE", "code": 3}
    preds = {"predictions": [prediction("2026-12-08", "BLEU"), prediction("2026-12-10", "ROUGE")]}
    data = build_tempo_data(TODAY, tomorrow_red, REMAINING, preds, FALLBACK)
    red = data.next_red()
    assert red is not None
    assert red.date == date(2026, 12, 8)
    assert red.official is True
    assert red.fiabilite == "officielle"


def test_next_red_ignores_past_days() -> None:
    preds = {"predictions": [prediction("2026-12-01", "ROUGE")]}
    data = build_tempo_data(TODAY, TOMORROW, REMAINING, preds, FALLBACK)
    assert data.next_red() is None


def test_reference_date_falls_back_when_today_unavailable() -> None:
    data = build_tempo_data(
        {"status": "unavailable"}, TOMORROW_UNAVAILABLE, REMAINING, {"predictions": []}, FALLBACK
    )
    assert data.reference_date == FALLBACK
    assert data.today.color is None
    assert data.prediction_for_offset(2) is None


def test_full_horizon_j0_to_j15() -> None:
    data = build_tempo_data(TODAY, TOMORROW, REMAINING, PREDICTIONS, FALLBACK)
    assert len(data.days) == 16
    assert [d.offset for d in data.days] == list(range(16))
    assert data.horizon_jours == 15
    assert data.generated_at == "2026-12-07T07:30:00+01:00"


def test_fiabilite_by_horizon() -> None:
    data = build_tempo_data(TODAY, TOMORROW, REMAINING, PREDICTIONS, FALLBACK)
    fiabilites = {d.offset: d.fiabilite for d in data.days}
    assert fiabilites[0] == fiabilites[1] == "officielle"
    assert all(fiabilites[n] == "fiable" for n in range(2, 6))
    assert all(fiabilites[n] == "indicative" for n in range(6, 16))
    assert fiabilite_for(1, official=False) == "fiable"
    assert fiabilite_for(5, official=False) == "fiable"
    assert fiabilite_for(6, official=False) == "indicative"
    assert fiabilite_for(15, official=True) == "officielle"


def test_official_color_overrides_forecast() -> None:
    """EDF a publié demain rouge alors que la prévision disait bleu."""
    tomorrow_red = {"status": "ok", "date": "2026-12-08", "couleur": "ROUGE", "code": 3}
    preds = {"predictions": [prediction("2026-12-08", "BLEU", probabilite_rouge=0.1)]}
    days = build_forecast_days(
        build_tempo_data(TODAY, tomorrow_red, REMAINING, preds, FALLBACK).predictions,
        parse_day(TODAY),
        parse_day(tomorrow_red, "tomorrow"),
        FALLBACK,
    )
    by_date = {d.date: d for d in days}
    # Aujourd'hui (officiel, absent des prévisions) est ajouté.
    assert by_date[date(2026, 12, 7)].color == "blanc"
    assert by_date[date(2026, 12, 7)].official is True
    tomorrow = by_date[date(2026, 12, 8)]
    assert (tomorrow.color, tomorrow.official) == ("rouge", True)
    # Probabilités d'un jour officiel : 1 pour sa couleur, 0 pour les autres.
    assert tomorrow.probability("rouge") == 1.0
    assert tomorrow.probability("bleu") == 0.0
    assert tomorrow.attributes["confirmed"] is True


def test_forecast_day_as_dict() -> None:
    data = build_tempo_data(TODAY, TOMORROW, REMAINING, PREDICTIONS, FALLBACK)
    j8 = data.day_for_offset(8)
    assert j8 is not None
    assert j8.as_dict() == {
        "date": "2026-12-15",
        "jour": 8,
        "couleur": "rouge",
        "officielle": False,
        "fiabilite": "indicative",
        "probabilite_bleu": 0.2,
        "probabilite_blanc": 0.3,
        "probabilite_rouge": 0.41,
    }


def test_probability_missing_is_none() -> None:
    preds = {"predictions": [{"date": "2026-12-09", "couleur_predite": "ROUGE"}]}
    data = build_tempo_data(TODAY, TOMORROW_UNAVAILABLE, REMAINING, preds, FALLBACK)
    j2 = data.day_for_offset(2)
    assert j2 is not None and j2.probability("rouge") is None


def test_next_white_and_past_days_excluded() -> None:
    preds = {
        "predictions": [
            prediction("2026-12-01", "BLANC"),
            prediction("2026-12-09", "BLEU"),
            prediction("2026-12-18", "BLANC"),
        ]
    }
    data = build_tempo_data(
        {"status": "ok", "date": "2026-12-07", "couleur": "BLEU"},
        TOMORROW_UNAVAILABLE,
        REMAINING,
        preds,
        FALLBACK,
    )
    assert date(2026, 12, 1) not in {d.date for d in data.days}
    white = data.next_white()
    assert white is not None
    assert (white.date, white.offset, white.fiabilite) == (date(2026, 12, 18), 11, "indicative")


def test_remaining_prefers_edf_counters() -> None:
    payload = dict(REMAINING, edf_official={"ROUGE": 17, "BLANC": 34, "BLEU": 199})
    remaining = parse_remaining(payload)
    assert (remaining.rouge, remaining.blanc, remaining.source) == (17, 34, "edf")
    assert parse_remaining(REMAINING).source == "calcul"
    assert parse_remaining({"status": "unavailable"}).source is None


def test_parse_history() -> None:
    colors = parse_history(
        {
            "status": "ok",
            "history": [
                {"date": "2026-12-06", "couleur_reelle": "ROUGE"},
                {"date": "2026-12-05", "couleur_reelle": "INCONNU"},
                "texte",
            ],
        }
    )
    assert colors == {date(2026, 12, 6): "rouge"}
    assert parse_history({"status": "ok"}) == {}


def test_stale_today_is_never_shown_as_today() -> None:
    """Juste après minuit : la réponse « aujourd'hui » date encore de la veille."""
    data = build_tempo_data(TODAY, TOMORROW, REMAINING, PREDICTIONS, date(2026, 12, 8))
    assert data.stale is True
    assert (data.today.date, data.today.color) == (date(2026, 12, 8), "bleu")
    assert (data.tomorrow.date, data.tomorrow.color) == (date(2026, 12, 9), None)
    assert (data.yesterday.date, data.yesterday.color) == (date(2026, 12, 7), "blanc")
    assert data.day_for_offset(0) is not None and data.day_for_offset(0).official is True
    assert not build_tempo_data(TODAY, TOMORROW, REMAINING, PREDICTIONS, FALLBACK).stale


def test_tempo_day_runs_from_6_to_6() -> None:
    paris = ZoneInfo("Europe/Paris")
    data = build_tempo_data(TODAY, TOMORROW, REMAINING, PREDICTIONS, FALLBACK)
    before = datetime(2026, 12, 8, 5, 59, tzinfo=paris)
    after = datetime(2026, 12, 8, 6, 0, tzinfo=paris)
    assert tempo_day(before) == date(2026, 12, 7)
    assert tempo_day(after) == date(2026, 12, 8)
    assert data.current_day(before).color == "blanc"
    assert data.current_day(after).color == "bleu"
    assert period_for(datetime(2026, 12, 8, 21, 59, tzinfo=paris)) == "hp"
    assert period_for(datetime(2026, 12, 8, 22, 0, tzinfo=paris)) == "hc"
    assert period_for(before) == "hc"


def test_empty_generated_at_is_none() -> None:
    data = build_tempo_data(
        TODAY, TOMORROW, REMAINING, {"predictions": [], "generated_at": ""}, FALLBACK
    )
    assert data.generated_at is None
