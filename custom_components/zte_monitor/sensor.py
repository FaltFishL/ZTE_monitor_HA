"""ZTE Monitor HA - 传感器实体"""
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    async_add_entities([
        ZTERouterStatusSensor(coordinator, client, entry),
        ZTEConnectedDevicesSensor(coordinator, client, entry),
        ZTEWANStatusSensor(coordinator, client, entry),
    ])


class ZTERouterStatusSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:router-network"

    def __init__(self, coordinator, client, entry):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_router_status"

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
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "台"
    _attr_icon = "mdi:devices"

    def __init__(self, coordinator, client, entry):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_connected_devices"

    @property
    def native_value(self):
        try:
            return len(self._client.get_connected_devices())
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
    _attr_has_entity_name = True
    _attr_icon = "mdi:wan"

    def __init__(self, coordinator, client, entry):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_wan_status"

    @property
    def native_value(self):
        try:
            return self._client.get_wan_info().get("ipv4", "unknown")
        except Exception:
            return None

    @property
    def extra_state_attributes(self):
        try:
            return self._client.get_wan_info()
        except Exception:
            return {}
