"""Lecture des réponses de l'API calendrier-tempo.fr.

Module sans dépendance Home Assistant : fonctions pures, testables seules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import math
from typing import Any

from .const import PEAK_END_HOUR, PERIOD_OFF_PEAK, PERIOD_PEAK, TEMPO_DAY_START_HOUR

# Couleurs exposées par les capteurs (minuscules, stables pour les automatisations).
COLOR_BLEU = "bleu"
COLOR_BLANC = "blanc"
COLOR_ROUGE = "rouge"
COLORS = (COLOR_BLEU, COLOR_BLANC, COLOR_ROUGE)

# Fiabilité d'un jour, alignée sur le site (page méthodologie) : couleur publiée
# par EDF, prévision jusqu'à J+5 (J+2 à J+5 = zone mesurée la plus fiable),
# prévision J+6 à J+15 (tendance indicative).
FIABILITE_OFFICIELLE = "officielle"
FIABILITE_FIABLE = "fiable"
FIABILITE_INDICATIVE = "indicative"
HORIZON_FIABLE_MAX = 5

# Hésitation, même règle que le site (incertitude.py) : écart entre la probabilité de la
# couleur prévue et celle de la seconde couleur (la plus probable des deux autres)
# inférieur à 0,30 ET seconde couleur au-dessus de 0,15. Jamais pour un jour officiel.
HESITATION_ECART = 0.30
HESITATION_SECONDE = 0.15
# Espace insécable avant « ? » et « : » dans le libellé (typographie du site).
NBSP = " "  # U+00A0

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
# Champs d'incertitude ajoutés à /api/predictions le 2026-10-26 (absents des anciennes réponses).
UNCERTAINTY_FIELDS = ("hesitation", "seconde_couleur", "tendance", "libelle")


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


def tempo_day(now_paris: datetime) -> date:
    """Journée Tempo en cours (heure de Paris) : celle de la veille avant 6 h."""
    return (now_paris - timedelta(hours=TEMPO_DAY_START_HOUR)).date()


def period_for(now_paris: datetime) -> str:
    """Heures pleines de 6 h à 22 h, heures creuses de 22 h à 6 h (heure de Paris)."""
    if TEMPO_DAY_START_HOUR <= now_paris.hour < PEAK_END_HOUR:
        return PERIOD_PEAK
    return PERIOD_OFF_PEAK


def percent(value: float) -> int:
    """Arrondi « demi vers le haut », comme le site : 0,505 -> 51, 0,285 -> 29."""
    return int(math.floor(round(value * 100, 9) + 0.5))


def hesitates(p1: float | None, p2: float | None) -> bool:
    """Écart < 0,30 et seconde > 0,15 (écart arrondi : 0,70 - 0,40 vaut bien 0,30)."""
    if p1 is None or p2 is None:
        return False
    return round(p1 - p2, 9) < HESITATION_ECART and p2 > HESITATION_SECONDE


def uncertainty_label(color: str, second: str | None, trend: bool, official: bool) -> str:
    """Libellé du site : « Blanc », « Blanc ou bleu ? », « Tendance blanc »,
    « Tendance : blanc ou bleu ? »."""
    if official or not (second or trend):
        return color.capitalize()
    if second:
        pair = f"{color} ou {second}{NBSP}?"
        return f"Tendance{NBSP}: {pair}" if trend else pair[0].upper() + pair[1:]
    return f"Tendance {color}"


def fiabilite_for(offset: int, official: bool) -> str:
    """Fiabilité d'un jour selon qu'il est officiel et son éloignement."""
    if official:
        return FIABILITE_OFFICIELLE
    if offset <= HORIZON_FIABLE_MAX:
        return FIABILITE_FIABLE
    return FIABILITE_INDICATIVE


@dataclass(frozen=True)
class Tariff:
    """Prix du kWh (EUR TTC) d'une couleur : heures pleines et heures creuses."""

    hp: float
    hc: float

    def price(self, period: str) -> float:
        return self.hp if period == PERIOD_PEAK else self.hc

    def as_dict(self) -> dict[str, float]:
        return {PERIOD_PEAK: self.hp, PERIOD_OFF_PEAK: self.hc}


@dataclass(frozen=True)
class TariffGrid:
    """Grille complète publiée par /api/today (champ `tarifs`)."""

    colors: dict[str, Tariff]
    date_effet: date | None = None

    def as_dict(self) -> dict[str, dict[str, float]]:
        return {color: self.colors[color].as_dict() for color in COLORS if color in self.colors}


