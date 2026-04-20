"""Coordinator for ScorpionTrack Share."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .share_api import (
    ScorpionTrackClient,
    ScorpionTrackConnectionError,
    ScorpionTrackInvalidTokenError,
    ScorpionTrackShare,
    ScorpionTrackShareUnavailableError,
)
from .const import DOMAIN, SHARE_SCAN_INTERVAL
from .utils import stable_hash

_LOGGER = logging.getLogger(__name__)


class ScorpionTrackShareCoordinator(DataUpdateCoordinator[ScorpionTrackShare]):
    """Coordinate shared-location updates."""

    def __init__(self, hass: HomeAssistant, client: ScorpionTrackClient) -> None:
        """Initialize the coordinator."""
        self.client = client
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_share_{stable_hash(client.token, length=8)}",
            update_interval=SHARE_SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> ScorpionTrackShare:
        """Fetch updated share data."""
        try:
            return await self.client.async_get_share()
        except ScorpionTrackConnectionError as err:
            raise UpdateFailed(f"Could not reach ScorpionTrack: {err}") from err
        except ScorpionTrackInvalidTokenError as err:
            raise UpdateFailed(f"ScorpionTrack rejected the configured token: {err}") from err
        except ScorpionTrackShareUnavailableError as err:
            raise UpdateFailed(f"Shared location is unavailable: {err}") from err
