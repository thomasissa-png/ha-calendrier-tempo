"""Calendrier Tempo EDF : un événement par jour blanc ou rouge de l'horizon.

Les jours bleus (environ 300 par an, la couleur par défaut) ne créent pas
d'événement : l'entité est « on » uniquement un jour blanc ou rouge, et les
déclencheurs de calendrier ne réagissent qu'aux jours qui comptent.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import TempoConfigEntry, TempoCoordinator
from .entity import TempoEntity
from .parsing import (
    COLOR_BLANC,
    COLOR_ROUGE,
    COLORS,
    FIABILITE_FIABLE,
    ForecastDay,
    percent,
)

PARALLEL_UPDATES = 0

EVENT_COLORS = (COLOR_BLANC, COLOR_ROUGE)
# Avant J+2, la couleur sera bientôt publiée par EDF : la prévision n'est qu'un relais.
FIRST_FORECAST_DAY = 2

# Textes des événements (non couverts par le système de traduction des entités).
TEXTS = {
    "fr": {
        "colors": {"bleu": "bleu", "blanc": "blanc", "rouge": "rouge"},
        "official": "Jour {color} (officiel)",
        "forecast": "Jour {color} prévu",
        "forecast_proba": "Jour {color} prévu (probabilité {pct} %)",
        "hesitation": "Jour {color} ou {second} ?",
        "hesitation_proba": "Jour {color} ou {second} ? ({pct} %)",
        "desc_official": "Couleur officielle publiée par EDF.",
        "desc_pending": "Prévision calendrier-tempo.fr à J+{n}, en attendant l'annonce d'EDF.",
        "desc_fiable": "Prévision calendrier-tempo.fr à J+{n}, dans la zone la plus fiable (J+2 à J+5).",
        "desc_indicative": "Prévision calendrier-tempo.fr à J+{n} : tendance indicative (6 à 15 jours).",
        "desc_hesitation": "Hésitation entre {color} et {second} : les deux restent possibles.",
        "desc_hesitation_probas": (
            "Hésitation entre {color} ({pct} %) et {second} ({pct2} %) : "
            "les deux restent possibles."
        ),
        "desc_probas": "Probabilités : {probas}.",
        "desc_temp": "Température moyenne prévue : {temp} °C.",
        "desc_disclaimer": "Seule la couleur publiée par EDF fait foi.",
        "proba_item": "{color} {pct} %",
    },
    "en": {
        "colors": {"bleu": "blue", "blanc": "white", "rouge": "red"},
        "official": "{Color} day (official)",
        "forecast": "{Color} day forecast",
        "forecast_proba": "{Color} day forecast ({pct}% probability)",
        "hesitation": "{Color} or {second} day?",
        "hesitation_proba": "{Color} or {second} day? ({pct}%)",
        "desc_official": "Official color published by EDF.",
        "desc_pending": "calendrier-tempo.fr forecast at D+{n}, until EDF announces the color.",
        "desc_fiable": "calendrier-tempo.fr forecast at D+{n}, in the most reliable range (D+2 to D+5).",
        "desc_indicative": "calendrier-tempo.fr forecast at D+{n}: indicative trend (6 to 15 days).",
        "desc_hesitation": "Hesitation between {color} and {second}: both remain possible.",
        "desc_hesitation_probas": (
            "Hesitation between {color} ({pct}%) and {second} ({pct2}%): both remain possible."
        ),
        "desc_probas": "Probabilities: {probas}.",
        "desc_temp": "Forecast mean temperature: {temp} °C.",
        "desc_disclaimer": "Only the color published by EDF is authoritative.",
        "proba_item": "{color} {pct}%",
    },
}


def _pct(value: float) -> int:
    # Arrondi « demi vers le haut », le même que le site (0,505 -> 51 %).
    return percent(value)


def _format_temp(value: object, lang: str) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    text = f"{value:.1f}"
    return text.replace(".", ",") if lang == "fr" else text


def build_event(day: ForecastDay, lang: str = "fr") -> CalendarEvent:
    """Événement journée entière pour un jour blanc ou rouge."""
    texts = TEXTS.get(lang, TEXTS["en"])
    color_name = texts["colors"][day.color]
    names = {"color": color_name, "Color": color_name.capitalize()}
    probability = day.probability(day.color)
    # Jour officiel : jamais d'hésitation (second_color renvoie None).
    second = day.second_color()
    if second is not None:
        names["second"] = texts["colors"][second]
    if day.official:
        summary = texts["official"].format(**names)
        lines = [texts["desc_official"]]
    else:
        prefix = "hesitation" if second is not None else "forecast"
        if probability is None:
            summary = texts[prefix].format(**names)
        else:
            summary = texts[f"{prefix}_proba"].format(pct=_pct(probability), **names)
        if day.offset < FIRST_FORECAST_DAY:
            key = "desc_pending"
        elif day.fiabilite == FIABILITE_FIABLE:
            key = "desc_fiable"
        else:
            key = "desc_indicative"
        lines = [texts[key].format(n=day.offset)]
        if second is not None:
            p2 = day.probability(second)
            if probability is None or p2 is None:
                lines.append(texts["desc_hesitation"].format(**names))
            else:
                lines.append(
                    texts["desc_hesitation_probas"].format(
                        pct=_pct(probability), pct2=_pct(p2), **names
                    )
                )
        probas = [
            texts["proba_item"].format(color=texts["colors"][c], pct=_pct(p))
            for c in COLORS
            if (p := day.probability(c)) is not None
        ]
        if probas:
            lines.append(texts["desc_probas"].format(probas=", ".join(probas)))
        temp = _format_temp(day.attributes.get("temp_moy_prevue"), lang)
        if temp is not None:
            lines.append(texts["desc_temp"].format(temp=temp))
        lines.append(texts["desc_disclaimer"])
    return CalendarEvent(
        start=day.date,
        end=day.date + timedelta(days=1),
        summary=summary,
        description="\n".join(lines),
        uid=f"{DOMAIN}_{day.date.isoformat()}",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TempoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crée l'entité calendrier."""
    async_add_entities([TempoCalendar(entry.runtime_data)])


class TempoCalendar(TempoEntity, CalendarEntity):
    """Jours blancs et rouges, officiels puis prévus, sur tout l'horizon publié."""

    # Entité principale de l'appareil : elle porte le nom « Calendrier Tempo EDF ».
    _attr_name = None
    _attr_translation_key = "calendrier"

    def __init__(self, coordinator: TempoCoordinator) -> None:
        super().__init__(coordinator, "calendrier")
        self.entity_id = f"calendar.{DOMAIN}"

    def _lang(self) -> str:
        return "fr" if (self.hass.config.language or "").startswith("fr") else "en"

    def _events(self) -> list[CalendarEvent]:
        lang = self._lang()
        return [
            build_event(day, lang)
            for day in self.coordinator.data.days
            if day.color in EVENT_COLORS
        ]

    @property
    def event(self) -> CalendarEvent | None:
        """Événement en cours, sinon le prochain."""
        now = dt_util.now()
        return next((e for e in self._events() if e.end_datetime_local > now), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Événements qui chevauchent la période demandée."""
        return [
            e
            for e in self._events()
            if e.start_datetime_local < end_date and e.end_datetime_local > start_date
        ]
