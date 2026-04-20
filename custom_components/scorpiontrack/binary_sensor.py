"""Binary sensor platform for ScorpionTrack."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import account_binary_sensor, share_binary_sensor
from .const import DOMAIN, SETUP_TYPE_ACCOUNT


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ScorpionTrack binary sensors for the configured entry type."""
    entry_state = hass.data[DOMAIN][entry.entry_id]
    if entry_state["type"] == SETUP_TYPE_ACCOUNT:
        await account_binary_sensor.async_setup_entry(hass, entry, async_add_entities)
        return

    await share_binary_sensor.async_setup_entry(hass, entry, async_add_entities)
