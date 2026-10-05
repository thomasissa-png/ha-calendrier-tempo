"""Constantes de l'intégration Calendrier Tempo EDF."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "calendrier_tempo"
NAME: Final = "Calendrier Tempo EDF"
VERSION: Final = "0.1.0"

SITE_URL: Final = "https://www.calendrier-tempo.fr/"
API_BASE_URL: Final = "https://www.calendrier-tempo.fr/api"
ENDPOINT_TODAY: Final = "today"
ENDPOINT_TOMORROW: Final = "tomorrow"
ENDPOINT_REMAINING: Final = "remaining"
ENDPOINT_PREDICTIONS: Final = "predictions"

USER_AGENT: Final = f"ha-calendrier-tempo/{VERSION}"

# L'API met ses réponses en cache 2 minutes et la couleur ne change que
# quelques fois par jour : 30 minutes suffisent largement.
SCAN_INTERVAL: Final = timedelta(minutes=30)
REQUEST_TIMEOUT_SECONDS: Final = 15

ATTRIBUTION: Final = (
    "Couleurs officielles EDF, prévisions indicatives de calendrier-tempo.fr"
)

# Horizons de prévision exposés en capteurs (J+2 à J+5 : zone de mesure du site).
FORECAST_HORIZONS: Final = (2, 3, 4, 5)
