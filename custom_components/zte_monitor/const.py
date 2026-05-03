"""ZTE Monitor HA - 常量定义"""
from typing import Final

DOMAIN: Final = "zte_monitor"

# ── 配置键 ──
CONF_HOST: Final = "host"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_MODEL: Final = "model"
CONF_REUSE_SESSION: Final = "reuse_session"
CONF_SCAN_WAN: Final = "scan_wan"
CONF_SCAN_ROUTER_DETAILS: Final = "scan_router_details"

# ── 默认值 ──
DEFAULT_HOST: Final = "192.168.5.1"
DEFAULT_USERNAME: Final = "admin"
DEFAULT_MODEL: Final = "SR7410"  # 默认型号：ZTE BE7200 Pro+
DEFAULT_REUSE_SESSION: Final = True
DEFAULT_SCAN_WAN: Final = True
DEFAULT_SCAN_ROUTER_DETAILS: Final = True

# ── 轮询间隔 ──
UPDATE_INTERVAL_FAST: Final = 30
UPDATE_INTERVAL_NORMAL: Final = 60
UPDATE_INTERVAL_SLOW: Final = 120
SESSION_MAX_AGE: Final = 300

# ── 全部 10 个 API ──
API_DEFINITIONS = [
    ("home_device",   "vueData",     "vue_home_device_data",      {}),
    ("wan_info",      "vueData",     "home_internetreg_lua",      {}),
    ("mesh_topo",     "vueData",     "vue_topo_data",             {}),
    ("clients_brief", "vueData",     "vue_client_data",           {}),
    ("lan_info",      "vueData",     "localnet_lan_info_lua",     {}),
    ("acl_rules",     "vuejsonData", "aclrule_data",              {}),
    ("device_info",   "vueData",     "home_managreg_lua",         {}),
    ("ntp_info",      "vueData",     "sntp_lua",                  {}),
    ("user_config",   "hiddenData",  "vue_userif_data",           {}),
    ("initial_info",  "hiddenScene", "initial_info_json",         {}),
]

BAND_MAP: Final = {"0": "有线/2.4G", "1": "5G-L", "2": "5G-H"}
