"""API client for authenticated ScorpionTrack portal access."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urljoin

from aiohttp import ClientError, ClientSession

from .const import (
    ACCOUNT_DEFAULT_NAME,
    CUSTOMER_MAP_POSITIONS_PATH,
    FMS_ALERTS_PATH,
    FMS_ALERTS_BULK_READ_PATH,
    FMS_VEHICLES_PATH,
    LOGIN_PATH,
    LOGIN_POST_PATH,
    PORTAL_BASE_URL,
    VEHICLE_LIST_PAGE_PATH,
)
from .utils import mask_email

_CSRF_TOKEN_RE = re.compile(r'name="ci_csrf_token"\s+value="([^"]+)"')
_FMS_API_URL_RE = re.compile(r'window\.ScorpionData\.fmsApiUrl\s*=\s*"([^"]+)"')
_PORTAL_USER_JSON_RE = re.compile(
    r"window\.ScorpionData\.user\s*=\s*(\{.*?\});",
    re.DOTALL,
)
_LOGGER = logging.getLogger(__name__)


class ScorpionTrackAccountError(Exception):
    """Base exception for ScorpionTrack account errors."""


class ScorpionTrackConnectionError(ScorpionTrackAccountError):
    """Raised when the ScorpionTrack portal cannot be reached."""


class ScorpionTrackAuthError(ScorpionTrackAccountError):
    """Raised when the portal authentication flow fails."""


class ScorpionTrackPortalError(ScorpionTrackAccountError):
    """Raised when the portal returns an unexpected response."""


@dataclass(slots=True, frozen=True)
class ScorpionTrackPortalContext:
    """Lightweight details extracted from an authenticated portal page."""

    user_id: int | None
    name: str | None
    distance_units: str | None
    app_api_key: str | None
    fms_api_url: str | None


@dataclass(slots=True, frozen=True)
class ScorpionTrackAlertSummary:
    """A compact authenticated alert record."""

    id: int
    source: str | None
    type: str | None
    severity: str | None
    timestamp: datetime | None
    read_status: bool | None
    vehicle_id: int | None
    vehicle_registration: str | None
    vehicle_alias: str | None
    vehicle_name: str | None
    alert_name: str | None
    speed_recorded: float | None
    road_speed: float | None
    idle: float | None
    engine_hours: float | None
    latitude: float | None
    longitude: float | None

    @property
    def location(self) -> str | None:
        """Return a human-friendly alert location string."""
        if self.latitude is None or self.longitude is None:
            return None
        return f"{self.latitude:.6f}, {self.longitude:.6f}"

    @property
    def display_vehicle(self) -> str | None:
        """Return the best user-facing vehicle label."""
        return (
            self.vehicle_alias
            or self.vehicle_registration
            or self.vehicle_name
            or (f"Vehicle {self.vehicle_id}" if self.vehicle_id is not None else None)
        )

    @property
    def summary(self) -> str:
        """Return a short one-line summary for the alert."""
        label = self.type or "Alert"
        if self.alert_name and self.alert_name.lower() != label.lower():
            label = f"{label} ({self.alert_name})"
        if self.display_vehicle:
            return f"{label} - {self.display_vehicle}"
        return label

    def as_attribute_dict(self) -> dict[str, object]:
        """Return the alert as Home Assistant-friendly attributes."""
        return {
            "alert_id": self.id,
            "source": self.source,
            "type": self.type,
            "severity": self.severity,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "read": self.read_status,
            "vehicle_id": self.vehicle_id,
            "vehicle": self.display_vehicle,
            "vehicle_registration": self.vehicle_registration,
            "alert_name": self.alert_name,
            "speed_recorded": self.speed_recorded,
            "road_speed": self.road_speed,
            "idle": self.idle,
            "engine_hours": self.engine_hours,
            "alert_location": self.location,
            "alert_latitude": self.latitude,
            "alert_longitude": self.longitude,
        }


@dataclass(slots=True, frozen=True)
class ScorpionTrackVehiclePosition:
    """The best-known position for a vehicle."""

    latitude: float | None
    longitude: float | None
    timestamp: datetime | None
    speed: float | None
    speed_kmh: float | None
    bearing: float | None
    accuracy: float | None
    address: str | None
    ignition: bool | None
    engine: bool | None
    gps_satellites: int | None
    hdop: float | None
    raw_state: str | None
    friendly_state: str | None
    vehicle_voltage: float | None
    odometer: float | None
    unit_type: str | None
    unit_id: int | None
    distance_units: str | None
    units_speed: str | None


@dataclass(slots=True, frozen=True)
class ScorpionTrackVehicleSummary:
    """A compact authenticated vehicle record."""

    id: int
    registration: str | None
    alias: str | None
    make: str | None
    model: str | None
    vehicle_type: str | None
    description: str | None
    colour: str | None
    fuel_type: str | None
    raw_state: str | None
    status: str | None
    odometer: float | None
    installed_at: datetime | None
    updated_at: datetime | None
    last_service_date: date | datetime | None
    mot_due: date | datetime | None
    tax_due: date | datetime | None
    battery_type: str | None
    vehicle_voltage: float | None
    backup_battery_voltage: float | None
    gps_antenna_voltage: float | None
    gps_antenna_current: float | None
    install_complete: bool | None
    immobiliser_fitted: bool | None
    driver_module: bool | None
    ewm_enabled: bool | None
    g_sense_enabled: bool | None
    privacy_mode_enabled: bool | None
    zero_speed_mode_enabled: bool | None
    armed_mode_enabled: bool | None
    transport_mode_begin: datetime | None
    transport_mode_end: datetime | None
    garage_mode_begin: datetime | None
    garage_mode_end: datetime | None
    no_alert_start: datetime | None
    no_alert_end: datetime | None
    pending_commands_count: int
    group_names: tuple[str, ...]
    unit_type: str | None
    unit_model: str | None
    unit_make: str | None
    unit_last_checked_in: datetime | None
    position: ScorpionTrackVehiclePosition | None

    @property
    def display_name(self) -> str:
        """Return the best user-facing name for the vehicle."""
        return self.alias or self.registration or f"Vehicle {self.id}"

    @property
    def transport_mode_active(self) -> bool:
        """Return True when transport mode is active now."""
        return _window_is_active(self.transport_mode_begin, self.transport_mode_end)

    @property
    def garage_mode_active(self) -> bool:
        """Return True when garage mode is active now."""
        return _window_is_active(self.garage_mode_begin, self.garage_mode_end)

    @property
    def no_alert_mode_active(self) -> bool:
        """Return True when no-alert mode is active now."""
        return _window_is_active(self.no_alert_start, self.no_alert_end)


@dataclass(slots=True, frozen=True)
class ScorpionTrackAccountData:
    """The current authenticated account snapshot."""

    email: str
    title: str
    user_id: int | None
    distance_units: str | None
    app_api_key: str | None
    fms_api_url: str | None
    vehicles: tuple[ScorpionTrackVehicleSummary, ...]
    total_alerts: int | None
    unread_alerts: int | None
    alerts: tuple[ScorpionTrackAlertSummary, ...]
    fetched_at: datetime

    @property
    def app_api_key_available(self) -> bool:
        """Return True if the portal exposed an app API key on the page."""
        return bool(self.app_api_key)

    @property
    def uses_miles(self) -> bool:
        """Return True when the portal is configured to display miles."""
        return (self.distance_units or "").strip().lower().startswith("mile")

    @property
    def latest_alert(self) -> ScorpionTrackAlertSummary | None:
        """Return the newest unread alert when available, else the newest alert."""
        for alert in self.alerts:
            if alert.read_status is False:
                return alert
        return self.alerts[0] if self.alerts else None


class ScorpionTrackAccountClient:
    """Minimal client for the ScorpionTrack authenticated web portal."""

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        *,
        base_url: str = PORTAL_BASE_URL,
        timeout_seconds: int = 20,
    ) -> None:
        """Initialize the portal client."""
        self._session = session
        self._email = email.strip().lower()
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._authenticated = False
        self._portal_context: ScorpionTrackPortalContext | None = None

    @property
    def email(self) -> str:
        """Return the normalized account email."""
        return self._email

    async def async_refresh_account(self) -> ScorpionTrackAccountData:
        """Return the latest authenticated account snapshot."""
        await self.async_login()

        try:
            return await self._async_build_account_data()
        except ScorpionTrackAuthError:
            _LOGGER.info(
                "ScorpionTrack portal session expired while refreshing account %s; retrying login",
                mask_email(self._email),
            )
            await self.async_login(force=True)
            return await self._async_build_account_data()

    async def async_login(self, *, force: bool = False) -> None:
        """Authenticate to the ScorpionTrack portal."""
        if self._authenticated and not force:
            _LOGGER.debug(
                "Reusing existing ScorpionTrack portal session for %s",
                mask_email(self._email),
            )
            return

        self._authenticated = False
        self._portal_context = None
        _LOGGER.debug(
            "Authenticating ScorpionTrack portal session for %s (force=%s)",
            mask_email(self._email),
            force,
        )

        login_status, login_url, login_html = await self._request_text(
            "GET", LOGIN_PATH, ajax=False
        )
        csrf_token = _extract_first(_CSRF_TOKEN_RE, login_html)
        if not csrf_token:
            lowered = login_html.lower()
            _LOGGER.warning(
                "ScorpionTrack login page for %s did not expose a CSRF token "
                "(status=%s, final_url=%s, has_login_form=%s, has_password_field=%s)",
                mask_email(self._email),
                login_status,
                login_url,
                'id=\"login_form\"' in lowered,
                'name=\"pass\"' in lowered,
            )
            raise ScorpionTrackPortalError(
                "ScorpionTrack login page did not expose a CSRF token"
            )

        form_data = {
            "ci_csrf_token": csrf_token,
            "register": "false",
            "email": self._email,
            "pass": self._password,
        }
        _, final_url, response_html = await self._request_text(
            "POST",
            LOGIN_POST_PATH,
            data=form_data,
            ajax=False,
        )

        if _looks_like_login_error(response_html):
            _LOGGER.warning(
                "ScorpionTrack rejected the supplied credentials for %s (final_url=%s)",
                mask_email(self._email),
                final_url,
            )
            raise ScorpionTrackAuthError(
                "Portal login rejected the supplied credentials"
            )

        portal_context = await self.async_get_portal_context()
        if not portal_context.app_api_key or not portal_context.fms_api_url:
            _LOGGER.warning(
                "ScorpionTrack portal login for %s completed but the authenticated page was "
                "missing expected API details (user_id=%s, has_app_api_key=%s, has_fms_api_url=%s)",
                mask_email(self._email),
                portal_context.user_id,
                bool(portal_context.app_api_key),
                bool(portal_context.fms_api_url),
            )
            raise ScorpionTrackPortalError(
                "Authenticated portal page did not expose the expected fleet API details"
            )

        self._portal_context = portal_context
        self._authenticated = True
        _LOGGER.debug(
            "Authenticated ScorpionTrack portal session for %s (user_id=%s)",
            mask_email(self._email),
            portal_context.user_id,
        )

    async def async_get_portal_context(self) -> ScorpionTrackPortalContext:
        """Extract account context from the authenticated vehicle list page."""
        _, final_url, page_html = await self._request_text(
            "GET",
            VEHICLE_LIST_PAGE_PATH,
            ajax=False,
        )
        if _looks_like_login_page(final_url, page_html):
            _LOGGER.warning(
                "ScorpionTrack vehicle list for %s redirected back to login (final_url=%s)",
                mask_email(self._email),
                final_url,
            )
            raise ScorpionTrackAuthError(
                "Authenticated vehicle list page redirected back to login"
            )

        user_payload = _extract_portal_user_payload(page_html)
        return ScorpionTrackPortalContext(
            user_id=_coerce_int(user_payload.get("userId")),
            name=_clean_text(user_payload.get("name")),
            distance_units=_clean_text(user_payload.get("distanceUnits")),
            app_api_key=_clean_text(user_payload.get("appApiKey")),
            fms_api_url=_clean_text(_extract_first(_FMS_API_URL_RE, page_html)),
        )

    async def async_get_vehicles(
        self, *, limit: int = 250
    ) -> tuple[ScorpionTrackVehicleSummary, ...]:
        """Return the latest vehicle data without the account wrapper."""
        await self.async_login()
        portal_context = await self._require_portal_context()
        vehicle_payloads = await self._async_get_vehicle_payloads(
            portal_context,
            limit=limit,
        )
        positions_by_id = await self._async_get_map_positions(
            [vehicle["id"] for vehicle in vehicle_payloads if "id" in vehicle]
        )

        return tuple(
            self._parse_vehicle(payload, positions_by_id.get(_coerce_int(payload.get("id"))))
            for payload in vehicle_payloads
            if isinstance(payload, dict) and _coerce_int(payload.get("id")) is not None
        )

    async def async_set_vehicle_mode(
        self,
        vehicle_id: int,
        mode_key: str,
        enabled: bool,
    ) -> None:
        """Toggle a supported boolean vehicle mode."""
        await self.async_login()

        try:
            portal_context = await self._require_portal_context()
            await self._request_fms_json(
                portal_context,
                "PUT",
                f"{FMS_VEHICLES_PATH}/{vehicle_id}",
                json_data={mode_key: bool(enabled)},
            )
        except ScorpionTrackAuthError:
            await self.async_login(force=True)
            portal_context = await self._require_portal_context()
            await self._request_fms_json(
                portal_context,
                "PUT",
                f"{FMS_VEHICLES_PATH}/{vehicle_id}",
                json_data={mode_key: bool(enabled)},
            )

    async def async_mark_all_alerts_read(self) -> int:
        """Mark all unread alerts as read and return the updated count."""
        await self.async_login()

        try:
            portal_context = await self._require_portal_context()
            unread_alert_payloads = await self._async_get_unread_alert_payloads(portal_context)
            if not unread_alert_payloads:
                return 0

            payload = await self._request_fms_json(
                portal_context,
                "POST",
                FMS_ALERTS_BULK_READ_PATH,
                json_data={"alerts": unread_alert_payloads},
            )
        except ScorpionTrackAuthError:
            await self.async_login(force=True)
            portal_context = await self._require_portal_context()
            unread_alert_payloads = await self._async_get_unread_alert_payloads(portal_context)
            if not unread_alert_payloads:
                return 0

            payload = await self._request_fms_json(
                portal_context,
                "POST",
                FMS_ALERTS_BULK_READ_PATH,
                json_data={"alerts": unread_alert_payloads},
            )

        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, dict):
                updated = _coerce_int(data.get("updated"))
                if updated is not None:
                    return updated

        return len(unread_alert_payloads)

    async def _async_build_account_data(self) -> ScorpionTrackAccountData:
        """Build the latest account snapshot."""
        portal_context = await self._require_portal_context()
        vehicle_payloads = await self._async_get_vehicle_payloads(portal_context, limit=250)
        vehicle_ids = [
            vehicle_id
            for vehicle_id in (_coerce_int(vehicle.get("id")) for vehicle in vehicle_payloads)
            if vehicle_id is not None
        ]

        try:
            positions_by_id = await self._async_get_map_positions(vehicle_ids)
        except ScorpionTrackPortalError as err:
            _LOGGER.debug(
                "ScorpionTrack map position fetch failed for %s: %s",
                mask_email(self._email),
                err,
            )
            positions_by_id = {}

        vehicles = tuple(
            self._parse_vehicle(payload, positions_by_id.get(_coerce_int(payload.get("id"))))
            for payload in vehicle_payloads
            if isinstance(payload, dict) and _coerce_int(payload.get("id")) is not None
        )

        alerts: tuple[ScorpionTrackAlertSummary, ...] = ()
        total_alerts: int | None = None
        try:
            alerts, total_alerts = await self._async_get_recent_alerts(
                portal_context,
                limit=5,
            )
        except ScorpionTrackPortalError as err:
            _LOGGER.debug(
                "ScorpionTrack alerts fetch failed for %s: %s",
                mask_email(self._email),
                err,
            )
            alerts = ()
            total_alerts = None

        try:
            unread_alerts = await self._async_get_unread_alert_count(portal_context)
        except ScorpionTrackPortalError as err:
            _LOGGER.debug(
                "ScorpionTrack unread alert count fetch failed for %s: %s",
                mask_email(self._email),
                err,
            )
            unread_alerts = None

        title = (
            f"ScorpionTrack ({portal_context.name})"
            if portal_context.name
            else ACCOUNT_DEFAULT_NAME
        )
        return ScorpionTrackAccountData(
            email=self._email,
            title=title,
            user_id=portal_context.user_id,
            distance_units=portal_context.distance_units,
            app_api_key=portal_context.app_api_key,
            fms_api_url=portal_context.fms_api_url,
            vehicles=vehicles,
            total_alerts=total_alerts,
            unread_alerts=unread_alerts,
            alerts=alerts,
            fetched_at=datetime.now(UTC),
        )

    async def _async_get_vehicle_payloads(
        self,
        portal_context: ScorpionTrackPortalContext,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch the rich FMS vehicle list for the account."""
        vehicles: list[dict[str, Any]] = []
        page = 1

        while True:
            payload = await self._request_fms_json(
                portal_context,
                "GET",
                FMS_VEHICLES_PATH,
                params={
                    "page": page,
                    "limit": limit,
                },
            )
            if not isinstance(payload, dict):
                _LOGGER.warning(
                    "ScorpionTrack vehicle list endpoint returned a non-object payload for %s "
                    "(page=%s, limit=%s)",
                    mask_email(self._email),
                    page,
                    limit,
                )
                raise ScorpionTrackPortalError(
                    "Vehicle list endpoint returned a non-object payload"
                )

            vehicle_container = payload.get("vehicles")
            page_items = _extract_nested_list(vehicle_container)
            vehicles.extend(item for item in page_items if isinstance(item, dict))

            meta = _extract_nested_dict(vehicle_container.get("meta") if isinstance(vehicle_container, dict) else None)
            total_pages = _coerce_int(meta.get("total_pages")) if meta else None
            if total_pages is None or page >= total_pages:
                break
            page += 1

        return vehicles

    async def _async_get_map_positions(
        self,
        vehicle_ids: list[int],
    ) -> dict[int, ScorpionTrackVehiclePosition]:
        """Fetch the current map positions for a set of vehicles."""
        if not vehicle_ids:
            return {}

        path = (
            f"{CUSTOMER_MAP_POSITIONS_PATH}/0/"
            + "_".join(str(vehicle_id) for vehicle_id in vehicle_ids)
        )
        payload = await self._request_json("GET", path, ajax=True)
        if not isinstance(payload, dict):
            _LOGGER.warning(
                "ScorpionTrack map positions endpoint returned a non-object payload for %s",
                mask_email(self._email),
            )
            raise ScorpionTrackPortalError(
                "Vehicle map endpoint returned a non-object payload"
            )

        positions = payload.get("Positions")
        if not isinstance(positions, list):
            return {}

        parsed: dict[int, ScorpionTrackVehiclePosition] = {}
        for item in positions:
            if not isinstance(item, dict):
                continue
            vehicle_id = _coerce_int(item.get("vehicleId"))
            if vehicle_id is None:
                continue
            parsed[vehicle_id] = _parse_position(item)

        return parsed

    async def _async_get_unread_alert_count(
        self,
        portal_context: ScorpionTrackPortalContext,
    ) -> int | None:
        """Return the unread alert count when the dashboard endpoint allows it."""
        payload = await self._request_fms_json(
            portal_context,
            "GET",
            FMS_ALERTS_PATH,
            params={
                "unread_only": "1",
                "page": 1,
                "limit": 1,
            },
        )

        if isinstance(payload, dict):
            meta = payload.get("meta")
            if isinstance(meta, dict):
                total = _coerce_int(meta.get("total"))
                if total is not None:
                    return total

            data = payload.get("data")
            if isinstance(data, list):
                return len(data)

        return None

    async def _async_get_recent_alerts(
        self,
        portal_context: ScorpionTrackPortalContext,
        *,
        limit: int,
    ) -> tuple[tuple[ScorpionTrackAlertSummary, ...], int | None]:
        """Return the newest alert records plus the total alert count."""
        payload = await self._request_fms_json(
            portal_context,
            "GET",
            FMS_ALERTS_PATH,
            params={
                "page": 1,
                "limit": limit,
            },
        )

        if not isinstance(payload, dict):
            _LOGGER.warning(
                "ScorpionTrack alerts endpoint returned a non-object payload for %s",
                mask_email(self._email),
            )
            raise ScorpionTrackPortalError(
                "Alerts endpoint returned a non-object payload"
            )

        alerts = tuple(
            self._parse_alert(item)
            for item in payload.get("data", [])
            if isinstance(item, dict)
        )
        meta = payload.get("meta")
        total = _coerce_int(meta.get("total")) if isinstance(meta, dict) else None
        return alerts, total

    async def _async_get_unread_alert_payloads(
        self,
        portal_context: ScorpionTrackPortalContext,
        *,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """Return every unread alert payload available to the account."""
        alerts: list[dict[str, Any]] = []
        page = 1

        while True:
            payload = await self._request_fms_json(
                portal_context,
                "GET",
                FMS_ALERTS_PATH,
                params={
                    "unread_only": "1",
                    "page": page,
                    "limit": page_size,
                },
            )

            if not isinstance(payload, dict):
                _LOGGER.warning(
                    "ScorpionTrack unread alerts endpoint returned a non-object payload for %s "
                    "(page=%s, page_size=%s)",
                    mask_email(self._email),
                    page,
                    page_size,
                )
                raise ScorpionTrackPortalError(
                    "Unread alerts endpoint returned a non-object payload"
                )

            data = payload.get("data")
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    if _coerce_int(item.get("id")) is not None:
                        alerts.append(item)

            meta = payload.get("meta")
            total_pages = _coerce_int(meta.get("total_pages")) if isinstance(meta, dict) else None
            if total_pages is None or page >= total_pages:
                break
            page += 1

        return alerts

    async def _require_portal_context(self) -> ScorpionTrackPortalContext:
        """Return the current portal context, refreshing it when necessary."""
        if self._portal_context is not None:
            return self._portal_context

        portal_context = await self.async_get_portal_context()
        self._portal_context = portal_context
        return portal_context

    async def _request_text(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        ajax: bool,
    ) -> tuple[int, str, str]:
        """Request a portal resource and return status, URL, and text."""
        url = self._build_portal_url(path)
        headers = {
            "Referer": f"{self._base_url}/",
            "Accept": (
                "application/json, text/javascript, */*; q=0.01"
                if ajax
                else "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            ),
        }
        if ajax:
            headers["X-Requested-With"] = "XMLHttpRequest"

        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._session.request(
                    method,
                    url,
                    params=params,
                    data=data,
                    headers=headers,
                    allow_redirects=True,
                ) as response:
                    text = await response.text()
                    status = response.status
                    final_url = str(response.url)
        except TimeoutError as err:
            _LOGGER.warning(
                "Timed out contacting the ScorpionTrack portal for %s (%s %s)",
                mask_email(self._email),
                method,
                path,
            )
            raise ScorpionTrackConnectionError(
                "Timed out contacting the ScorpionTrack portal"
            ) from err
        except ClientError as err:
            _LOGGER.warning(
                "Error contacting the ScorpionTrack portal for %s (%s %s): %s",
                mask_email(self._email),
                method,
                path,
                err,
            )
            raise ScorpionTrackConnectionError(
                "Failed to contact the ScorpionTrack portal"
            ) from err

        if final_url != url:
            _LOGGER.debug(
                "ScorpionTrack portal request for %s redirected (%s %s -> %s)",
                mask_email(self._email),
                method,
                path,
                final_url,
            )
        if status in (401, 403):
            _LOGGER.warning(
                "ScorpionTrack portal rejected the session for %s (%s %s, status=%s, final_url=%s)",
                mask_email(self._email),
                method,
                path,
                status,
                final_url,
            )
            raise ScorpionTrackAuthError("Portal session was rejected")
        if status >= 500:
            _LOGGER.warning(
                "ScorpionTrack portal returned HTTP %s for %s (%s %s)",
                status,
                mask_email(self._email),
                method,
                path,
            )
            raise ScorpionTrackPortalError(
                f"Portal returned HTTP {status} for {path}"
            )

        return status, final_url, text

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        ajax: bool = True,
    ) -> Any:
        """Request a JSON portal endpoint."""
        _, final_url, text = await self._request_text(
            method,
            path,
            params=params,
            data=data,
            ajax=ajax,
        )

        if _looks_like_login_page(final_url, text) or _looks_like_login_error(text):
            _LOGGER.warning(
                "ScorpionTrack portal endpoint for %s redirected to login instead of returning JSON "
                "(%s %s, final_url=%s)",
                mask_email(self._email),
                method,
                path,
                final_url,
            )
            raise ScorpionTrackAuthError(
                "Portal endpoint redirected to login instead of returning JSON"
            )

        try:
            return json.loads(text)
        except json.JSONDecodeError as err:
            _LOGGER.warning(
                "ScorpionTrack portal endpoint for %s returned non-JSON content (%s %s, final_url=%s, text_length=%s)",
                mask_email(self._email),
                method,
                path,
                final_url,
                len(text),
            )
            raise ScorpionTrackPortalError(
                f"Portal returned non-JSON content for {path}"
            ) from err

    async def _request_fms_text(
        self,
        portal_context: ScorpionTrackPortalContext,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> tuple[int, str, str]:
        """Request an authenticated FMS resource and return status, URL, and text."""
        if not portal_context.fms_api_url or not portal_context.app_api_key:
            raise ScorpionTrackPortalError(
                "FMS API details are not available in the portal context"
            )

        authorization = "Basic " + base64.b64encode(
            portal_context.app_api_key.encode("utf-8")
        ).decode("ascii")
        url = self._build_fms_url(portal_context.fms_api_url, path)
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Authorization": authorization,
        }

        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._session.request(
                    method,
                    url,
                    params=params,
                    json=json_data,
                    headers=headers,
                    allow_redirects=True,
                ) as response:
                    text = await response.text()
                    status = response.status
                    final_url = str(response.url)
        except TimeoutError as err:
            _LOGGER.warning(
                "Timed out contacting the ScorpionTrack fleet API for %s (%s %s)",
                mask_email(self._email),
                method,
                path,
            )
            raise ScorpionTrackConnectionError(
                "Timed out contacting the ScorpionTrack fleet API"
            ) from err
        except ClientError as err:
            _LOGGER.warning(
                "Error contacting the ScorpionTrack fleet API for %s (%s %s): %s",
                mask_email(self._email),
                method,
                path,
                err,
            )
            raise ScorpionTrackConnectionError(
                "Failed to contact the ScorpionTrack fleet API"
            ) from err

        if final_url != url:
            _LOGGER.debug(
                "ScorpionTrack fleet request for %s redirected (%s %s -> %s)",
                mask_email(self._email),
                method,
                path,
                final_url,
            )
        if status in (401, 403):
            _LOGGER.warning(
                "ScorpionTrack fleet API rejected credentials for %s (%s %s, status=%s)",
                mask_email(self._email),
                method,
                path,
                status,
            )
            raise ScorpionTrackAuthError("Fleet API credentials were rejected")
        if status >= 500:
            _LOGGER.warning(
                "ScorpionTrack fleet API returned HTTP %s for %s (%s %s)",
                status,
                mask_email(self._email),
                method,
                path,
            )
            raise ScorpionTrackPortalError(
                f"Fleet API returned HTTP {status} for {path}"
            )

        return status, final_url, text

    async def _request_fms_json(
        self,
        portal_context: ScorpionTrackPortalContext,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        """Request a JSON FMS endpoint."""
        _, _, text = await self._request_fms_text(
            portal_context,
            method,
            path,
            params=params,
            json_data=json_data,
        )

        try:
            return json.loads(text)
        except json.JSONDecodeError as err:
            _LOGGER.warning(
                "ScorpionTrack fleet API returned non-JSON content for %s (%s %s, text_length=%s)",
                mask_email(self._email),
                method,
                path,
                len(text),
            )
            raise ScorpionTrackPortalError(
                f"Fleet API returned non-JSON content for {path}"
            ) from err

    def _build_portal_url(self, path: str) -> str:
        """Return a fully qualified portal URL."""
        return path if path.startswith("http") else urljoin(f"{self._base_url}/", path.lstrip("/"))

    def _build_fms_url(self, base_url: str, path: str) -> str:
        """Return a fully qualified FMS URL."""
        return path if path.startswith("http") else urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))

    def _parse_vehicle(
        self,
        vehicle_data: dict[str, Any],
        map_position: ScorpionTrackVehiclePosition | None,
    ) -> ScorpionTrackVehicleSummary:
        """Convert a raw vehicle payload into a compact summary."""
        vehicle_id = _coerce_int(vehicle_data.get("id"))
        if vehicle_id is None:
            raise ScorpionTrackPortalError("Vehicle record did not contain an ID")

        unit_data = _extract_nested_dict(vehicle_data.get("unit"))
        group_entries = _extract_nested_list(vehicle_data.get("groups"))
        pending_commands = _extract_nested_list(vehicle_data.get("pending_commands"))
        healthcheck_data = _extract_nested_dict(vehicle_data.get("healthcheck"))
        latest_position_data = _extract_nested_dict(vehicle_data.get("latest_position"))

        latest_position = _parse_position(latest_position_data)
        position = _merge_positions(map_position, latest_position)
        raw_state = _clean_text(
            (position.raw_state if position is not None else None) or vehicle_data.get("state")
        )
        status = (
            position.friendly_state
            if position is not None
            else _derive_vehicle_status(raw_state, None, None, None)
        )

        return ScorpionTrackVehicleSummary(
            id=vehicle_id,
            registration=_clean_text(vehicle_data.get("registration")),
            alias=_clean_text(vehicle_data.get("alias")),
            make=_clean_text(vehicle_data.get("make")),
            model=_clean_text(vehicle_data.get("model")),
            vehicle_type=_clean_text(vehicle_data.get("type")),
            description=_clean_text(vehicle_data.get("description")),
            colour=_clean_text(vehicle_data.get("colour")),
            fuel_type=_clean_text(vehicle_data.get("fuel_type")),
            raw_state=raw_state,
            status=status,
            odometer=_coerce_float(
                (position.odometer if position is not None else None)
                or vehicle_data.get("odometer")
            ),
            installed_at=_coerce_datetime(vehicle_data.get("installed") or unit_data.get("fitted")),
            updated_at=_coerce_datetime(vehicle_data.get("timestamp")),
            last_service_date=_coerce_temporal(vehicle_data.get("lastService")),
            mot_due=_coerce_temporal(vehicle_data.get("mot_due")),
            tax_due=_coerce_temporal(vehicle_data.get("tax_due")),
            battery_type=_clean_text(vehicle_data.get("battery_type")),
            vehicle_voltage=_coerce_float(
                (position.vehicle_voltage if position is not None else None)
                or healthcheck_data.get("vehicle_system_voltage")
            ),
            backup_battery_voltage=_coerce_float(
                healthcheck_data.get("backup_battery_voltage")
            ),
            gps_antenna_voltage=_coerce_float(
                healthcheck_data.get("gps_antenna_voltage")
            ),
            gps_antenna_current=_coerce_float(
                healthcheck_data.get("gps_antenna_current")
            ),
            install_complete=_coerce_bool(vehicle_data.get("install_complete")),
            immobiliser_fitted=_coerce_bool(vehicle_data.get("immobiliser")),
            driver_module=_coerce_bool(vehicle_data.get("driver_module")),
            ewm_enabled=_coerce_bool(vehicle_data.get("ewm_enabled")),
            g_sense_enabled=_coerce_bool(vehicle_data.get("g_sense")),
            privacy_mode_enabled=_coerce_bool(vehicle_data.get("privacy_mode_enabled")),
            zero_speed_mode_enabled=_coerce_bool(vehicle_data.get("zero_speed_mode_enabled")),
            armed_mode_enabled=_coerce_bool(vehicle_data.get("monitored_mode_enabled")),
            transport_mode_begin=_coerce_datetime(vehicle_data.get("transport_mode_begin")),
            transport_mode_end=_coerce_datetime(vehicle_data.get("transport_mode_end")),
            garage_mode_begin=_coerce_datetime(vehicle_data.get("garage_mode_begin")),
            garage_mode_end=_coerce_datetime(vehicle_data.get("garage_mode_end")),
            no_alert_start=_coerce_datetime(vehicle_data.get("no_alert_start")),
            no_alert_end=_coerce_datetime(vehicle_data.get("no_alert_end")),
            pending_commands_count=len(pending_commands),
            group_names=tuple(
                group_name
                for group_name in (
                    _clean_text(group.get("group_name") or group.get("name"))
                    for group in group_entries
                )
                if group_name
            ),
            unit_type=_clean_text(unit_data.get("type")),
            unit_model=_clean_text(unit_data.get("model")),
            unit_make=_clean_text(unit_data.get("make")),
            unit_last_checked_in=_coerce_datetime(unit_data.get("last_checked_in")),
            position=position,
        )

    def _parse_alert(self, alert_data: dict[str, Any]) -> ScorpionTrackAlertSummary:
        """Convert a raw alert payload into a compact summary."""
        vehicle_data = _extract_nested_dict(alert_data.get("vehicle"))
        details_data = _extract_nested_dict(alert_data.get("details"))
        location_data = _extract_nested_dict(alert_data.get("location"))

        return ScorpionTrackAlertSummary(
            id=int(alert_data["id"]),
            source=_clean_text(alert_data.get("source")),
            type=_clean_text(alert_data.get("type")),
            severity=_clean_text(alert_data.get("severity")),
            timestamp=_coerce_datetime(alert_data.get("timestamp")),
            read_status=_coerce_bool(alert_data.get("read_status")),
            vehicle_id=_coerce_int(vehicle_data.get("id")),
            vehicle_registration=_clean_text(vehicle_data.get("registration")),
            vehicle_alias=_clean_text(vehicle_data.get("alias")),
            vehicle_name=_clean_text(vehicle_data.get("vehicle_name")),
            alert_name=_clean_text(details_data.get("alert_name")),
            speed_recorded=_coerce_float(details_data.get("speed_recorded")),
            road_speed=_coerce_float(details_data.get("road_speed")),
            idle=_coerce_float(details_data.get("idle")),
            engine_hours=_coerce_float(details_data.get("engine_hours")),
            latitude=_coerce_float(location_data.get("latitude")),
            longitude=_coerce_float(location_data.get("longitude")),
        )


