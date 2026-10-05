"""Lecture des réponses de l'API calendrier-tempo.fr.

Module sans dépendance Home Assistant : fonctions pures, testables seules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

# Couleurs exposées par les capteurs (minuscules, stables pour les automatisations).
COLOR_BLEU = "bleu"
COLOR_BLANC = "blanc"
COLOR_ROUGE = "rouge"
COLORS = (COLOR_BLEU, COLOR_BLANC, COLOR_ROUGE)

# Champs d'une prévision repris tels quels en attributs, uniquement s'ils existent.
PREDICTION_ATTRIBUTES = (
    "probabilite_bleu",
    "probabilite_blanc",
    "probabilite_rouge",
    "score_risque",
    "temp_min_prevue",
    "temp_max_prevue",
    "temp_moy_prevue",
    "raison",
    "confirmed",
)


class ApiDataError(ValueError):
    """Réponse de l'API inexploitable (format inattendu)."""


def normalize_color(value: Any) -> str | None:
    """Convertit « BLEU », « Rouge »... en « bleu », « rouge ». None si inconnu."""
    if not isinstance(value, str):
        return None
    color = value.strip().lower()
    return color if color in COLORS else None


def parse_date(value: Any) -> date | None:
    """Lit une date ISO AAAA-MM-JJ, None si absente ou invalide."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


@dataclass(frozen=True)
class DayColor:
    """Couleur officielle EDF d'un jour (aujourd'hui ou demain)."""

    date: date | None
    color: str | None
    code: int | None = None


@dataclass(frozen=True)
class Prediction:
    """Prévision (ou couleur confirmée) pour un jour donné."""

    date: date
    color: str
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def confirmed(self) -> bool:
        return bool(self.attributes.get("confirmed"))


@dataclass(frozen=True)
class Remaining:
    """Jours restants dans la saison en cours."""

    rouge: int | None
    blanc: int | None
    total_rouge: int | None = None
    total_blanc: int | None = None
    season_start: date | None = None
    season_end: date | None = None


@dataclass(frozen=True)
class TempoData:
    """Ensemble des données lues lors d'une mise à jour."""

    reference_date: date
    today: DayColor
    tomorrow: DayColor
    remaining: Remaining
    predictions: tuple[Prediction, ...]

    def prediction_for_offset(self, days: int) -> Prediction | None:
        """Prévision pour J+days (par rapport à la date de référence)."""
        target = self.reference_date + timedelta(days=days)
        return next((p for p in self.predictions if p.date == target), None)

    def next_red(self) -> Prediction | None:
        """Premier jour rouge, officiel ou prévu, à partir d'aujourd'hui."""
        return next_red_day(self.predictions, self.today, self.tomorrow, self.reference_date)


def _require_dict(payload: Any, endpoint: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ApiDataError(f"Réponse inattendue de /api/{endpoint}")
    return payload


def parse_day(payload: Any, endpoint: str = "today") -> DayColor:
    """Lit /api/today ou /api/tomorrow. status « unavailable » = couleur inconnue."""
    data = _require_dict(payload, endpoint)
    if data.get("status") != "ok":
        return DayColor(date=parse_date(data.get("date")), color=None)
    code = data.get("code")
    return DayColor(
        date=parse_date(data.get("date")),
        color=normalize_color(data.get("couleur")),
        code=code if isinstance(code, int) and not isinstance(code, bool) else None,
    )


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def parse_remaining(payload: Any) -> Remaining:
    """Lit /api/remaining."""
    data = _require_dict(payload, "remaining")
    if data.get("status", "ok") != "ok":
        return Remaining(rouge=None, blanc=None)
    remaining = data.get("remaining")
    totals = data.get("totals")
    remaining = remaining if isinstance(remaining, dict) else {}
    totals = totals if isinstance(totals, dict) else {}
    return Remaining(
        rouge=_as_int(remaining.get("ROUGE")),
        blanc=_as_int(remaining.get("BLANC")),
        total_rouge=_as_int(totals.get("ROUGE")),
        total_blanc=_as_int(totals.get("BLANC")),
        season_start=parse_date(data.get("season_start")),
        season_end=parse_date(data.get("season_end")),
    )


def parse_predictions(payload: Any) -> tuple[Prediction, ...]:
    """Lit /api/predictions. Ignore les entrées invalides ou simulées."""
    data = _require_dict(payload, "predictions")
    items = data.get("predictions")
    if not isinstance(items, list):
        return ()
    result: dict[date, Prediction] = {}
    for item in items:
        if not isinstance(item, dict) or item.get("simulated") is True:
            continue
        day = parse_date(item.get("date"))
        color = normalize_color(item.get("couleur_predite"))
        if day is None or color is None or day in result:
            continue
        attributes = {key: item[key] for key in PREDICTION_ATTRIBUTES if key in item}
        result[day] = Prediction(date=day, color=color, attributes=attributes)
    return tuple(sorted(result.values(), key=lambda p: p.date))


def next_red_day(
    predictions: tuple[Prediction, ...],
    today: DayColor,
    tomorrow: DayColor,
    reference_date: date,
) -> Prediction | None:
    """Premier jour rouge à partir de reference_date.

    La couleur officielle EDF (aujourd'hui, demain) prime sur la prévision.
    """
    official = {
        day.date: day.color for day in (today, tomorrow) if day.date and day.color
    }
    candidates: dict[date, Prediction] = {
        p.date: p for p in predictions if p.date >= reference_date
    }
    for day, color in official.items():
        if day < reference_date:
            continue
        previous = candidates.get(day)
        attributes = dict(previous.attributes) if previous else {}
        attributes["confirmed"] = True
        candidates[day] = Prediction(date=day, color=color, attributes=attributes)
    return next(
        (candidates[d] for d in sorted(candidates) if candidates[d].color == COLOR_ROUGE),
        None,
    )


def build_tempo_data(
    today_payload: Any,
    tomorrow_payload: Any,
    remaining_payload: Any,
    predictions_payload: Any,
    fallback_date: date,
) -> TempoData:
    """Assemble les 4 réponses. La date de référence est celle d'EDF si connue."""
    today = parse_day(today_payload, "today")
    tomorrow = parse_day(tomorrow_payload, "tomorrow")
    return TempoData(
        reference_date=today.date or fallback_date,
        today=today,
        tomorrow=tomorrow,
        remaining=parse_remaining(remaining_payload),
        predictions=parse_predictions(predictions_payload),
    )
