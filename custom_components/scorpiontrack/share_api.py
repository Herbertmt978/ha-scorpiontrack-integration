"""API client for ScorpionTrack shared locations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from aiohttp import ClientError, ClientSession

from .const import API_BASE_URL
from .utils import mask_token

_LOGGER = logging.getLogger(__name__)


class ScorpionTrackError(Exception):
    """Base exception for ScorpionTrack errors."""


class ScorpionTrackConnectionError(ScorpionTrackError):
    """Raised when the API cannot be reached."""


class ScorpionTrackInvalidTokenError(ScorpionTrackError):
    """Raised when the provided share token is invalid."""


class ScorpionTrackShareUnavailableError(ScorpionTrackError):
    """Raised when the share has expired, been revoked, or has no data."""


@dataclass(slots=True, frozen=True)
class ScorpionTrackPosition:
    """The latest known position for a vehicle."""

    latitude: float | None
    longitude: float | None
    timestamp: datetime | None
    speed_kmh: float | None
    ignition: bool | None
    bearing: float | None
    address: str | None


@dataclass(slots=True, frozen=True)
class ScorpionTrackVehicle:
    """A shared ScorpionTrack vehicle."""

    id: int
    name: str | None
    registration: str | None
    make: str | None
    model: str | None
    position: ScorpionTrackPosition
    status: str

    @property
    def display_name(self) -> str:
        """Return the best user-facing name for the vehicle."""
        return self.registration or self.name or f"Vehicle {self.id}"


@dataclass(slots=True, frozen=True)
class ScorpionTrackShare:
    """A shared location bundle."""

    id: int
    token: str
    title: str | None
    owner_name: str | None
    distance_units: str
    created_at: datetime | None
    expires_at: datetime | None
    vehicles: tuple[ScorpionTrackVehicle, ...]

    @property
    def uses_miles(self) -> bool:
        """Return True if the share prefers imperial distance units."""
        return self.distance_units.lower() == "miles"

    def convert_speed(self, speed_kmh: float | None) -> float | None:
        """Convert API speed to the share's preferred unit."""
        if speed_kmh is None:
            return None
        if self.uses_miles:
            return round(speed_kmh * 0.621371, 1)
        return round(speed_kmh, 1)