def _clean_text(value: Any) -> str | None:
    """Normalize text values."""
    if value is None:
        return None

    cleaned = str(value).strip()
    return cleaned or None


def _coerce_int(value: Any) -> int | None:
    """Convert a value to int when possible."""
    if value is None or value == "":
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    """Convert a value to float when possible."""
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool(value: Any) -> bool | None:
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


def _coerce_datetime(value: Any) -> datetime | None:
    """Parse a datetime-like value into an aware UTC datetime."""
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC)

    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None

        try:
            if cleaned.endswith("Z"):
                return datetime.fromisoformat(cleaned.replace("Z", "+00:00")).astimezone(UTC)
            if "T" in cleaned:
                parsed = datetime.fromisoformat(cleaned)
                return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
            if " " in cleaned:
                parsed = datetime.fromisoformat(cleaned.replace(" ", "T"))
                return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
            if cleaned.isdigit():
                return datetime.fromtimestamp(int(cleaned), UTC)
        except ValueError:
            return None

    return None


def _coerce_temporal(value: Any) -> date | datetime | None:
    """Parse a date-like or datetime-like value."""
    parsed_datetime = _coerce_datetime(value)
    if parsed_datetime is not None:
        return parsed_datetime

    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return date.fromisoformat(cleaned)
        except ValueError:
            return None

    return None


