"""Button platform for ScorpionTrack."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import account_button
from .const import DOMAIN, SETUP_TYPE_ACCOUNT


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ScorpionTrack buttons for the configured entry type."""
    entry_state = hass.data[DOMAIN][entry.entry_id]
    if entry_state["type"] == SETUP_TYPE_ACCOUNT:
        await account_button.async_setup_entry(hass, entry, async_add_entities)
