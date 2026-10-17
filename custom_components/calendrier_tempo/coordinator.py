"""Coordinateur de mise à jour : interroge l'API calendrier-tempo.fr."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, datetime, timedelta
import logging
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    API_BASE_URL,
    DOMAIN,
    ENDPOINT_HISTORY,
    ENDPOINT_PREDICTIONS,
    ENDPOINT_REMAINING,
    ENDPOINT_TODAY,
    ENDPOINT_TOMORROW,
    REQUEST_TIMEOUT_SECONDS,
    RETRY_INTERVAL,
    SCAN_INTERVAL,
    STALE_PAYLOAD_MAX_AGE,
    TEMPO_DAY_START_HOUR,
    TIMEZONE,
    USER_AGENT,
)
from .parsing import (
    COLORS,
    ApiDataError,
    DayColor,
    Tariff,
    TariffGrid,
    TempoData,
    build_forecast_days,
    build_tempo_data,
    parse_history,
)

_LOGGER = logging.getLogger(__name__)

PARIS_TZ = ZoneInfo(TIMEZONE)

type TempoConfigEntry = ConfigEntry[TempoCoordinator]


class TempoApiError(Exception):
    """Erreur de communication avec l'API."""


class TempoApiClient:
    """Client HTTP minimal (session aiohttp partagée de Home Assistant)."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def async_get(self, endpoint: str) -> Any:
        """GET /api/<endpoint> et renvoie le JSON décodé."""
        url = f"{API_BASE_URL}/{endpoint}"
        try:
            async with self._session.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            ) as response:
                if response.status != 200:
                    raise TempoApiError(f"/api/{endpoint} : HTTP {response.status}")
                return await response.json(content_type=None)
        except TempoApiError:
            raise
        except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError) as err:
            raise TempoApiError(f"/api/{endpoint} : {err!r}") from err
        except ValueError as err:
            raise TempoApiError(f"/api/{endpoint} : JSON invalide") from err


class TempoCoordinator(DataUpdateCoordinator[TempoData]):
    """Lit les endpoints publics toutes les 30 minutes.

    /api/today et /api/tomorrow sont indispensables ; /api/remaining et
    /api/predictions sont facultatifs : en cas d'échec, la dernière réponse
    valide est conservée. Après un échec ou une réponse incomplète, une seule
    relance a lieu 5 minutes plus tard, puis le cycle normal reprend.
    """

    config_entry: TempoConfigEntry

    def __init__(self, hass: HomeAssistant, entry: TempoConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = TempoApiClient(async_get_clientsession(hass))
        # Dernière réponse valide de chaque endpoint facultatif, avec son heure de réception.
        self._last_payloads: dict[str, tuple[Any, datetime]] = {}
        # Endpoints en échec : un seul avertissement à l'entrée, une info au retour.
        self._failing: set[str] = set()
        # Couleurs officielles déjà vues (hier et aujourd'hui), pour la journée
        # Tempo qui court jusqu'à 6 h le lendemain.
        self._official_colors: dict[date, str] = {}
        # Prix du kWh (champ `tarif`) de ces mêmes jours, quand l'API l'a donné.
        self._official_tarifs: dict[date, Tariff] = {}
        self._short_retry_done = False
        # Dernière grille de prix reçue : gardée 24 h au plus si /api/today répond
        # sans elle (couleur en attente, source EDF indisponible).
        self._last_tarifs: tuple[TariffGrid, datetime] | None = None

    def _plan_next(self, complete: bool) -> None:
        """Cycle normal si tout va bien, sinon une relance unique à 5 minutes."""
        if complete or self._short_retry_done:
            self.update_interval = SCAN_INTERVAL
            self._short_retry_done = not complete
        else:
            self.update_interval = RETRY_INTERVAL
            self._short_retry_done = True

    async def _async_optional(self, endpoint: str, missing: list[str]) -> Any:
        """Endpoint facultatif : dernière réponse valide (24 h au plus) si l'appel échoue."""
        now = dt_util.utcnow()
        try:
            payload = await self.client.async_get(endpoint)
        except TempoApiError as err:
            missing.append(endpoint)
            if endpoint not in self._failing:
                self._failing.add(endpoint)
                _LOGGER.warning("%s, dernière réponse valide conservée 24 h au plus", err)
            last = self._last_payloads.get(endpoint)
            if last is None or now - last[1] > STALE_PAYLOAD_MAX_AGE:
                return {}
            return last[0]
        if endpoint in self._failing:
            self._failing.discard(endpoint)
            _LOGGER.info("/api/%s de nouveau disponible", endpoint)
        self._last_payloads[endpoint] = (payload, now)
        return payload

    async def _async_yesterday(self, yesterday: date) -> None:
        """Couleur d'hier, utile seulement entre 0 h et 6 h si elle n'a pas été vue."""
        try:
            colors = parse_history(await self.client.async_get(ENDPOINT_HISTORY))
        except (TempoApiError, ApiDataError) as err:
            _LOGGER.debug("Couleur de la veille indisponible : %s", err)
            return
        if yesterday in colors:
            self._official_colors[yesterday] = colors[yesterday]

    def _with_known_color(self, day: DayColor) -> DayColor:
        """Une réponse sans couleur (attente, source EDF indisponible) n'efface
        jamais une couleur officielle déjà lue pour cette date (recette 2026-10-17,
        point 3.12 ; même règle que withKnownColor de l'intégration Gladys).

        La date vient du calcul local (date de Paris), jamais de la réponse : une
        réponse « unavailable » n'a pas de date et son `code` 0 n'est pas une couleur.
        """
        if day.color is not None or day.date is None:
            return day
        known = self._official_colors.get(day.date)
        if known is None:
            return day
        return DayColor(
            date=day.date,
            color=known,
            code=COLORS.index(known) + 1,
            tarif=self._official_tarifs.get(day.date),
        )

    async def _async_update_data(self) -> TempoData:
        # Requêtes séquentielles : 4 appels toutes les 30 minutes, l'API reste ménagée.
        now = dt_util.now(PARIS_TZ)
        missing: list[str] = []
        try:
            today = await self.client.async_get(ENDPOINT_TODAY)
            tomorrow = await self.client.async_get(ENDPOINT_TOMORROW)
        except TempoApiError as err:
            self._plan_next(complete=False)
            raise UpdateFailed(f"API calendrier-tempo.fr injoignable : {err}") from err
        remaining = await self._async_optional(ENDPOINT_REMAINING, missing)
        predictions = await self._async_optional(ENDPOINT_PREDICTIONS, missing)
        try:
            data = build_tempo_data(today, tomorrow, remaining, predictions, now.date())
        except ApiDataError as err:
            self._plan_next(complete=False)
            raise UpdateFailed(str(err)) from err

        known_today = self._with_known_color(data.today)
        known_tomorrow = self._with_known_color(data.tomorrow)
        if (known_today, known_tomorrow) != (data.today, data.tomorrow):
            data = replace(
                data,
                today=known_today,
                tomorrow=known_tomorrow,
                days=build_forecast_days(
                    data.predictions, known_today, known_tomorrow, data.reference_date
                ),
            )

        yesterday = now.date() - timedelta(days=1)
        for day in (data.yesterday, data.today, data.tomorrow):
            if day.date is not None and day.color is not None:
                self._official_colors[day.date] = day.color
                if day.tarif is not None:
                    self._official_tarifs[day.date] = day.tarif
        if now.hour < TEMPO_DAY_START_HOUR and yesterday not in self._official_colors:
            await self._async_yesterday(yesterday)
        self._official_colors = {
            d: c for d, c in self._official_colors.items() if d >= yesterday
        }
        self._official_tarifs = {
            d: t
            for d, t in self._official_tarifs.items()
            if d >= yesterday and d in self._official_colors
        }
        tarifs = data.tarifs
        utc_now = dt_util.utcnow()
        if tarifs is not None:
            self._last_tarifs = (tarifs, utc_now)
        elif self._last_tarifs and utc_now - self._last_tarifs[1] <= STALE_PAYLOAD_MAX_AGE:
            tarifs = self._last_tarifs[0]
        if data.stale:
            _LOGGER.info("Réponse de la veille reçue (cache), nouvelle lecture dans 5 minutes")
        self._plan_next(complete=not missing and not data.stale)
        return replace(
            data,
            yesterday=DayColor(date=yesterday, color=self._official_colors.get(yesterday)),
            tarifs=tarifs,
        )