def _extract_first(pattern: re.Pattern[str], text: str) -> str | None:
    """Return the first captured match for a compiled regex."""
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1).strip()


def _extract_portal_user_payload(page_html: str) -> dict[str, Any]:
    """Return the authenticated portal user payload embedded in the page."""
    raw_json = _extract_first(_PORTAL_USER_JSON_RE, page_html)
    if not raw_json:
        return {}

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}

    return payload if isinstance(payload, dict) else {}


def _extract_nested_dict(value: Any) -> dict[str, Any]:
    """Return a nested dict from either a raw dict or {data: {...}} shape."""
    if isinstance(value, dict):
        data = value.get("data")
        if isinstance(data, dict):
            return data
        return value
    return {}


def _extract_nested_list(value: Any) -> list[dict[str, Any]]:
    """Return a nested list from either a raw list or {data: [...]} shape."""
    if isinstance(value, dict):
        data = value.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _parse_position(position_data: dict[str, Any] | None) -> ScorpionTrackVehiclePosition | None:
    """Parse a raw map or FMS position payload."""
    if not isinstance(position_data, dict):
        return None

    latitude = _coerce_float(position_data.get("lat"))
    longitude = _coerce_float(position_data.get("lng"))
    timestamp = _coerce_datetime(position_data.get("timestamp"))
    speed_kmh = _coerce_float(position_data.get("speedkm"))
    speed = _coerce_float(position_data.get("speed"))
    if speed_kmh is None:
        speed_kmh = speed

    ignition = _coerce_bool(position_data.get("ignition"))
    engine = _coerce_bool(position_data.get("engine"))
    raw_state = _clean_text(position_data.get("state"))
    friendly_state = _derive_vehicle_status(raw_state, ignition, engine, speed_kmh)

    if (
        latitude is None
        and longitude is None
        and timestamp is None
        and speed_kmh is None
        and raw_state is None
    ):
        return None

    return ScorpionTrackVehiclePosition(
        latitude=latitude,
        longitude=longitude,
        timestamp=timestamp,
        speed=speed,
        speed_kmh=speed_kmh,
        bearing=_coerce_float(position_data.get("bearing")),
        accuracy=_coerce_float(position_data.get("accuracy")),
        address=_clean_text(position_data.get("address")),
        ignition=ignition,
        engine=engine,
        gps_satellites=_coerce_int(
            position_data.get("gps") or position_data.get("gps_satellites")
        ),
        hdop=_coerce_float(position_data.get("hdop")),
        raw_state=raw_state,
        friendly_state=friendly_state,
        vehicle_voltage=_coerce_float(position_data.get("vehicleVoltage")),
        odometer=_coerce_float(position_data.get("odometer")),
        unit_type=_clean_text(position_data.get("unitType")),
        unit_id=_coerce_int(position_data.get("unitId")),
        distance_units=_clean_text(position_data.get("distanceUnits")),
        units_speed=_clean_text(position_data.get("unitsSpeed")),
    )


