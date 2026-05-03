"""ZTE Monitor HA - 集成入口"""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN, CONF_HOST, CONF_USERNAME, CONF_PASSWORD,
    CONF_REUSE_SESSION, DEFAULT_REUSE_SESSION, UPDATE_INTERVAL_NORMAL,
)
from .coordinator import ZTEMonitorCoordinator
from .zteclient.zte_client import ZTERouterClient

PLATFORMS = ["sensor", "device_tracker"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = ZTERouterClient(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        reuse_session=entry.options.get(CONF_REUSE_SESSION, DEFAULT_REUSE_SESSION),
    )
    coordinator = ZTEMonitorCoordinator(hass, client, UPDATE_INTERVAL_NORMAL)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"client": client, "coordinator": coordinator}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(data["client"].logout)
    return unload_ok
