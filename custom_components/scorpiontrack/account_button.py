"""Button platform for ScorpionTrack Account."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .account_api import (
    ScorpionTrackAuthError,
    ScorpionTrackConnectionError,
    ScorpionTrackPortalError,
)
from .account_entity import ScorpionTrackAccountEntity
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ScorpionTrack account buttons."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([ScorpionTrackMarkAlertsReadButton(coordinator)])


class ScorpionTrackMarkAlertsReadButton(ScorpionTrackAccountEntity, ButtonEntity):
    """Button entity that marks unread alerts as read."""

    _attr_has_entity_name = True
    _attr_name = "Mark Alerts Read"
    _attr_icon = "mdi:bell-check-outline"

    def __init__(self, coordinator) -> None:
        """Initialize the alert button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.account_identifier}_mark_alerts_read"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return extra state attributes."""
        return self.common_account_attributes()

    async def async_press(self) -> None:
        """Mark unread alerts as read and refresh account data."""
        try:
            await self.coordinator.client.async_mark_all_alerts_read()
        except (
            ScorpionTrackAuthError,
            ScorpionTrackConnectionError,
            ScorpionTrackPortalError,
        ) as err:
            raise HomeAssistantError(
                f"Unable to mark alerts as read: {err}"
            ) from err

        await self.coordinator.async_request_refresh()
