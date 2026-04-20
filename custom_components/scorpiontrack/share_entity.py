"""Shared entity helpers for ScorpionTrack Share."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MANUFACTURER, SHARE_DEFAULT_NAME, STALE_POSITION_THRESHOLD
from .share_api import ScorpionTrackShare, ScorpionTrackVehicle
from .share_coordinator import ScorpionTrackShareCoordinator


class ScorpionTrackEntity(CoordinatorEntity[ScorpionTrackShareCoordinator]):
    """Base class for ScorpionTrack entities."""

    def __init__(self, coordinator: ScorpionTrackShareCoordinator, vehicle_id: int) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._vehicle_id = vehicle_id

    @property
    def share(self) -> ScorpionTrackShare:
        """Return the active share data."""
        return self.coordinator.data

    def get_vehicle(self) -> ScorpionTrackVehicle | None:
        """Return the matching vehicle, if present."""
        for vehicle in self.share.vehicles:
            if vehicle.id == self._vehicle_id:
                return vehicle
        return None

    @property
    def vehicle(self) -> ScorpionTrackVehicle:
        """Return the matching vehicle."""
        vehicle = self.get_vehicle()
        if vehicle is None:
            raise RuntimeError(f"Vehicle {self._vehicle_id} is no longer present in the share")
        return vehicle

    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        return super().available and self.get_vehicle() is not None

    def position_age(self) -> timedelta | None:
        """Return the age of the latest reported position."""
        timestamp = self.vehicle.position.timestamp
        if timestamp is None:
            return None

        age = dt_util.utcnow() - timestamp
        if age.total_seconds() < 0:
            return timedelta(seconds=0)
        return age

    def position_is_stale(self) -> bool:
        """Return True if the latest reported position is stale."""
        age = self.position_age()
        return age is None or age >= STALE_POSITION_THRESHOLD

    def common_location_attributes(
        self,
        *,
        include_coordinates: bool = False,
    ) -> dict[str, Any]:
        """Return shared location-related attributes."""
        vehicle = self.vehicle
        position = vehicle.position
        age = self.position_age()
        age_seconds = max(0, int(age.total_seconds())) if age is not None else None

        attributes = {
            "registration": vehicle.registration,
            "make": vehicle.make,
            "model": vehicle.model,
            "status": vehicle.status,
            "bearing": position.bearing,
            "heading_cardinal": _bearing_to_cardinal(position.bearing),
            "address": position.address,
            "ignition": position.ignition,
            "last_reported": position.timestamp.isoformat() if position.timestamp else None,
            "last_reported_age_seconds": age_seconds,
            "stale": self.position_is_stale(),
            "stale_after_hours": int(STALE_POSITION_THRESHOLD.total_seconds() // 3600),
            "share_title": self.share.title,
            "shared_by": self.share.owner_name,
            "share_expires": self.share.expires_at.isoformat() if self.share.expires_at else None,
        }
        if include_coordinates:
            attributes["latitude"] = position.latitude
            attributes["longitude"] = position.longitude
        return attributes

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device metadata for the vehicle."""
        vehicle = self.vehicle
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.share.id}_{vehicle.id}")},
            manufacturer=vehicle.make or MANUFACTURER,
            model=vehicle.model,
            name=vehicle.display_name,
        )


class ScorpionTrackShareEntity(CoordinatorEntity[ScorpionTrackShareCoordinator]):
    """Base class for share-level entities."""

    @property
    def share(self) -> ScorpionTrackShare:
        """Return the active share data."""
        return self.coordinator.data

    def share_common_attributes(self) -> dict[str, Any]:
        """Return shared share-level attributes."""
        return {
            "share_id": self.share.id,
            "share_title": self.share.title,
            "shared_by": self.share.owner_name,
            "distance_units": self.share.distance_units,
            "vehicle_count": len(self.share.vehicles),
            "created_at": self.share.created_at.isoformat() if self.share.created_at else None,
            "share_expires": self.share.expires_at.isoformat() if self.share.expires_at else None,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device metadata for the share."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"share_{self.share.id}")},
            manufacturer=MANUFACTURER,
            model="Location Share",
            name=self.share.title or SHARE_DEFAULT_NAME,
        )


def _bearing_to_cardinal(bearing: float | None) -> str | None:
    """Convert a numeric bearing into a cardinal heading."""
    if bearing is None:
        return None

    directions = (
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    )
    index = int((bearing % 360) / 22.5 + 0.5) % len(directions)
    return directions[index]
