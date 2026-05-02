"""ZTE Monitor HA - 传感器实体"""
import logging

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    client = hass.data[DOMAIN][entry.entry_id]["client"]

    entities = [
        ZTERouterStatusSensor(coordinator, client, entry),
        ZTEConnectedDevicesSensor(coordinator, client, entry),
        ZTEWANStatusSensor(coordinator, client, entry),
    ]
    async_add_entities(entities)


class ZTERouterStatusSensor(CoordinatorEntity, SensorEntity):
    """路由器状态传感器（含完整属性）"""
    _attr_has_entity_name = True

    def __init__(self, coordinator, client, entry):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_router_status"
        self._attr_translation_key = "router_status"
        self._attr_icon = "mdi:router-network"

    @property
    def native_value(self):
        return "online" if self.coordinator.data else "unavailable"

    @property
    def extra_state_attributes(self):
        try:
            return self._client.get_router_info()
        except Exception:
            return {}


class ZTEConnectedDevicesSensor(CoordinatorEntity, SensorEntity):
    """在线设备数"""
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "台"
    _attr_icon = "mdi:devices"

    def __init__(self, coordinator, client, entry):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_connected_devices"
        self._attr_translation_key = "connected_devices"

    @property
    def native_value(self):
        try:
            devices = self._client.get_connected_devices()
            return len(devices)
        except Exception:
            return None

    @property
    def extra_state_attributes(self):
        try:
            devices = self._client.get_connected_devices()
            return {"devices": devices, "count": len(devices)}
        except Exception:
            return {}


class ZTEWANStatusSensor(CoordinatorEntity, SensorEntity):
    """WAN 状态传感器"""
    _attr_has_entity_name = True
    _attr_icon = "mdi:wan"

    def __init__(self, coordinator, client, entry):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_wan_status"
        self._attr_translation_key = "wan_status"

    @property
    def native_value(self):
        try:
            wan = self._client.get_wan_info()
            return wan.get("ipv4", "unknown")
        except Exception:
            return None

    @property
    def extra_state_attributes(self):
        try:
            return self._client.get_wan_info()
        except Exception:
            return {}