@dataclass(frozen=True)
class DayColor:
    """Couleur officielle EDF d'un jour (aujourd'hui ou demain)."""

    date: date | None
    color: str | None
    code: int | None = None
    # Prix du kWh de cette couleur (champ `tarif` de l'API), absent des anciennes réponses.
    tarif: Tariff | None = None


@dataclass(frozen=True)
class Prediction:
    """Prévision (ou couleur confirmée) pour un jour donné."""

    date: date
    color: str
    attributes: dict[str, Any] = field(default_factory=dict)
    # Champs d'incertitude bruts de l'API (UNCERTAINTY_FIELDS), s'ils existent.
    uncertainty: dict[str, Any] = field(default_factory=dict)

    @property
    def confirmed(self) -> bool:
        return bool(self.attributes.get("confirmed"))


@dataclass(frozen=True)
class ForecastDay:
    """Un jour de l'horizon : couleur officielle EDF si connue, sinon prévision."""

    date: date
    offset: int
    color: str
    official: bool
    attributes: dict[str, Any] = field(default_factory=dict)
    uncertainty: dict[str, Any] = field(default_factory=dict)

    @property
    def fiabilite(self) -> str:
        return fiabilite_for(self.offset, self.official)

    @property
    def tendance(self) -> bool:
        """Prévision au-delà de J+5 : une tendance (calcul local, toujours à jour)."""
        return not self.official and self.offset > HORIZON_FIABLE_MAX

    def _api_second_color(self) -> tuple[bool, str | None]:
        """(champs de l'API exploitables ?, seconde couleur si hésitation)."""
        flag = self.uncertainty.get("hesitation")
        if not isinstance(flag, bool):
            return False, None
        if not flag:
            return True, None
        second = normalize_color(self.uncertainty.get("seconde_couleur"))
        if second is None or second == self.color:
            return False, None
        return True, second

    def second_color(self) -> str | None:
        """Seconde couleur en cas d'hésitation, sinon None (jamais pour un jour officiel).

        Champs `hesitation` et `seconde_couleur` de l'API s'ils sont présents et
        cohérents, sinon même calcul que le site à partir des probabilités.
        """
        if self.official:
            return None
        usable, second = self._api_second_color()
        if usable:
            return second
        others = [
            (c, p) for c in COLORS if c != self.color and (p := self.probability(c)) is not None
        ]
        if not others:
            return None
        # À égalité, ordre stable bleu, blanc, rouge (comme le site).
        second, p2 = max(others, key=lambda item: item[1])
        return second if hesitates(self.probability(self.color), p2) else None

    @property
    def hesitation(self) -> bool:
        return self.second_color() is not None

    @property
    def libelle(self) -> str:
        """Libellé du site (« Blanc ou bleu ? »...) : celui de l'API s'il est cohérent."""
        api_label = self.uncertainty.get("libelle")
        api_trend = self.uncertainty.get("tendance")
        if (
            not self.official
            and isinstance(api_label, str)
            and api_label.strip()
            and self._api_second_color()[0]
            and (not isinstance(api_trend, bool) or api_trend == self.tendance)
        ):
            return api_label
        return uncertainty_label(self.color, self.second_color(), self.tendance, self.official)

    def probability(self, color: str) -> float | None:
        """Probabilité (0 à 1) d'une couleur ; 1 ou 0 pour un jour officiel."""
        if self.official:
            return 1.0 if color == self.color else 0.0
        value = self.attributes.get(f"probabilite_{color}")
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        return float(value)

    def as_dict(self) -> dict[str, Any]:
        """Résumé d'un jour (attribut `previsions` du capteur 15 jours)."""
        item: dict[str, Any] = {
            "date": self.date.isoformat(),
            "jour": self.offset,
            "couleur": self.color,
            "officielle": self.official,
            "fiabilite": self.fiabilite,
        }
        for color in COLORS:
            item[f"probabilite_{color}"] = self.probability(color)
        return item


# Origine des jours restants : compteurs EDF, sinon calcul du site à partir
# des couleurs officielles enregistrées.
SOURCE_EDF = "edf"
SOURCE_CALCUL = "calcul"


@dataclass(frozen=True)
class Remaining:
    """Jours restants dans la saison en cours."""

    rouge: int | None
    blanc: int | None
    total_rouge: int | None = None
    total_blanc: int | None = None
    season_start: date | None = None
    season_end: date | None = None
    source: str | None = None


