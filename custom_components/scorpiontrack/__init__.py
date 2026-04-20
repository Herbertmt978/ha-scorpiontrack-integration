"""ScorpionTrack integration."""

from __future__ import annotations

from aiohttp import CookieJar
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import (
    async_create_clientsession,
    async_get_clientsession,
)

from .account_api import ScorpionTrackAccountClient
from .account_coordinator import ScorpionTrackAccountCoordinator
from .const import (
    CONF_SETUP_TYPE,
    CONF_SHARE_TOKEN,
    DOMAIN,
    PLATFORMS,
    SETUP_TYPE_ACCOUNT,
    SETUP_TYPE_SHARE,
)
from .share_api import ScorpionTrackClient as ScorpionTrackShareClient
from .share_coordinator import ScorpionTrackShareCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ScorpionTrack from a config entry."""
    entry_type = entry.data[CONF_SETUP_TYPE]

    if entry_type == SETUP_TYPE_ACCOUNT:
        session = async_create_clientsession(
            hass,
            cookie_jar=CookieJar(quote_cookie=False),
        )
        client = ScorpionTrackAccountClient(
            session=session,
            email=entry.data[CONF_EMAIL],
            password=entry.data[CONF_PASSWORD],
        )
        coordinator = ScorpionTrackAccountCoordinator(hass, client)
    elif entry_type == SETUP_TYPE_SHARE:
        client = ScorpionTrackShareClient(
            session=async_get_clientsession(hass),
            token=entry.data[CONF_SHARE_TOKEN],
        )
        coordinator = ScorpionTrackShareCoordinator(hass, client)
    else:  # pragma: no cover - defensive guard
        raise ValueError(f"Unsupported ScorpionTrack entry type: {entry_type}")

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "type": entry_type,
        "coordinator": coordinator,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
