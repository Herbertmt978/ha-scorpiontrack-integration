"""Device tracker platform for ScorpionTrack Account."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .account_entity import ScorpionTrackVehicleEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ScorpionTrack tracker entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    known_vehicle_ids: set[int] = set()

    @callback
    def _async_add_missing_entities() -> None:
        new_vehicle_ids = [
            vehicle.id
            for vehicle in coordinator.data.vehicles
            if vehicle.id not in known_vehicle_ids
        ]
        if not new_vehicle_ids:
            return

        known_vehicle_ids.update(new_vehicle_ids)
        async_add_entities(
            ScorpionTrackTrackerEntity(coordinator, vehicle_id)
            for vehicle_id in new_vehicle_ids
        )

    _async_add_missing_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_missing_entities))


class ScorpionTrackTrackerEntity(ScorpionTrackVehicleEntity, TrackerEntity):
    """Represent the latest authenticated GPS location for a vehicle."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:car"
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator, vehicle_id: int) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator, vehicle_id)
        self._attr_unique_id = f"{self.account_identifier}_{vehicle_id}_tracker"
        self._attr_name = "Live Location"

    @property
    def available(self) -> bool:
        """Return if the tracker is available."""
        return (
            super().available
            and self.position is not None
            and self.position.latitude is not None
            and self.position.longitude is not None
        )

    @property
    def latitude(self) -> float | None:
        """Return the latitude."""
        return self.position.latitude if self.position else None

    @property
    def longitude(self) -> float | None:
        """Return the longitude."""
        return self.position.longitude if self.position else None

    @property
    def location_accuracy(self) -> float:
        """Return the location accuracy in meters."""
        if self.position is None or self.position.accuracy is None:
            return 0.0
        return float(self.position.accuracy)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attributes = self.common_vehicle_attributes()
        attributes["formatted_location"] = self.format_location()
        return attributes
