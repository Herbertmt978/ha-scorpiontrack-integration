"""Shared entity helpers for ScorpionTrack Account."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .account_api import (
    ScorpionTrackAccountData,
    ScorpionTrackVehiclePosition,
    ScorpionTrackVehicleSummary,
)
from .const import DOMAIN, MANUFACTURER
from .account_coordinator import ScorpionTrackAccountCoordinator
from .utils import stable_hash

_STALE_AFTER = timedelta(hours=24)


class ScorpionTrackCoordinatorEntity(CoordinatorEntity[ScorpionTrackAccountCoordinator]):
    """Base class for entities backed by the account coordinator."""

    @property
    def account(self) -> ScorpionTrackAccountData:
        """Return the latest account snapshot."""
        return self.coordinator.data

    @property
    def account_identifier(self) -> str:
        """Return a stable account identifier for device registry use."""
        if self.account.user_id is not None:
            return str(self.account.user_id)
        return f"acct_{stable_hash(self.account.email)}"


class ScorpionTrackAccountEntity(ScorpionTrackCoordinatorEntity):
    """Base class for account-level entities."""

    def common_account_attributes(self) -> dict[str, Any]:
        """Return shared account attributes."""
        return {
            "user_id": self.account.user_id,
            "distance_units": self.account.distance_units,
            "vehicle_ids": [vehicle.id for vehicle in self.account.vehicles],
            "app_api_key_available": self.account.app_api_key_available,
            "fms_api_available": bool(self.account.fms_api_url),
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return the account device metadata."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"account_{self.account_identifier}")},
            manufacturer=MANUFACTURER,
            model="Portal Account",
            name=self.account.title,
        )


class ScorpionTrackVehicleEntity(ScorpionTrackCoordinatorEntity):
    """Base class for vehicle-level entities."""

    def __init__(self, coordinator: ScorpionTrackAccountCoordinator, vehicle_id: int) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._vehicle_id = vehicle_id

    def get_vehicle(self) -> ScorpionTrackVehicleSummary | None:
        """Return the matching vehicle, if present."""
        for vehicle in self.account.vehicles:
            if vehicle.id == self._vehicle_id:
                return vehicle
        return None

    @property
    def vehicle(self) -> ScorpionTrackVehicleSummary:
        """Return the matching vehicle."""
        vehicle = self.get_vehicle()
        if vehicle is None:
            raise RuntimeError(f"Vehicle {self._vehicle_id} is no longer present in the account")
        return vehicle

    @property
    def position(self) -> ScorpionTrackVehiclePosition | None:
        """Return the best-known vehicle position."""
        return self.vehicle.position

    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        return super().available and self.get_vehicle() is not None

    @property
    def location_is_stale(self) -> bool:
        """Return True when the current location is stale."""
        if self.position is None or self.position.timestamp is None:
            return True
        return datetime.now(UTC) - self.position.timestamp > _STALE_AFTER

    def format_location(self) -> str | None:
        """Return a human-friendly location string."""
        if self.position is None:
            return None
        if self.position.address:
            return self.position.address
        if self.position.latitude is None or self.position.longitude is None:
            return None
        return f"{self.position.latitude:.6f}, {self.position.longitude:.6f}"

    def common_position_attributes(self) -> dict[str, Any]:
        """Return shared position attributes."""
        if self.position is None:
            return {}
        return {
            "latitude": self.position.latitude,
            "longitude": self.position.longitude,
            "position_timestamp": self.position.timestamp,
            "speed_kmh": self.position.speed_kmh,
            "heading": self.position.bearing,
            "accuracy": self.position.accuracy,
            "address": self.position.address,
            "ignition": self.position.ignition,
            "engine": self.position.engine,
            "gps_satellites": self.position.gps_satellites,
            "gps_hdop": self.position.hdop,
            "vehicle_voltage": self.position.vehicle_voltage,
            "position_odometer": self.position.odometer,
            "position_state": self.position.raw_state,
        }

    def common_vehicle_attributes(self) -> dict[str, Any]:
        """Return shared vehicle attributes."""
        vehicle = self.vehicle
        attributes = {
            "portal_vehicle_id": vehicle.id,
            "registration": vehicle.registration,
            "alias": vehicle.alias,
            "description": vehicle.description,
            "make": vehicle.make,
            "model": vehicle.model,
            "vehicle_type": vehicle.vehicle_type,
            "colour": vehicle.colour,
            "fuel_type": vehicle.fuel_type,
            "status": vehicle.status,
            "portal_state": vehicle.raw_state,
            "odometer": vehicle.odometer,
            "groups": list(vehicle.group_names),
            "last_service_date": vehicle.last_service_date,
            "battery_type": vehicle.battery_type,
            "vehicle_voltage": vehicle.vehicle_voltage,
            "backup_battery_voltage": vehicle.backup_battery_voltage,
            "gps_antenna_voltage": vehicle.gps_antenna_voltage,
            "gps_antenna_current": vehicle.gps_antenna_current,
            "privacy_mode_enabled": vehicle.privacy_mode_enabled,
            "zero_speed_mode_enabled": vehicle.zero_speed_mode_enabled,
            "armed_mode_enabled": vehicle.armed_mode_enabled,
            "transport_mode_active": vehicle.transport_mode_active,
            "garage_mode_active": vehicle.garage_mode_active,
            "no_alert_mode_active": vehicle.no_alert_mode_active,
            "ewm_enabled": vehicle.ewm_enabled,
            "driver_module": vehicle.driver_module,
            "g_sense_enabled": vehicle.g_sense_enabled,
            "immobiliser_fitted": vehicle.immobiliser_fitted,
            "install_complete": vehicle.install_complete,
            "pending_commands_count": vehicle.pending_commands_count,
            "unit_type": vehicle.unit_type,
            "unit_model": vehicle.unit_model,
            "unit_make": vehicle.unit_make,
            "installed_at": vehicle.installed_at,
            "updated_at": vehicle.updated_at,
            "distance_units": self.account.distance_units,
        }
        attributes.update(self.common_position_attributes())
        return attributes

    @property
    def device_info(self) -> DeviceInfo:
        """Return the vehicle device metadata."""
        vehicle = self.vehicle
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.account_identifier}_vehicle_{vehicle.id}")},
            via_device=(DOMAIN, f"account_{self.account_identifier}"),
            manufacturer=vehicle.make or MANUFACTURER,
            model=vehicle.model or vehicle.unit_model or vehicle.vehicle_type or "Vehicle",
            name=vehicle.display_name,
        )
