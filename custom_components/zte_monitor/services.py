"""ZTE Monitor HA - 服务（重启路由器）"""
import logging
from homeassistant.core import HomeAssistant, ServiceCall
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_services(hass: HomeAssistant) -> None:
    """注册重启服务"""

    async def reboot(call: ServiceCall) -> None:
        for entry_id, data in hass.data.get(DOMAIN, {}).items():
            client = data["client"]
            try:
                r = await hass.async_add_executor_job(
                    client.call_api, "menuData", "devmgr_restartmgr_lua.lua"
                )
                if r and r.status_code == 200:
                    _LOGGER.info("路由器重启命令已发送")
            except Exception as e:
                _LOGGER.error(f"重启失败: {e}")

    hass.services.async_register(DOMAIN, "reboot", reboot)
