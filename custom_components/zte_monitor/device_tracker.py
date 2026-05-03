"""ZTE Monitor HA - 设备追踪实体"""
from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, BAND_MAP


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    devices = client.get_connected_devices()
    async_add_entities([ZTEDeviceTracker(coordinator, client, entry, d["mac"]) for d in devices])


class ZTEDeviceTracker(CoordinatorEntity, ScannerEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, client, entry, mac: str):
        super().__init__(coordinator)
        self._client = client
        self._mac = mac
        self._attr_unique_id = f"{entry.entry_id}_device_{mac.replace(':', '').replace('-', '')}"
        self._attr_name = f"ZTE {mac}"

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
                        "ip": d.get("ip"),
                        "hostname": d.get("hostname"),
                        "connection_type": d.get("connection_type"),
                        "band": BAND_MAP.get(d.get("band", "0"), d.get("band")),
                        "rssi": d.get("rssi"),
                        "brand": d.get("brand"),
                        "model": d.get("model"),
                        "mlo_enabled": d.get("mlo_enabled"),
                    }
        except Exception:
            pass
        return {}
