"""Config flow for ScorpionTrack."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import CookieJar
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import (
    async_create_clientsession,
    async_get_clientsession,
)

from .account_api import (
    ScorpionTrackAccountClient,
    ScorpionTrackAuthError,
    ScorpionTrackConnectionError as ScorpionTrackAccountConnectionError,
    ScorpionTrackPortalError,
)
from .const import (
    CONF_SETUP_TYPE,
    CONF_SHARE_TOKEN,
    DOMAIN,
    SETUP_TYPE_ACCOUNT,
    SETUP_TYPE_SHARE,
)
from .share_api import (
    ScorpionTrackClient as ScorpionTrackShareClient,
    ScorpionTrackConnectionError as ScorpionTrackShareConnectionError,
    ScorpionTrackInvalidTokenError,
    ScorpionTrackShareUnavailableError,
)
from .utils import stable_hash

_LOGGER = logging.getLogger(__name__)


async def _async_validate_account_input(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> dict[str, str]:
    """Validate the provided account credentials."""
    session = async_create_clientsession(
        hass,
        cookie_jar=CookieJar(quote_cookie=False),
    )
    client = ScorpionTrackAccountClient(
        session=session,
        email=user_input[CONF_EMAIL],
        password=user_input[CONF_PASSWORD],
    )
    account = await client.async_refresh_account()

    unique_id = (
        str(account.user_id)
        if account.user_id is not None
        else stable_hash(account.email)
    )
    return {
        "email": account.email,
        "title": account.title,
        "unique_id": f"{SETUP_TYPE_ACCOUNT}_{unique_id}",
    }


async def _async_validate_share_input(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> dict[str, str]:
    """Validate the provided share token or URL."""
    client = ScorpionTrackShareClient(
        session=async_get_clientsession(hass),
        token=user_input[CONF_SHARE_TOKEN],
    )
    share = await client.async_get_share()

    if share.title:
        title = share.title
    elif share.vehicles:
        title = share.vehicles[0].display_name
    else:
        title = "ScorpionTrack Share"

    return {
        "token": share.token,
        "title": title,
        "unique_id": f"{SETUP_TYPE_SHARE}_{share.id}",
    }


class ScorpionTrackConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ScorpionTrack."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Let the user choose how to connect."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["account", "share"],
        )

    async def async_step_account(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the portal account flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _async_validate_account_input(self.hass, user_input)
            except ScorpionTrackAccountConnectionError:
                errors["base"] = "cannot_connect"
            except ScorpionTrackAuthError:
                errors["base"] = "invalid_auth"
            except ScorpionTrackPortalError:
                errors["base"] = "unexpected_response"
            except Exception:  # pragma: no cover - defensive logging
                _LOGGER.exception("Unexpected exception while validating ScorpionTrack account")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=info["title"],
                    data={
                        CONF_SETUP_TYPE: SETUP_TYPE_ACCOUNT,
                        CONF_EMAIL: info["email"],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        return self.async_show_form(
            step_id="account",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_share(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the shared-location flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _async_validate_share_input(self.hass, user_input)
            except ScorpionTrackShareConnectionError:
                errors["base"] = "cannot_connect"
            except ScorpionTrackInvalidTokenError:
                errors["base"] = "invalid_token"
            except ScorpionTrackShareUnavailableError:
                errors["base"] = "share_unavailable"
            except Exception:  # pragma: no cover - defensive logging
                _LOGGER.exception("Unexpected exception while validating ScorpionTrack share")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=info["title"],
                    data={
                        CONF_SETUP_TYPE: SETUP_TYPE_SHARE,
                        CONF_SHARE_TOKEN: info["token"],
                    },
                )

        return self.async_show_form(
            step_id="share",
            data_schema=vol.Schema({vol.Required(CONF_SHARE_TOKEN): str}),
            errors=errors,
        )
