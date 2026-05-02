"""ZTE Monitor HA - Config Flow"""
import voluptuous as vol

from homeassistant import config_entries

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_MODEL,
    DEFAULT_HOST,
    DEFAULT_USERNAME,
    DEFAULT_MODEL,
)


class ZTEMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """UI 配置流程"""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            from .zteclient.zte_client import ZTERouterClient

            client = ZTERouterClient(
                host=user_input[CONF_HOST],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                reuse_session=False,
            )

            try:
                auth_ok = await self.hass.async_add_executor_job(client.login)
                if auth_ok:
                    await self.hass.async_add_executor_job(client.logout)
                    return self.async_create_entry(
                        title=f"ZTE Monitor ({user_input[CONF_HOST]})",
                        data=user_input,
                    )
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_MODEL, default=DEFAULT_MODEL): vol.In([
                    "SR7410", "F6640", "F6645P", "F680", "F6600P",
                    "H169A", "H2640", "H288A", "H388X",
                    "H3600P", "H3640", "H6645P", "AX3000", "E2631",
                ]),
            }),
            errors=errors,
        )
