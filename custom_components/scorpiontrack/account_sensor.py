"""Sensor platform for ScorpionTrack Account."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfSpeed,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .account_api import (
    ScorpionTrackAccountData,
    ScorpionTrackVehicleSummary,
)
from .const import DOMAIN
from .account_entity import ScorpionTrackAccountEntity, ScorpionTrackVehicleEntity


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackAccountSensorDescription(SensorEntityDescription):
    """Describe an account-level sensor."""

    value_fn: Callable[[ScorpionTrackAccountData], object]


@dataclass(frozen=True, kw_only=True)
class ScorpionTrackVehicleSensorDescription(SensorEntityDescription):
    """Describe a vehicle-level sensor."""

    value_fn: Callable[[ScorpionTrackAccountData, ScorpionTrackVehicleSummary], object]
    unit_fn: Callable[[ScorpionTrackAccountData, ScorpionTrackVehicleSummary], str | None] | None = None


ACCOUNT_SENSOR_DESCRIPTIONS: tuple[ScorpionTrackAccountSensorDescription, ...] = (
    ScorpionTrackAccountSensorDescription(
        key="vehicle_count",
        name="Vehicle Count",
        icon="mdi:car-multiple",
        value_fn=lambda account: len(account.vehicles),
    ),
    ScorpionTrackAccountSensorDescription(
        key="unread_alerts",
        name="Unread Alerts",
        icon="mdi:bell-badge",
        value_fn=lambda account: account.unread_alerts,
    ),
    ScorpionTrackAccountSensorDescription(
        key="latest_alert",
        name="Latest Alert",
        icon="mdi:alert-circle-outline",
        value_fn=lambda account: (
            account.latest_alert.summary if account.latest_alert is not None else None
        ),
    ),
    ScorpionTrackAccountSensorDescription(
        key="latest_alert_time",
        name="Latest Alert Time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-alert-outline",
        value_fn=lambda account: (
            account.latest_alert.timestamp if account.latest_alert is not None else None
        ),
    ),
    ScorpionTrackAccountSensorDescription(
        key="last_refreshed",
        name="Last Refreshed",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-outline",
        value_fn=lambda account: account.fetched_at,
    ),
    ScorpionTrackAccountSensorDescription(
        key="user_id",
        name="User ID",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:identifier",
        value_fn=lambda account: account.user_id,
    ),
)

VEHICLE_SENSOR_DESCRIPTIONS: tuple[ScorpionTrackVehicleSensorDescription, ...] = (
    ScorpionTrackVehicleSensorDescription(
        key="status",
        name="Status",
        icon="mdi:car-info",
        value_fn=lambda account, vehicle: vehicle.status,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="portal_state",
        name="Portal State",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:code-braces",
        value_fn=lambda account, vehicle: vehicle.raw_state,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="location",
        name="Location",
        icon="mdi:map-marker",
        value_fn=lambda account, vehicle: _format_location(vehicle),
    ),
    ScorpionTrackVehicleSensorDescription(
        key="speed",
        name="Speed",
        device_class=SensorDeviceClass.SPEED,
        icon="mdi:speedometer",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda account, vehicle: _vehicle_speed(account, vehicle),
        unit_fn=lambda account, vehicle: (
            UnitOfSpeed.MILES_PER_HOUR
            if account.uses_miles
            else UnitOfSpeed.KILOMETERS_PER_HOUR
        ),
    ),
    ScorpionTrackVehicleSensorDescription(
        key="heading",
        name="Heading",
        icon="mdi:compass",
        suggested_display_precision=0,
        native_unit_of_measurement="deg",
        value_fn=lambda account, vehicle: (
            round(vehicle.position.bearing)
            if vehicle.position and vehicle.position.bearing is not None
            else None
        ),
    ),
    ScorpionTrackVehicleSensorDescription(
        key="odometer",
        name="Odometer",
        suggested_display_precision=1,
        icon="mdi:counter",
        value_fn=lambda account, vehicle: vehicle.odometer,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="battery_voltage",
        name="Battery Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:car-battery",
        value_fn=lambda account, vehicle: vehicle.vehicle_voltage,
        unit_fn=lambda account, vehicle: UnitOfElectricPotential.VOLT,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="backup_battery_voltage",
        name="Backup Battery Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:battery-medium",
        value_fn=lambda account, vehicle: vehicle.backup_battery_voltage,
        unit_fn=lambda account, vehicle: UnitOfElectricPotential.VOLT,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="gps_satellites",
        name="GPS Satellites",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:satellite-variant",
        value_fn=lambda account, vehicle: (
            vehicle.position.gps_satellites if vehicle.position else None
        ),
    ),
    ScorpionTrackVehicleSensorDescription(
        key="gps_hdop",
        name="GPS HDOP",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        icon="mdi:crosshairs-question",
        value_fn=lambda account, vehicle: vehicle.position.hdop if vehicle.position else None,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="last_reported",
        name="Last Reported",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-outline",
        value_fn=lambda account, vehicle: (
            vehicle.position.timestamp if vehicle.position else vehicle.updated_at
        ),
    ),
    ScorpionTrackVehicleSensorDescription(
        key="installed",
        name="Installed",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar-check",
        value_fn=lambda account, vehicle: vehicle.installed_at,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="unit_last_checked_in",
        name="Unit Last Checked In",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:router-wireless",
        value_fn=lambda account, vehicle: vehicle.unit_last_checked_in,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="last_service_date",
        name="Last Service Date",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:wrench-clock",
        value_fn=lambda account, vehicle: _as_date(vehicle.last_service_date),
    ),
    ScorpionTrackVehicleSensorDescription(
        key="registration",
        name="Registration",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:card-text-outline",
        value_fn=lambda account, vehicle: vehicle.registration,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="description",
        name="Description",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:text-box-outline",
        value_fn=lambda account, vehicle: vehicle.description,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="alias",
        name="Alias",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:badge-account-outline",
        value_fn=lambda account, vehicle: vehicle.alias,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="colour",
        name="Colour",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:palette-outline",
        value_fn=lambda account, vehicle: vehicle.colour,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="fuel_type",
        name="Fuel Type",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:gas-station-outline",
        value_fn=lambda account, vehicle: vehicle.fuel_type,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="battery_type",
        name="Battery Type",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:battery-outline",
        value_fn=lambda account, vehicle: vehicle.battery_type,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="make",
        name="Make",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:factory",
        value_fn=lambda account, vehicle: vehicle.make,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="model",
        name="Model",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:car-side",
        value_fn=lambda account, vehicle: vehicle.model,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="vehicle_type",
        name="Vehicle Type",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:car-multiple",
        value_fn=lambda account, vehicle: vehicle.vehicle_type,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="unit_model",
        name="Unit Model",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:chip",
        value_fn=lambda account, vehicle: vehicle.unit_model,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="unit_make",
        name="Unit Make",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:chip",
        value_fn=lambda account, vehicle: vehicle.unit_make,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="gps_antenna_voltage",
        name="GPS Antenna Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:antenna",
        value_fn=lambda account, vehicle: vehicle.gps_antenna_voltage,
        unit_fn=lambda account, vehicle: UnitOfElectricPotential.VOLT,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="gps_antenna_current",
        name="GPS Antenna Current",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        native_unit_of_measurement="mA",
        icon="mdi:current-ac",
        value_fn=lambda account, vehicle: vehicle.gps_antenna_current,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="pending_command_count",
        name="Pending Command Count",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:progress-clock",
        value_fn=lambda account, vehicle: vehicle.pending_commands_count,
    ),
    ScorpionTrackVehicleSensorDescription(
        key="mot_due",
        name="MOT Due",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar",
        value_fn=lambda account, vehicle: _as_date(vehicle.mot_due),
    ),
    ScorpionTrackVehicleSensorDescription(
        key="tax_due",
        name="Tax Due",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar",
        value_fn=lambda account, vehicle: _as_date(vehicle.tax_due),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ScorpionTrack account sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    known_vehicle_ids: set[int] = set()
    account_entities_added = False

    @callback
    def _async_add_missing_entities() -> None:
        nonlocal account_entities_added
        entities: list[SensorEntity] = []

        if not account_entities_added:
            entities.extend(
                ScorpionTrackAccountSensorEntity(coordinator, description)
                for description in ACCOUNT_SENSOR_DESCRIPTIONS
            )
            account_entities_added = True

        new_vehicle_ids = [
            vehicle.id
            for vehicle in coordinator.data.vehicles
            if vehicle.id not in known_vehicle_ids
        ]
        if new_vehicle_ids:
            known_vehicle_ids.update(new_vehicle_ids)
            entities.extend(
                ScorpionTrackVehicleSensorEntity(coordinator, vehicle_id, description)
                for vehicle_id in new_vehicle_ids
                for description in VEHICLE_SENSOR_DESCRIPTIONS
            )

        if entities:
            async_add_entities(entities)

    _async_add_missing_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_missing_entities))


class ScorpionTrackAccountSensorEntity(ScorpionTrackAccountEntity, SensorEntity):
    """Represent an account-level ScorpionTrack sensor."""

    _attr_has_entity_name = True

    entity_description: ScorpionTrackAccountSensorDescription

    def __init__(self, coordinator, description: ScorpionTrackAccountSensorDescription) -> None:
        """Initialize the account sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self.account_identifier}_{description.key}"
        self._attr_name = description.name

    @property
    def native_value(self) -> object:
        """Return the native sensor value."""
        return self.entity_description.value_fn(self.account)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return extra state attributes."""
        attributes = self.common_account_attributes()
        if self.entity_description.key in {"unread_alerts", "latest_alert"}:
            latest_alert = self.account.latest_alert
            if latest_alert is not None:
                attributes.update(latest_alert.as_attribute_dict())
            attributes["recent_alerts"] = _recent_alert_attribute_list(self.account)
        return attributes


class ScorpionTrackVehicleSensorEntity(ScorpionTrackVehicleEntity, SensorEntity):
    """Represent a vehicle-level ScorpionTrack sensor."""

    _attr_has_entity_name = True

    entity_description: ScorpionTrackVehicleSensorDescription

    def __init__(
        self,
        coordinator,
        vehicle_id: int,
        description: ScorpionTrackVehicleSensorDescription,
    ) -> None:
        """Initialize the vehicle sensor."""
        super().__init__(coordinator, vehicle_id)
        self.entity_description = description
        self._attr_unique_id = f"{self.account_identifier}_{vehicle_id}_{description.key}"
        self._attr_name = description.name

    @property
    def native_value(self) -> object:
        """Return the native sensor value."""
        return self.entity_description.value_fn(self.account, self.vehicle)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit of measurement."""
        if self.entity_description.unit_fn is None:
            return None
        return self.entity_description.unit_fn(self.account, self.vehicle)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return extra state attributes."""
        attributes = self.common_vehicle_attributes()
        if self.entity_description.key == "location":
            attributes["formatted_location"] = self.format_location()
        return attributes


def _format_location(vehicle: ScorpionTrackVehicleSummary) -> str | None:
    """Return a human-friendly location string."""
    if vehicle.position is None:
        return None
    if vehicle.position.address:
        return vehicle.position.address
    if (
        vehicle.position.latitude is not None
        and vehicle.position.longitude is not None
    ):
        return f"{vehicle.position.latitude:.6f}, {vehicle.position.longitude:.6f}"
    return None


def _vehicle_speed(
    account: ScorpionTrackAccountData,
    vehicle: ScorpionTrackVehicleSummary,
) -> float | None:
    """Return the current vehicle speed in the user's preferred units."""
    if vehicle.position is None or vehicle.position.speed_kmh is None:
        return None
    if account.uses_miles:
        return round(vehicle.position.speed_kmh * 0.621371, 2)
    return vehicle.position.speed_kmh


def _as_date(value: date | datetime | None) -> date | None:
    """Return a date value for Home Assistant date sensors."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def _recent_alert_attribute_list(
    account: ScorpionTrackAccountData,
) -> list[dict[str, object]]:
    """Return a compact recent-alert list for state attributes."""
    alerts: list[dict[str, object]] = []
    for alert in account.alerts:
        item = alert.as_attribute_dict()
        item["summary"] = alert.summary
        alerts.append(item)
    return alerts
