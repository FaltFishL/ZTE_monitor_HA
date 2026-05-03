"""ZTE Monitor HA - 设备追踪实体（名称用 hostname，属性含实时速率+累计流量）"""
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
    """ZTE 设备追踪实体 — 名称使用 hostname，属性包含完整设备信息+流量数据"""
    _attr_has_entity_name = True

    def __init__(self, coordinator, client, entry, device: dict):
        super().__init__(coordinator)
        self._client = client
        self._mac = device.get("mac", "")
        self._hostname = device.get("hostname", "") or self._mac
        self._attr_unique_id = f"{entry.entry_id}_device_{self._mac.replace(':', '').replace('-', '')}"
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
                        "download_speed": d.get("download_speed", 0),
                        "upload_speed": d.get("upload_speed", 0),
                        "download_speed_str": d.get("download_speed_str", "0"),
                        "upload_speed_str": d.get("upload_speed_str", "0"),
                        "bytes_received": d.get("bytes_received", 0),
                        "bytes_sent": d.get("bytes_sent", 0),
                        "bytes_total": d.get("bytes_total", 0),
                        "bytes_received_str": d.get("bytes_received_str", "0 B"),
                        "bytes_sent_str": d.get("bytes_sent_str", "0 B"),
                        "bytes_total_str": d.get("bytes_total_str", "0 B"),
                    }
        except Exception:
            pass
        return {}
