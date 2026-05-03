"""ZTE Monitor HA - 传感器实体（全部 10 个 API 的数据）"""
import logging

from homeassistant.components.sensor import SensorEntity
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
        # 核心传感器
        ZTERouterStatusSensor(coordinator, client, entry),
        ZTEConnectedDevicesCountSensor(coordinator, client, entry),
        ZTEWANStatusSensor(coordinator, client, entry),
        # WiFi 配置
        ZTEWiFiConfigSensor(coordinator, client, entry),
        # Mesh 拓扑
        ZTEMeshTopoSensor(coordinator, client, entry),
        # ACL 规则
        ZTEACLRulesSensor(coordinator, client, entry),
        # NTP 时间
        ZTENTPTimeSensor(coordinator, client, entry),
        # 用户配置
        ZTEUserConfigSensor(coordinator, client, entry),
    ]
    async_add_entities(entities)


class ZTERouterStatusSensor(CoordinatorEntity, SensorEntity):
    """路由器状态传感器 — 包含所有路由器属性"""
    _attr_has_entity_name = True
    _attr_icon = "mdi:router-network"
    _attr_translation_key = "router_status"

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
            info = self._client.get_router_info()
            wifi = self._client.get_wifi_config()
            info["wifi_networks"] = wifi
            return info
        except Exception:
            return {}


class ZTEConnectedDevicesCountSensor(CoordinatorEntity, SensorEntity):
    """在线设备数量传感器 — 属性包含完整设备列表"""
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "台"
    _attr_icon = "mdi:devices"
    _attr_translation_key = "connected_devices"

    def __init__(self, coordinator, client, entry):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_connected_devices"

    @property
    def native_value(self):
        try:
            return len(self._client.get_connected_devices())
        except Exception:
            return 0

    @property
    def extra_state_attributes(self):
        try:
            online = self._client.get_connected_devices()
            offline = self._client.get_offline_devices()
            return {
                "online_devices": online,
                "online_count": len(online),
                "offline_devices": offline,
                "offline_count": len(offline),
            }
        except Exception:
            return {}


class ZTEWANStatusSensor(CoordinatorEntity, SensorEntity):
    """WAN 状态传感器 — 包含 IPv4/IPv6 全部信息"""
    _attr_has_entity_name = True
    _attr_icon = "mdi:wan"
    _attr_translation_key = "wan_status"

    def __init__(self, coordinator, client, entry):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_wan_status"

    @property
    def native_value(self):
        try:
            return self._client.get_wan_info().get("ipv4", "unknown")
        except Exception:
            return "unavailable"

    @property
    def extra_state_attributes(self):
        try:
            return self._client.get_wan_info()
        except Exception:
            return {}


class ZTEWiFiConfigSensor(CoordinatorEntity, SensorEntity):
    """WiFi 配置传感器 — 主网络和访客网络"""
    _attr_has_entity_name = True
    _attr_icon = "mdi:wifi"
    _attr_translation_key = "wifi_config"

    def __init__(self, coordinator, client, entry):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_wifi_config"

    @property
    def native_value(self):
        try:
            wifis = self._client.get_wifi_config()
            return f"{len(wifis)} 个网络"
        except Exception:
            return "unavailable"

    @property
    def extra_state_attributes(self):
        try:
            return {"networks": self._client.get_wifi_config()}
        except Exception:
            return {}


class ZTEMeshTopoSensor(CoordinatorEntity, SensorEntity):
    """Mesh 拓扑传感器"""
    _attr_has_entity_name = True
    _attr_icon = "mdi:access-point-network"
    _attr_translation_key = "mesh_topo"

    def __init__(self, coordinator, client, entry):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_mesh_topo"

    @property
    def native_value(self):
        try:
            topo = self._client.get_mesh_topo()
            return "已连接" if topo else "无数据"
        except Exception:
            return "unavailable"

    @property
    def extra_state_attributes(self):
        try:
            return self._client.get_mesh_topo()
        except Exception:
            return {}


class ZTEACLRulesSensor(CoordinatorEntity, SensorEntity):
    """ACL 规则传感器"""
    _attr_has_entity_name = True
    _attr_icon = "mdi:shield-key"
    _attr_translation_key = "acl_rules"

    def __init__(self, coordinator, client, entry):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_acl_rules"

    @property
    def native_value(self):
        try:
            rules = self._client.get_acl_rules()
            return f"{len(rules)} 条规则"
        except Exception:
            return "unavailable"

    @property
    def extra_state_attributes(self):
        try:
            return {"rules": self._client.get_acl_rules()}
        except Exception:
            return {}


class ZTENTPTimeSensor(CoordinatorEntity, SensorEntity):
    """NTP 时间传感器"""
    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-outline"
    _attr_translation_key = "ntp_time"

    def __init__(self, coordinator, client, entry):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_ntp_time"

    @property
    def native_value(self):
        try:
            return self._client.get_ntp_info().get("current_time", "")
        except Exception:
            return "unavailable"

    @property
    def extra_state_attributes(self):
        try:
            return self._client.get_ntp_info()
        except Exception:
            return {}


class ZTEUserConfigSensor(CoordinatorEntity, SensorEntity):
    """用户配置传感器"""
    _attr_has_entity_name = True
    _attr_icon = "mdi:account-cog"
    _attr_translation_key = "user_config"

    def __init__(self, coordinator, client, entry):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_user_config"

    @property
    def native_value(self):
        try:
            uc = self._client.get_user_config()
            return "已加载" if uc else "无数据"
        except Exception:
            return "unavailable"

    @property
    def extra_state_attributes(self):
        try:
            return self._client.get_user_config()
        except Exception:
            return {}