@dataclass(frozen=True)
class TempoData:
    """Ensemble des données lues lors d'une mise à jour."""

    reference_date: date
    today: DayColor
    tomorrow: DayColor
    remaining: Remaining
    predictions: tuple[Prediction, ...]
    days: tuple[ForecastDay, ...] = ()
    generated_at: str | None = None
    yesterday: DayColor = field(default_factory=lambda: DayColor(date=None, color=None))
    # Grille de prix du kWh, None tant que l'API ne la fournit pas.
    tarifs: TariffGrid | None = None
    # Vrai si /api/today ou /api/tomorrow a renvoyé une autre date que prévu
    # (copie en cache juste après minuit, copie de secours) : relance rapide.
    stale: bool = False

    def official_day(self, day: date) -> DayColor:
        """Couleur officielle connue pour ce jour (hier, aujourd'hui ou demain)."""
        for known in (self.today, self.tomorrow, self.yesterday):
            if known.date == day and known.color is not None:
                return known
        return DayColor(date=day, color=None)

    def current_day(self, now_paris: datetime) -> DayColor:
        """Couleur qui s'applique maintenant : journée Tempo de 6 h à 6 h."""
        return self.official_day(tempo_day(now_paris))

    def day_tariff(self, day: DayColor) -> Tariff | None:
        """Prix HP/HC d'un jour officiel : champ `tarif`, sinon grille selon sa couleur."""
        if day.tarif is not None:
            return day.tarif
        if day.color is None or self.tarifs is None:
            return None
        return self.tarifs.colors.get(day.color)

    def current_price(self, now_paris: datetime) -> float | None:
        """Prix du kWh qui s'applique maintenant (journée Tempo et période HP/HC)."""
        tariff = self.day_tariff(self.current_day(now_paris))
        return tariff.price(period_for(now_paris)) if tariff else None

    def prediction_for_offset(self, days: int) -> Prediction | None:
        """Prévision brute de l'API pour J+days (par rapport à la date de référence)."""
        target = self.reference_date + timedelta(days=days)
        return next((p for p in self.predictions if p.date == target), None)

    def day_for_offset(self, days: int) -> ForecastDay | None:
        """Jour J+days de l'horizon, couleur officielle prioritaire."""
        return next((d for d in self.days if d.offset == days), None)

    def next_color(self, color: str) -> ForecastDay | None:
        """Premier jour de cette couleur (officielle ou prévue) à partir d'aujourd'hui."""
        return next((d for d in self.days if d.color == color), None)

    def next_red(self) -> ForecastDay | None:
        return self.next_color(COLOR_ROUGE)

    def next_white(self) -> ForecastDay | None:
        return self.next_color(COLOR_BLANC)

    @property
    def horizon_jours(self) -> int:
        """Nombre de jours couverts après aujourd'hui (15 en temps normal)."""
        return max((d.offset for d in self.days), default=0)


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
    color = normalize_color(data.get("couleur"))
    return DayColor(
        date=parse_date(data.get("date")),
        color=color,
        # Code 0 (couleur inconnue) ou sans couleur lisible : jamais exposé comme couleur.
        code=code if color and isinstance(code, int) and not isinstance(code, bool) else None,
        tarif=parse_tariff(data.get("tarif")),
    )


