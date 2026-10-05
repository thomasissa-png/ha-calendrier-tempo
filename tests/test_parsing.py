"""Tests de la lecture des réponses de l'API (fonctions pures)."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.calendrier_tempo.parsing import (
    ApiDataError,
    build_tempo_data,
    normalize_color,
    parse_day,
    parse_predictions,
    parse_remaining,
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
    assert red.confirmed is True


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
