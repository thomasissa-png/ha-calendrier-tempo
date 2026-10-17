"""Constantes de l'intégration Calendrier Tempo EDF."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "calendrier_tempo"
NAME: Final = "Calendrier Tempo EDF"
VERSION: Final = "0.3.0"

SITE_URL: Final = "https://www.calendrier-tempo.fr/"
API_BASE_URL: Final = "https://www.calendrier-tempo.fr/api"
ENDPOINT_TODAY: Final = "today"
ENDPOINT_TOMORROW: Final = "tomorrow"
ENDPOINT_REMAINING: Final = "remaining"
ENDPOINT_PREDICTIONS: Final = "predictions"
# Couleur de la veille, lue seulement entre 0 h et 6 h si elle n'est pas déjà connue.
ENDPOINT_HISTORY: Final = "history?days=2"

USER_AGENT: Final = f"ha-calendrier-tempo/{VERSION}"

# L'API met ses réponses en cache 2 minutes et la couleur ne change que
# quelques fois par jour : 30 minutes suffisent largement.
SCAN_INTERVAL: Final = timedelta(minutes=30)
REQUEST_TIMEOUT_SECONDS: Final = 15
# Après un échec ou une réponse incomplète : une seule relance, 5 minutes plus tard,
# puis retour au cycle de 30 minutes.
RETRY_INTERVAL: Final = timedelta(minutes=5)
# Prévisions et jours restants conservés pendant une panne de leur endpoint : 24 h au plus,
# pour ne jamais présenter d'anciennes prévisions comme récentes.
STALE_PAYLOAD_MAX_AGE: Final = timedelta(hours=24)

# Horaires en heure de Paris (celle d'EDF), quel que soit le fuseau de Home Assistant.
TIMEZONE: Final = "Europe/Paris"
# Changement de jour : 0 h 05, une fois expirés les caches de l'API (2 + 3 minutes).
DAY_REFRESH_HOUR: Final = 0
DAY_REFRESH_MINUTE: Final = 5

# Mise à jour supplémentaire juste après l'annonce par EDF de la couleur du
# lendemain (vers 11 h), pour ne pas attendre le cycle de 30 minutes.
ANNOUNCEMENT_REFRESH_HOUR: Final = 11
ANNOUNCEMENT_REFRESH_MINUTE: Final = 35

# Journée Tempo : de 6 h à 6 h le lendemain ; heures pleines de 6 h à 22 h.
TEMPO_DAY_START_HOUR: Final = 6
PEAK_END_HOUR: Final = 22
PERIOD_PEAK: Final = "hp"
PERIOD_OFF_PEAK: Final = "hc"
# Minuit : changement de date civile (la journée Tempo, elle, continue jusqu'à 6 h).
MIDNIGHT_HOUR: Final = 0

ATTRIBUTION: Final = (
    "Couleurs officielles EDF, prévisions indicatives de calendrier-tempo.fr"
)

# Capteurs individuels de prévision.
# J+2 à J+5 : zone mesurée la plus fiable, capteurs activés par défaut.
FORECAST_HORIZONS: Final = (2, 3, 4, 5)
# J+6 à J+15 : tendance indicative, capteurs créés mais désactivés par défaut
# (tout l'horizon reste disponible dans le calendrier et le capteur 15 jours).
INDICATIVE_HORIZONS: Final = tuple(range(6, 16))
