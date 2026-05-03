"""ZTE Monitor HA - 设备追踪实体（名称用 hostname，属性包含全部设备信息）"""
import logging

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, BAND_MAP

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    client = hass.data[DOMAIN][entry.entry_id]["client"]

    devices = client.get_connected_devices()
    entities = [
        ZTEDeviceTracker(coordinator, client, entry, d)
        for d in devices
    ]
    async_add_entities(entities)


class ZTEDeviceTracker(CoordinatorEntity, ScannerEntity):
    """ZTE 设备追踪实体 — 名称使用 hostname，属性包含完整设备信息"""
    _attr_has_entity_name = True

    def __init__(self, coordinator, client, entry, device: dict):
        super().__init__(coordinator)
        self._client = client
        self._mac = device.get("mac", "")
        self._hostname = device.get("hostname", "") or self._mac
        self._attr_unique_id = f"{entry.entry_id}_device_{self._mac.replace(':', '').replace('-', '')}"
        # 实体名称改用 hostname（回退到 MAC）
        self._attr_name = self._hostname

    @property
    def mac_address(self) -> str:
        return self._mac

    @property
    def source_type(self) -> SourceType:
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        try:
            for d in self._client.get_connected_devices():
                if d["mac"] == self._mac:
                    return True
        except Exception:
            pass
        return False

    @property
    def extra_state_attributes(self):
        """返回该设备的所有可用信息"""
        try:
            for d in self._client.get_connected_devices():
                if d["mac"] == self._mac:
                    return {
                        "mac": d.get("mac", ""),
                        "ip": d.get("ip", ""),
                        "hostname": d.get("hostname", ""),
                        "connection_type": d.get("connection_type", ""),
                        "band": BAND_MAP.get(d.get("band", "0"), d.get("band", "")),
                        "rssi": d.get("rssi", ""),
                        "parent_ap": d.get("parent_ap", ""),
                        "interface": d.get("interface", ""),
                        "brand": d.get("brand", ""),
                        "model": d.get("model", ""),
                        "mlo_enabled": d.get("mlo_enabled", False),
                        "inactive_time": d.get("inactive_time", ""),
                        "link_time": d.get("link_time", ""),
                    }
        except Exception:
            pass
        return {}
