"""Fixtures communes : réponses d'API au format relevé en production le 2026-10-05."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.calendrier_tempo.const import API_BASE_URL

TODAY: dict[str, Any] = {"status": "ok", "date": "2026-12-07", "couleur": "BLANC", "code": 2}
TOMORROW: dict[str, Any] = {"status": "ok", "date": "2026-12-08", "couleur": "BLEU", "code": 1}
TOMORROW_UNAVAILABLE: dict[str, Any] = {
    "status": "unavailable",
    "message": "Couleur de demain pas encore publiée par EDF",
}
REMAINING: dict[str, Any] = {
    "status": "ok",
    "remaining": {"ROUGE": 18, "BLANC": 35, "BLEU": 200},
    "totals": {"ROUGE": 22, "BLANC": 43, "BLEU": 300},
    "season_start": "2026-09-01",
    "season_end": "2027-08-31",
}


def prediction(day: str, color: str, **extra: Any) -> dict[str, Any]:
    """Une entrée de /api/predictions."""
    base: dict[str, Any] = {
        "date": day,
        "couleur_predite": color,
        "probabilite_bleu": 0.2,
        "probabilite_blanc": 0.3,
        "probabilite_rouge": 0.5,
        "score_risque": 61.0,
        "temp_min_prevue": -2.0,
        "temp_max_prevue": 4.0,
        "temp_moy_prevue": 1.1,
        "raison": "Froid marqué",
        "horizon": "J-3",
        "confirmed": False,
        "simulated": False,
    }
    base.update(extra)
    return base


PREDICTIONS: dict[str, Any] = {
    "status": "ok",
    "predictions": [
        prediction("2026-12-07", "BLANC", confirmed=True),
        prediction("2026-12-08", "BLEU", confirmed=True),
        prediction("2026-12-09", "BLANC"),
        prediction("2026-12-10", "ROUGE"),
        prediction("2026-12-11", "ROUGE"),
        prediction("2026-12-12", "BLANC"),
        prediction("2026-12-13", "BLEU"),
    ],
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Active les intégrations personnalisées dans chaque test."""


@pytest.fixture
def mock_api(aioclient_mock: Any) -> Any:
    """API en bon état (demain déjà publié)."""
    aioclient_mock.get(f"{API_BASE_URL}/today", json=TODAY)
    aioclient_mock.get(f"{API_BASE_URL}/tomorrow", json=TOMORROW)
    aioclient_mock.get(f"{API_BASE_URL}/remaining", json=REMAINING)
    aioclient_mock.get(f"{API_BASE_URL}/predictions", json=PREDICTIONS)
    return aioclient_mock