class ScorpionTrackClient:
    """Minimal client for the shared-location endpoint."""

    def __init__(
        self,
        session: ClientSession,
        token: str,
        *,
        base_url: str = API_BASE_URL,
        timeout_seconds: int = 10,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._token = self.extract_token(token)
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    @property
    def token(self) -> str:
        """Return the canonical share token."""
        return self._token

    @staticmethod
    def extract_token(value: str) -> str:
        """Extract a ScorpionTrack token from a raw token or shared URL."""
        cleaned = value.strip()
        if not cleaned:
            _LOGGER.warning("ScorpionTrack share setup was attempted without a token")
            raise ScorpionTrackInvalidTokenError("No share token supplied")

        if "://" not in cleaned:
            return cleaned

        parsed = urlparse(cleaned)
        token = parse_qs(parsed.query).get("token", [None])[0]
        if not token:
            _LOGGER.warning(
                "ScorpionTrack shared URL did not contain a token parameter (path=%s)",
                parsed.path,
            )
            raise ScorpionTrackInvalidTokenError(
                "Shared URL does not contain a token parameter"
            )

        return token.strip()

    async def async_get_share(self) -> ScorpionTrackShare:
        """Fetch the latest shared-location payload."""
        url = f"{self._base_url}/location-shares/{quote(self._token, safe='')}/view"
        _LOGGER.debug(
            "Fetching ScorpionTrack shared location for token %s",
            mask_token(self._token),
        )

        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._session.get(url) as response:
                    if response.status in (401, 403):
                        _LOGGER.warning(
                            "ScorpionTrack rejected shared-location token %s with HTTP %s",
                            mask_token(self._token),
                            response.status,
                        )
                        raise ScorpionTrackInvalidTokenError("Share token was rejected")
                    if response.status == 404:
                        _LOGGER.warning(
                            "ScorpionTrack shared-location token %s no longer resolves (HTTP 404)",
                            mask_token(self._token),
                        )
                        raise ScorpionTrackShareUnavailableError(
                            "Shared location was not found"
                        )
                    if response.status >= 400:
                        _LOGGER.warning(
                            "ScorpionTrack shared-location token %s returned unexpected HTTP %s",
                            mask_token(self._token),
                            response.status,
                        )
                        raise ScorpionTrackConnectionError(
                            f"Unexpected HTTP status {response.status}"
                        )

                    payload = await response.json(content_type=None)
        except TimeoutError as err:
            _LOGGER.warning(
                "Timed out contacting ScorpionTrack for shared-location token %s",
                mask_token(self._token),
            )
            raise ScorpionTrackConnectionError("Timed out contacting ScorpionTrack") from err
        except ClientError as err:
            _LOGGER.warning(
                "Error contacting ScorpionTrack for shared-location token %s: %s",
                mask_token(self._token),
                err,
            )
            raise ScorpionTrackConnectionError("Failed to contact ScorpionTrack") from err
        except ValueError as err:
            _LOGGER.warning(
                "ScorpionTrack returned invalid JSON for shared-location token %s",
                mask_token(self._token),
            )
            raise ScorpionTrackConnectionError("ScorpionTrack returned invalid JSON") from err

        try:
            share = self._parse_share(payload)
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.warning(
                "ScorpionTrack returned malformed shared-location data for token %s: %s",
                mask_token(self._token),
                err,
            )
            raise ScorpionTrackShareUnavailableError(
                "Shared location returned malformed data"
            ) from err

        _LOGGER.debug(
            "Fetched ScorpionTrack shared location %s for token %s with %s vehicle(s)",
            share.id,
            mask_token(self._token),
            len(share.vehicles),
        )
        return share

    def _parse_share(self, payload: dict[str, Any]) -> ScorpionTrackShare:
        """Convert the API payload into structured data."""
        share_data = payload.get("data")
        if not isinstance(share_data, dict):
            _LOGGER.warning(
                "ScorpionTrack shared-location token %s returned no active share payload",
                mask_token(self._token),
            )
            raise ScorpionTrackShareUnavailableError(
                "Shared location is expired, revoked, or empty"
            )

        user = share_data.get("user") or {}
        owner_name = " ".join(
            part for part in (user.get("first_name"), user.get("last_name")) if part
        ) or None

        vehicles = tuple(
            self._parse_vehicle(vehicle_data)
            for vehicle_data in share_data.get("vehicles", [])
            if isinstance(vehicle_data, dict)
        )

        return ScorpionTrackShare(
            id=int(share_data["id"]),
            token=str(share_data.get("token") or self._token),
            title=share_data.get("title"),
            owner_name=owner_name,
            distance_units=str(user.get("distance_units") or "km"),
            created_at=_parse_datetime(share_data.get("created_at")),
            # The live-share frontend appends "Z" to this field, so we mirror it.
            expires_at=_parse_datetime(share_data.get("expires_at"), assume_utc=True),
            vehicles=vehicles,
        )

    def _parse_vehicle(self, vehicle_data: dict[str, Any]) -> ScorpionTrackVehicle:
        """Parse a shared vehicle."""
        latest_position = vehicle_data.get("latest_position") or {}
        position = ScorpionTrackPosition(
            latitude=_to_float(latest_position.get("lat")),
            longitude=_to_float(latest_position.get("lng")),
            timestamp=_parse_datetime(latest_position.get("timestamp")),
            speed_kmh=_to_float(latest_position.get("speed")),
            ignition=_to_bool(latest_position.get("ignition")),
            bearing=_to_float(latest_position.get("bearing")),
            address=_clean_text(latest_position.get("address")),
        )

        status = "unknown"
        if position.speed_kmh is not None and position.speed_kmh > 0:
            status = "moving"
        elif position.ignition is True:
            status = "idle"
        elif latest_position:
            status = "parked"

        return ScorpionTrackVehicle(
            id=int(vehicle_data["id"]),
            name=_clean_text(vehicle_data.get("name")),
            registration=_clean_text(vehicle_data.get("registration")),
            make=_clean_text(vehicle_data.get("make")),
            model=_clean_text(vehicle_data.get("model")),
            position=position,
            status=status,
        )


def _clean_text(value: Any) -> str | None:
    """Normalize text values."""
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _to_float(value: Any) -> float | None:
    """Convert a value to float when possible."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool | None:
    """Convert a value to bool when possible."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return None


def _parse_datetime(value: Any, *, assume_utc: bool = False) -> datetime | None:
    """Parse an ISO-style datetime from the API."""
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    if assume_utc and "Z" not in text and "+" not in text:
        text = f"{text}Z"

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