def _merge_positions(
    primary: ScorpionTrackVehiclePosition | None,
    fallback: ScorpionTrackVehiclePosition | None,
) -> ScorpionTrackVehiclePosition | None:
    """Prefer the primary position while filling any missing values from the fallback."""
    if primary is None:
        return fallback
    if fallback is None:
        return primary

    return ScorpionTrackVehiclePosition(
        latitude=primary.latitude if primary.latitude is not None else fallback.latitude,
        longitude=primary.longitude if primary.longitude is not None else fallback.longitude,
        timestamp=primary.timestamp if primary.timestamp is not None else fallback.timestamp,
        speed=primary.speed if primary.speed is not None else fallback.speed,
        speed_kmh=primary.speed_kmh if primary.speed_kmh is not None else fallback.speed_kmh,
        bearing=primary.bearing if primary.bearing is not None else fallback.bearing,
        accuracy=primary.accuracy if primary.accuracy is not None else fallback.accuracy,
        address=primary.address or fallback.address,
        ignition=primary.ignition if primary.ignition is not None else fallback.ignition,
        engine=primary.engine if primary.engine is not None else fallback.engine,
        gps_satellites=(
            primary.gps_satellites
            if primary.gps_satellites is not None
            else fallback.gps_satellites
        ),
        hdop=primary.hdop if primary.hdop is not None else fallback.hdop,
        raw_state=primary.raw_state or fallback.raw_state,
        friendly_state=primary.friendly_state or fallback.friendly_state,
        vehicle_voltage=(
            primary.vehicle_voltage
            if primary.vehicle_voltage is not None
            else fallback.vehicle_voltage
        ),
        odometer=primary.odometer if primary.odometer is not None else fallback.odometer,
        unit_type=primary.unit_type or fallback.unit_type,
        unit_id=primary.unit_id if primary.unit_id is not None else fallback.unit_id,
        distance_units=primary.distance_units or fallback.distance_units,
        units_speed=primary.units_speed or fallback.units_speed,
    )


