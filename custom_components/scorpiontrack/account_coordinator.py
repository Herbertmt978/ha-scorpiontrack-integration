"""Coordinator for ScorpionTrack Account."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .account_api import (
    ScorpionTrackAccountClient,
    ScorpionTrackAccountData,
    ScorpionTrackAuthError,
    ScorpionTrackConnectionError,
    ScorpionTrackPortalError,
)
from .const import ACCOUNT_SCAN_INTERVAL, DOMAIN
from .utils import stable_hash

_LOGGER = logging.getLogger(__name__)


class ScorpionTrackAccountCoordinator(DataUpdateCoordinator[ScorpionTrackAccountData]):
    """Coordinate authenticated ScorpionTrack account updates."""

    def __init__(self, hass: HomeAssistant, client: ScorpionTrackAccountClient) -> None:
        """Initialize the coordinator."""
        self.client = client
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_account_{stable_hash(client.email, length=8)}",
            update_interval=ACCOUNT_SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> ScorpionTrackAccountData:
        """Fetch updated account data."""
        try:
            return await self.client.async_refresh_account()
        except ScorpionTrackConnectionError as err:
            raise UpdateFailed(f"Could not reach the ScorpionTrack portal: {err}") from err
        except ScorpionTrackAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except ScorpionTrackPortalError as err:
            raise UpdateFailed(f"Unexpected portal response: {err}") from err
