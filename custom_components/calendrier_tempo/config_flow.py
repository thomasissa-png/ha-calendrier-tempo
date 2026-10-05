"""Assistant de configuration : aucun paramètre, une seule instance."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, ENDPOINT_TODAY, NAME
from .coordinator import TempoApiClient, TempoApiError


class TempoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ajout de l'intégration depuis l'interface."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape unique : confirmation, puis test de l'API."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            client = TempoApiClient(async_get_clientsession(self.hass))
            try:
                await client.async_get(ENDPOINT_TODAY)
            except TempoApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=NAME, data={})

        return self.async_show_form(step_id="user", errors=errors)
