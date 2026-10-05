"""Coordinateur de mise à jour : interroge l'API calendrier-tempo.fr."""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_BASE_URL,
    DOMAIN,
    ENDPOINT_PREDICTIONS,
    ENDPOINT_REMAINING,
    ENDPOINT_TODAY,
    ENDPOINT_TOMORROW,
    REQUEST_TIMEOUT_SECONDS,
    SCAN_INTERVAL,
    USER_AGENT,
)
from .parsing import ApiDataError, TempoData, build_tempo_data

_LOGGER = logging.getLogger(__name__)

PARIS_TZ = ZoneInfo("Europe/Paris")

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
    """Lit les 4 endpoints publics toutes les 30 minutes."""

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

    async def _async_update_data(self) -> TempoData:
        # Requêtes séquentielles : 4 appels toutes les 30 minutes, l'API reste ménagée.
        try:
            today = await self.client.async_get(ENDPOINT_TODAY)
            tomorrow = await self.client.async_get(ENDPOINT_TOMORROW)
            remaining = await self.client.async_get(ENDPOINT_REMAINING)
            predictions = await self.client.async_get(ENDPOINT_PREDICTIONS)
        except TempoApiError as err:
            raise UpdateFailed(f"API calendrier-tempo.fr injoignable : {err}") from err
        try:
            return build_tempo_data(
                today,
                tomorrow,
                remaining,
                predictions,
                fallback_date=datetime.now(PARIS_TZ).date(),
            )
        except ApiDataError as err:
            raise UpdateFailed(str(err)) from err
