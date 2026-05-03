"""ZTE Monitor HA - DataUpdateCoordinator"""
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL_FAST, UPDATE_INTERVAL_NORMAL, UPDATE_INTERVAL_SLOW

_LOGGER = logging.getLogger(__name__)


class ZTEMonitorCoordinator(DataUpdateCoordinator):
    """数据协调器——定时采集 + 自适应轮询"""

    def __init__(self, hass: HomeAssistant, client, scan_interval: int = UPDATE_INTERVAL_NORMAL):
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=scan_interval))
        self.client = client
        self._stable_count = 0
        self._prev_device_count = 0

    async def _async_update_data(self) -> dict:
        try:
            auth_ok = await self.hass.async_add_executor_job(self.client.ensure_auth)
            if not auth_ok:
                raise UpdateFailed("ZTE 路由器登录失败")
            data = await self.hass.async_add_executor_job(self.client.fetch_all)
            success = sum(1 for v in data.values() if v is not None)
            if success == 0:
                raise UpdateFailed("所有 API 均返回空数据，SID 可能已过期")
            self._adapt_interval()
            if not self.client.reuse_session:
                await self.hass.async_add_executor_job(self.client.logout)
            return data
        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"数据更新异常: {err}") from err

    def _adapt_interval(self) -> None:
        devices = self.client.get_connected_devices()
        current_count = len(devices)
        if current_count != self._prev_device_count:
            self._stable_count = 0
            self.update_interval = timedelta(seconds=UPDATE_INTERVAL_FAST)
        else:
            self._stable_count += 1
            if self._stable_count >= 5:
                self.update_interval = timedelta(seconds=UPDATE_INTERVAL_SLOW)
            elif self._stable_count >= 2:
                self.update_interval = timedelta(seconds=UPDATE_INTERVAL_NORMAL)
        self._prev_device_count = current_count