def _as_price(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    price = float(value)
    return price if math.isfinite(price) and price >= 0 else None


def parse_tariff(value: Any) -> Tariff | None:
    """Lit {"hp": 0.1654, "hc": 0.1356}. None si absent ou incomplet."""
    if not isinstance(value, dict):
        return None
    hp, hc = _as_price(value.get("hp")), _as_price(value.get("hc"))
    if hp is None or hc is None:
        return None
    return Tariff(hp=hp, hc=hc)


def parse_tariff_grid(payload: Any) -> TariffGrid | None:
    """Lit le champ `tarifs` de /api/today. None si absent (ancienne réponse) ou vide."""
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return None
    tarifs = payload.get("tarifs")
    couleurs = tarifs.get("couleurs") if isinstance(tarifs, dict) else None
    if not isinstance(couleurs, dict):
        return None
    colors: dict[str, Tariff] = {}
    for key, value in couleurs.items():
        color = normalize_color(key)
        tariff = parse_tariff(value)
        if color is not None and tariff is not None:
            colors[color] = tariff
    if not colors:
        return None
    return TariffGrid(colors=colors, date_effet=parse_date(tarifs.get("date_effet")))


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _counters(value: Any) -> tuple[int | None, int | None]:
    value = value if isinstance(value, dict) else {}
    return _as_int(value.get("ROUGE")), _as_int(value.get("BLANC"))


def parse_remaining(payload: Any) -> Remaining:
    """Lit /api/remaining : compteurs EDF (`edf_official`) en priorité, calcul du site sinon."""
    data = _require_dict(payload, "remaining")
    if data.get("status", "ok") != "ok":
        return Remaining(rouge=None, blanc=None)
    totals = data.get("totals")
    totals = totals if isinstance(totals, dict) else {}
    rouge, blanc = _counters(data.get("edf_official"))
    source = SOURCE_EDF
    if rouge is None or blanc is None:
        rouge, blanc = _counters(data.get("remaining"))
        source = SOURCE_CALCUL
    return Remaining(
        rouge=rouge,
        blanc=blanc,
        total_rouge=_as_int(totals.get("ROUGE")),
        total_blanc=_as_int(totals.get("BLANC")),
        season_start=parse_date(data.get("season_start")),
        season_end=parse_date(data.get("season_end")),
        source=source if rouge is not None or blanc is not None else None,
    )


def parse_history(payload: Any) -> dict[date, str]:
    """Lit /api/history : couleurs officielles des derniers jours."""
    data = _require_dict(payload, "history")
    items = data.get("history")
    colors: dict[date, str] = {}
    if not isinstance(items, list):
        return colors
    for item in items:
        if not isinstance(item, dict):
            continue
        day = parse_date(item.get("date"))
        color = normalize_color(item.get("couleur_reelle"))
        if day is not None and color is not None:
            colors[day] = color
    return colors


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
        uncertainty = {key: item[key] for key in UNCERTAINTY_FIELDS if key in item}
        result[day] = Prediction(
            date=day, color=color, attributes=attributes, uncertainty=uncertainty
        )
    return tuple(sorted(result.values(), key=lambda p: p.date))


def build_forecast_days(
    predictions: tuple[Prediction, ...],
    today: DayColor,
    tomorrow: DayColor,
    reference_date: date,
) -> tuple[ForecastDay, ...]:
    """Horizon complet à partir de reference_date, jour par jour.

    La couleur officielle EDF (/api/today, /api/tomorrow) prime sur la prévision ;
    une entrée marquée `confirmed` par l'API est aussi officielle.
    """
    official = {d.date: d.color for d in (today, tomorrow) if d.date and d.color}
    days: dict[date, ForecastDay] = {}
    for p in predictions:
        if p.date < reference_date:
            continue
        days[p.date] = ForecastDay(
            date=p.date,
            offset=(p.date - reference_date).days,
            color=p.color,
            official=p.confirmed,
            attributes=dict(p.attributes),
            uncertainty=dict(p.uncertainty),
        )
    for day, color in official.items():
        if day < reference_date:
            continue
        previous = days.get(day)
        attributes = dict(previous.attributes) if previous else {}
        attributes["confirmed"] = True
        days[day] = ForecastDay(
            date=day,
            offset=(day - reference_date).days,
            color=color,
            official=True,
            attributes=attributes,
        )
    return tuple(days[d] for d in sorted(days))


def build_tempo_data(
    today_payload: Any,
    tomorrow_payload: Any,
    remaining_payload: Any,
    predictions_payload: Any,
    current_date: date,
) -> TempoData:
    """Assemble les 4 réponses autour de la date du jour à Paris (`current_date`).

    Chaque couleur officielle est rangée selon SA date : une réponse en retard
    (cache juste après minuit, copie de secours de plusieurs jours) ne fait
    jamais passer la couleur de la veille pour celle d'aujourd'hui.
    """
    parsed = (parse_day(today_payload, "today"), parse_day(tomorrow_payload, "tomorrow"))
    expected = (current_date, current_date + timedelta(days=1))
    stale = any(d.date is not None and d.date != e for d, e in zip(parsed, expected, strict=True))
    by_date = {d.date: d for d in parsed if d.date is not None and d.color is not None}
    today = by_date.get(current_date, DayColor(date=current_date, color=None))
    tomorrow = by_date.get(expected[1], DayColor(date=expected[1], color=None))
    # Réponse « aujourd'hui » de la veille (en retard) : couleur d'hier, utile jusqu'à 6 h.
    previous = current_date - timedelta(days=1)
    yesterday = by_date.get(previous, DayColor(date=previous, color=None))
    predictions = parse_predictions(predictions_payload)
    generated_at = (
        predictions_payload.get("generated_at") if isinstance(predictions_payload, dict) else None
    )
    return TempoData(
        reference_date=current_date,
        today=today,
        tomorrow=tomorrow,
        remaining=parse_remaining(remaining_payload),
        predictions=predictions,
        days=build_forecast_days(predictions, today, tomorrow, current_date),
        generated_at=generated_at if isinstance(generated_at, str) and generated_at else None,
        yesterday=yesterday,
        stale=stale,
        tarifs=parse_tariff_grid(today_payload),
    )
