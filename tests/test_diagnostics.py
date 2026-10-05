"""Tests des diagnostics."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.calendrier_tempo.const import DOMAIN, NAME, VERSION


async def test_diagnostics(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, mock_api: Any
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, title=NAME)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    assert result["version"] == VERSION
    assert result["derniere_mise_a_jour_reussie"] is True
    assert result["date_reference"] == "2026-12-07"
    assert result["aujourd_hui"] == {"date": "2026-12-07", "couleur": "blanc", "code": 2}
    assert result["jours_restants"] == {"rouge": 18, "blanc": 35, "source": "calcul"}
    assert len(result["previsions"]) == 16
