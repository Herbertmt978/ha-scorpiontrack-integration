"""Sensor platform for ScorpionTrack Share."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfSpeed
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .share_api import ScorpionTrackShare, ScorpionTrackVehicle
from .const import DOMAIN
from .share_entity import ScorpionTrackEntity, ScorpionTrackShareEntity


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackSensorDescription(SensorEntityDescription):
    """Describes a ScorpionTrack sensor."""

    value_fn: Callable[[ScorpionTrackShare, ScorpionTrackVehicle], object]
    unit_fn: Callable[[ScorpionTrackShare], str | None] | None = None


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackShareSensorDescription(SensorEntityDescription):
    """Describes a ScorpionTrack share-level sensor."""

    value_fn: Callable[[ScorpionTrackShare], object]


SENSOR_DESCRIPTIONS: tuple[ScorpionTrackSensorDescription, ...] = (
    ScorpionTrackSensorDescription(
        key="status",
        name="Status",
        icon="mdi:car-info",
        value_fn=lambda share, vehicle: vehicle.status,
    ),
    ScorpionTrackSensorDescription(
        key="location",
        name="Location",
        icon="mdi:map-marker",
        value_fn=lambda share, vehicle: _format_location(vehicle),
    ),
    ScorpionTrackSensorDescription(
        key="speed",
        name="Speed",
        device_class=SensorDeviceClass.SPEED,
        icon="mdi:speedometer",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda share, vehicle: share.convert_speed(vehicle.position.speed_kmh),
        unit_fn=lambda share: (
            UnitOfSpeed.MILES_PER_HOUR
            if share.uses_miles
            else UnitOfSpeed.KILOMETERS_PER_HOUR
        ),
    ),
    ScorpionTrackSensorDescription(
        key="heading",
        name="Heading",
        icon="mdi:compass",
        suggested_display_precision=0,
        native_unit_of_measurement="deg",
        value_fn=lambda share, vehicle: (
            round(vehicle.position.bearing)
            if vehicle.position.bearing is not None
            else None
        ),
    ),
    ScorpionTrackSensorDescription(
        key="last_reported",
        name="Last Reported",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-outline",
        value_fn=lambda share, vehicle: vehicle.position.timestamp,
    ),
    ScorpionTrackSensorDescription(
        key="share_expires",
        name="Share Expires",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar-clock",
        value_fn=lambda share, vehicle: share.expires_at,
    ),
)

SHARE_SENSOR_DESCRIPTIONS: tuple[ScorpionTrackShareSensorDescription, ...] = (
    ScorpionTrackShareSensorDescription(
        key="share_title",
        name="Share Title",
        icon="mdi:share-variant",
        value_fn=lambda share: share.title,
    ),
    ScorpionTrackShareSensorDescription(
        key="shared_by",
        name="Shared By",
        icon="mdi:account",
        value_fn=lambda share: share.owner_name,
    ),
    ScorpionTrackShareSensorDescription(
        key="share_created",
        name="Share Created",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar-plus",
        value_fn=lambda share: share.created_at,
    ),
    ScorpionTrackShareSensorDescription(
        key="share_expires",
        name="Share Expires",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar-clock",
        value_fn=lambda share: share.expires_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ScorpionTrack sensor entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    known_vehicle_ids: set[int] = set()
    share_entities_added = False

    @callback
    def _async_add_missing_entities() -> None:
        nonlocal share_entities_added
        entities: list[SensorEntity] = []

        if not share_entities_added:
            entities.extend(
                ScorpionTrackShareSensorEntity(coordinator, description)
                for description in SHARE_SENSOR_DESCRIPTIONS
            )
            share_entities_added = True

        new_vehicle_ids = [
            vehicle.id
            for vehicle in coordinator.data.vehicles
            if vehicle.id not in known_vehicle_ids
        ]
        if new_vehicle_ids:
            known_vehicle_ids.update(new_vehicle_ids)
            entities.extend(
                ScorpionTrackSensorEntity(coordinator, vehicle_id, description)
                for vehicle_id in new_vehicle_ids
                for description in SENSOR_DESCRIPTIONS
            )

        if entities:
            async_add_entities(entities)

    _async_add_missing_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_missing_entities))


class ScorpionTrackSensorEntity(ScorpionTrackEntity, SensorEntity):
    """Represent a ScorpionTrack sensor."""

    _attr_has_entity_name = True

    entity_description: ScorpionTrackSensorDescription

    def __init__(
        self,
        coordinator,
        vehicle_id: int,
        description: ScorpionTrackSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, vehicle_id)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.data.id}_{vehicle_id}_{description.key}"
        self._attr_name = description.name

    @property
    def native_value(self) -> object:
        """Return the native sensor value."""
        return self.entity_description.value_fn(self.share, self.vehicle)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit of measurement."""
        if self.entity_description.unit_fn is None:
            return None
        return self.entity_description.unit_fn(self.share)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return extra state attributes."""
        attributes = self.common_location_attributes()
        attributes["distance_units"] = self.share.distance_units
        if self.entity_description.key == "location":
            attributes["formatted_location"] = _format_location(self.vehicle)
            attributes["coordinates"] = _format_coordinates(self.vehicle)
        return attributes


class ScorpionTrackShareSensorEntity(ScorpionTrackShareEntity, SensorEntity):
    """Represent a share-level ScorpionTrack sensor."""

    _attr_has_entity_name = True

    entity_description: ScorpionTrackShareSensorDescription

    def __init__(self, coordinator, description: ScorpionTrackShareSensorDescription) -> None:
        """Initialize the share sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.data.id}_share_{description.key}"
        self._attr_name = description.name

    @property
    def native_value(self) -> object:
        """Return the native sensor value."""
        return self.entity_description.value_fn(self.share)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return extra state attributes."""
        return self.share_common_attributes()


def _format_location(vehicle: ScorpionTrackVehicle) -> str | None:
    """Return a human-friendly location string."""
    if vehicle.position.address:
        return vehicle.position.address

    if (
        vehicle.position.latitude is not None
        and vehicle.position.longitude is not None
    ):
        return f"{vehicle.position.latitude:.6f}, {vehicle.position.longitude:.6f}"

    return None


def _format_coordinates(vehicle: ScorpionTrackVehicle) -> str | None:
    """Return raw coordinates in a compact string form."""
    if (
        vehicle.position.latitude is None
        or vehicle.position.longitude is None
    ):
        return None
    return f"{vehicle.position.latitude:.6f}, {vehicle.position.longitude:.6f}"