def _derive_vehicle_status(
    raw_state: str | None,
    ignition: bool | None,
    engine: bool | None,
    speed_kmh: float | None,
) -> str | None:
    """Return a human-friendly vehicle status."""
    if raw_state == "ALM":
        return "alarm"
    if raw_state == "ALT":
        return "alert"

    if ignition:
        if speed_kmh is None or speed_kmh < 3:
            return "idle" if engine else "ignition"
        return "moving"

    if speed_kmh is not None:
        return "parked" if speed_kmh < 3 else "moving"

    return _clean_text(raw_state.lower() if raw_state else None)


def _window_is_active(
    start: datetime | None,
    end: datetime | None,
) -> bool:
    """Return True when the current time falls inside a scheduled window."""
    if start is None or end is None:
        return False
    now = datetime.now(UTC)
    return start <= now <= end


def _looks_like_login_page(final_url: str, text: str) -> bool:
    """Return True when the portal served the login page instead of data."""
    lowered = text.lower()
    return (
        "/home/login" in final_url
        or 'id="login_form"' in lowered
        or ('name="ci_csrf_token"' in lowered and 'name="pass"' in lowered)
    )


def _looks_like_login_error(text: str) -> bool:
    """Return True when the portal emitted its generic login failure page."""
    lowered = text.lower()
    return (
        '<h1 class="u-heading--dark">error</h1>'.lower() in lowered
        and ("user_model.php" in lowered or "go back to the" in lowered)
    )
