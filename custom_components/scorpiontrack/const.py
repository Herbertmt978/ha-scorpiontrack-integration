"""Constants for the ScorpionTrack integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "scorpiontrack"
DEFAULT_NAME = "ScorpionTrack Integration"
ACCOUNT_DEFAULT_NAME = "ScorpionTrack Account"
SHARE_DEFAULT_NAME = "ScorpionTrack Share"
MANUFACTURER = "ScorpionTrack"

CONF_SETUP_TYPE = "setup_type"
CONF_SHARE_TOKEN = "share_token"

SETUP_TYPE_ACCOUNT = "account"
SETUP_TYPE_SHARE = "share"

PORTAL_BASE_URL = "https://app.scorpiontrack.com"
LOGIN_PATH = "/home/login"
LOGIN_POST_PATH = "/login/check_for_multiple_accounts"
VEHICLE_LIST_PAGE_PATH = "/customer/vehicle/vehiclelist"
CUSTOMER_MAP_POSITIONS_PATH = "/customer/map/getNewVehiclePositions"
FMS_VEHICLES_PATH = "/vehicles"
FMS_ALERTS_PATH = "/alerts-dashboard/alerts"
FMS_ALERTS_BULK_READ_PATH = "/alerts-dashboard/bulk-read"

API_BASE_URL = "https://api2.fleet.scorpiontrack.com/v1"

ACCOUNT_SCAN_INTERVAL = timedelta(minutes=5)
SHARE_SCAN_INTERVAL = timedelta(minutes=2)
STALE_POSITION_THRESHOLD = timedelta(hours=24)

PLATFORMS: tuple[Platform, ...] = (
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.SWITCH,
    Platform.BUTTON,
)
