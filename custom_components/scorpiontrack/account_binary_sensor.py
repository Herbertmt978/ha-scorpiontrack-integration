"""Binary sensor platform for ScorpionTrack Account."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .account_api import ScorpionTrackAccountData, ScorpionTrackVehicleSummary
from .const import DOMAIN
from .account_entity import ScorpionTrackVehicleEntity


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackVehicleBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a vehicle-level binary sensor."""

    value_fn: Callable[[ScorpionTrackAccountData, ScorpionTrackVehicleSummary], bool | None]


VEHICLE_BINARY_SENSOR_DESCRIPTIONS: tuple[
    ScorpionTrackVehicleBinarySensorDescription, ...
] = (
    ScorpionTrackVehicleBinarySensorDescription(
        key="ignition",
        name="Ignition",
        icon="mdi:key-variant",
        value_fn=lambda account, vehicle: (
            vehicle.position.ignition if vehicle.position else None
        ),
    ),
    ScorpionTrackVehicleBinarySensorDescription(
        key="engine",
        name="Engine",
        icon="mdi:engine",
        value_fn=lambda account, vehicle: (
            bool(vehicle.position.engine) if vehicle.position else None
        ),
    ),
    ScorpionTrackVehicleBinarySensorDescription(
        key="transport_mode_active",
        name="Transport Mode Active",
        icon="mdi:truck-fast",
        value_fn=lambda account, vehicle: vehicle.transport_mode_active,
    ),
    ScorpionTrackVehicleBinarySensorDescription(
        key="garage_mode_active",
        name="Garage Mode Active",
        icon="mdi:garage-variant",
        value_fn=lambda account, vehicle: vehicle.garage_mode_active,
    ),
    ScorpionTrackVehicleBinarySensorDescription(
        key="no_alert_mode_active",
        name="No-Alert Mode Active",
        icon="mdi:bell-off",
        value_fn=lambda account, vehicle: vehicle.no_alert_mode_active,
    ),
    ScorpionTrackVehicleBinarySensorDescription(
        key="ewm_enabled",
        name="EWM Enabled",
        icon="mdi:motion-sensor",
        value_fn=lambda account, vehicle: vehicle.ewm_enabled,
    ),
    ScorpionTrackVehicleBinarySensorDescription(
        key="armed_mode_enabled",
        name="Armed Mode Enabled",
        icon="mdi:shield-car",
        value_fn=lambda account, vehicle: vehicle.armed_mode_enabled,
    ),
    ScorpionTrackVehicleBinarySensorDescription(
        key="driver_module",
        name="Driver Module Fitted",
        icon="mdi:key-chain-variant",
        value_fn=lambda account, vehicle: vehicle.driver_module,
    ),
    ScorpionTrackVehicleBinarySensorDescription(
        key="g_sense_enabled",
        name="G-Sense Enabled",
        icon="mdi:car-emergency",
        value_fn=lambda account, vehicle: vehicle.g_sense_enabled,
    ),
    ScorpionTrackVehicleBinarySensorDescription(
        key="install_complete",
        name="Installation Complete",
        icon="mdi:check-decagram",
        value_fn=lambda account, vehicle: vehicle.install_complete,
    ),
    ScorpionTrackVehicleBinarySensorDescription(
        key="immobiliser_fitted",
        name="Immobiliser Fitted",
        icon="mdi:shield-car",
        value_fn=lambda account, vehicle: vehicle.immobiliser_fitted,
    ),
    ScorpionTrackVehicleBinarySensorDescription(
        key="pending_commands",
        name="Pending Commands",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:progress-clock",
        value_fn=lambda account, vehicle: vehicle.pending_commands_count > 0,
    ),
    ScorpionTrackVehicleBinarySensorDescription(
        key="location_stale",
        name="Location Stale",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:map-marker-alert",
        value_fn=lambda account, vehicle: _is_location_stale(vehicle),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ScorpionTrack vehicle binary sensors."""
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
            ScorpionTrackVehicleBinarySensorEntity(coordinator, vehicle_id, description)
            for vehicle_id in new_vehicle_ids
            for description in VEHICLE_BINARY_SENSOR_DESCRIPTIONS
        )

    _async_add_missing_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_missing_entities))


class ScorpionTrackVehicleBinarySensorEntity(
    ScorpionTrackVehicleEntity,
    BinarySensorEntity,
):
    """Represent a vehicle-level ScorpionTrack binary sensor."""

    _attr_has_entity_name = True

    entity_description: ScorpionTrackVehicleBinarySensorDescription

    def __init__(self, coordinator, vehicle_id: int, description) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, vehicle_id)
        self.entity_description = description
        self._attr_unique_id = f"{self.account_identifier}_{vehicle_id}_{description.key}"
        self._attr_name = description.name

    @property
    def is_on(self) -> bool | None:
        """Return the sensor state."""
        return self.entity_description.value_fn(self.account, self.vehicle)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return extra state attributes."""
        return self.common_vehicle_attributes()


def _is_location_stale(vehicle: ScorpionTrackVehicleSummary) -> bool:
    """Return True when a vehicle position is missing or stale."""
    if vehicle.position is None or vehicle.position.timestamp is None:
        return True

    return datetime.now(UTC) - vehicle.position.timestamp > timedelta(hours=24)
