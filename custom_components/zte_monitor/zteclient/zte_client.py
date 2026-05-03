import hashlib
import json as _json
import time
import xml.etree.ElementTree as ET
from typing import Any, Optional

import requests


class ZTERouterClient:
    """ZTE 路由器 HTTP 客户端"""

    def __init__(
        self,
        host: str = "192.168.5.1",
        username: str = "admin",
        password: str = "",
        reuse_session: bool = True,
        model: str = "SR7410",
    ):
        self.host = host
        self.username = username
        self.password = password
        self.reuse_session = reuse_session
        self.model = model
        self.base = f"http://{host}"
        self.sess = requests.Session()
        self._login_token: str = ""
        self._session_token: str = ""
        self._sid: Optional[str] = None
        self._login_time: float = 0.0
        self._last_data: dict[str, Any] = {}
        self._guid_counter = int(time.time() * 1000)
        self._init_headers()

    def _init_headers(self) -> None:
        self.sess.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

    def _guid(self) -> int:
        g = self._guid_counter
        self._guid_counter += 1
        return g

    @staticmethod
    def _sha256(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    # ═══════════════════════════════════════════════════════
    # 登录
    # ═══════════════════════════════════════════════════════
    def login(self) -> bool:
        self._login_token = ""
        self._session_token = ""

        try:
            r = self.sess.get(
                f"{self.base}/",
                params={"_type": "loginData", "_tag": "login_entry"},
                headers={"Referer": f"{self.base}/"},
                timeout=10,
            )
            data = r.json()
            if data.get("lockingTime", 1) != 0:
                return False
            self._session_token = data.get("sess_token", "")
            if not self._session_token:
                return False
        except Exception:
            return False

        try:
            r = self.sess.get(
                f"{self.base}/",
                params={"_type": "loginData", "_tag": "login_token", "_": self._guid()},
                headers={"Referer": f"{self.base}/"},
                timeout=10,
            )
            xml = ET.fromstring(r.content)
            if xml.tag != "ajax_response_xml_root":
                return False
            self._login_token = (xml.text or "").strip()
            if not self._login_token:
                return False
        except Exception:
            return False

        pass_hash = self._sha256(self.password + self._login_token)
        try:
            r = self.sess.post(
                f"{self.base}/",
                params={"_type": "loginData", "_tag": "login_entry"},
                data={
                    "action": "login",
                    "Password": pass_hash,
                    "Username": self.username,
                    "_sessionTOKEN": self._session_token,
                },
                headers={
                    "Referer": f"{self.base}/",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=15,
            )
            resp = r.json()
        except Exception:
            return False

        locking = resp.get("lockingTime", 0)
        if locking == -1 or locking > 0:
            return False
        err_msg = resp.get("loginErrMsg", "")
        if err_msg and "password" in err_msg.lower():
            return False

        self._login_time = time.time()
        for c in self.sess.cookies:
            if c.name in ("SID", "SID_HTTPS_"):
                self._sid = c.value
        return True

    def logout(self) -> None:
        try:
            self.sess.post(
                f"{self.base}/",
                params={"_type": "loginData", "_tag": "logout_entry"},
                data={"IF_LogOff": "1"},
                headers={"Referer": f"{self.base}/"},
                timeout=10,
            )
        except Exception:
            pass
        self._sid = None
        self._login_time = 0.0

    def ensure_auth(self) -> bool:
        from ..const import SESSION_MAX_AGE
        if self.reuse_session and self._sid:
            if time.time() - self._login_time < SESSION_MAX_AGE:
                return True
        return self.login()

    # ═══════════════════════════════════════════════════════
    # API 调用
    # ═══════════════════════════════════════════════════════
    def call_api(self, _type: str, _tag: str, **extra) -> Optional[requests.Response]:
        params = {"_type": _type, "_tag": _tag, "_": self._guid()}
        params.update(extra)
        try:
            return self.sess.get(
                f"{self.base}/",
                params=params,
                headers={"Referer": f"{self.base}/"},
                timeout=30,
            )
        except requests.RequestException:
            return None

    # ═══════════════════════════════════════════════════════
    # 全量采集
    # ═══════════════════════════════════════════════════════
    def fetch_all(self) -> dict[str, Any]:
        from ..const import API_DEFINITIONS
        results: dict[str, Any] = {}
        for name, typ, tag, extra in API_DEFINITIONS:
            r = self.call_api(_type=typ, _tag=tag, **extra)
            if r is None or r.status_code != 200:
                results[name] = None
                continue
            ct = r.headers.get("Content-Type", "")
            text = r.text
            if "<!DOCTYPE html>" in text or "<html" in text[:200].lower():
                results[name] = None
                continue
            if "json" in ct:
                try:
                    results[name] = r.json()
                except Exception:
                    results[name] = None
            elif "xml" in ct or text.strip().startswith("<"):
                results[name] = self._parse_xml(text)
            else:
                results[name] = None
        self._last_data = results
        return results

    @staticmethod
    def _parse_xml(text: str) -> Optional[dict[str, Any]]:
        try:
            root = ET.fromstring(text)
            out: dict[str, Any] = {}
            for el in root:
                tag = el.tag
                if tag.startswith(("OBJ_", "ID_", "LUA_")):
                    arr = []
                    for inst in el.findall("Instance"):
                        d = {}
                        kids = list(inst)
                        for i in range(0, len(kids), 2):
                            if kids[i].tag == "ParaName" and i + 1 < len(kids) and kids[i + 1].tag == "ParaValue":
                                d[kids[i].text] = kids[i + 1].text or ""
                        arr.append(d)
                    out[tag] = arr
            return out
        except ET.ParseError:
            return None

    def _safe_get(self, data: Any) -> dict[str, Any]:
        """安全转换数据为 dict"""
        if isinstance(data, str):
            return self._parse_xml(data) or {}
        return data if isinstance(data, dict) else {}

    # ═══════════════════════════════════════════════════════
    # 数据提取方法
    # ═══════════════════════════════════════════════════════

    def get_connected_devices(self) -> list[dict[str, Any]]:
        """在线设备列表（完整属性）"""
        data = self._last_data
        devices: list[dict[str, Any]] = []

        lan = self._safe_get(data.get("lan_info", {}))
        for d in lan.get("OBJ_LAN_INFO_ID", []):
            if d.get("Active") == "1":
                devices.append({
                    "mac": d.get("MACAddress", ""),
                    "ip": d.get("IPAddress", ""),
                    "hostname": d.get("HostName") or d.get("DevName") or "Unknown",
                    "connection_type": "WLAN" if d.get("DirectBand", "0") != "0" else "LAN",
                    "band": d.get("DirectBand", ""),
                    "rssi": d.get("DirectRssi", "0"),
                    "parent_ap": d.get("ParentDeviceName", ""),
                    "interface": d.get("IFAliasName", ""),
                    "brand": d.get("Brand", ""),
                    "model": d.get("Model", ""),
                    "mlo_enabled": d.get("MLOEnable") == "1",
                    "inactive_time": d.get("InactiveTime", ""),
                    "link_time": d.get("LinkTime", ""),
                })

        # WiFi 客户端补充
        clients = self._safe_get(data.get("clients_brief", {}))
        for d in clients.get("OBJ_CLIENTS_ID", []):
            mac = d.get("MACAddress", "")
            if mac and not any(dev["mac"] == mac for dev in devices):
                devices.append({
                    "mac": mac,
                    "ip": d.get("IPAddress", ""),
                    "hostname": d.get("HostName") or "Unknown",
                    "connection_type": "WLAN",
                    "band": d.get("Band", ""),
                    "rssi": d.get("RSSI", "0"),
                    "parent_ap": d.get("ParentAP", ""),
                    "interface": "",
                    "brand": "",
                    "model": "",
                    "mlo_enabled": False,
                    "inactive_time": "",
                    "link_time": "",
                })
        return devices

    def get_router_info(self) -> dict[str, Any]:
        """路由器基础信息（所有属性）"""
        data = self._last_data
        hd = self._safe_get(data.get("home_device", {}))
        env = (hd.get("OBJ_GLOBAL_ENV") or [{}])[0]
        basic = (hd.get("OBJ_HOME_BASICINFO_ID") or [{}])[0]

        di = self._safe_get(data.get("device_info", {}))
        devinfo = (di.get("OBJ_DEVINFO_ID") or [{}])[0] if di else {}

        init = data.get("initial_info", {}) or {}
        dt = init.get("data", {}) if isinstance(init, dict) else {}

        return {
            "title": (env.get("WEBTitle") or "").replace("&#32;", " "),
            "firmware": env.get("SoftwareVer", ""),
            "mode": env.get("Mode", ""),
            "mesh_enabled": env.get("MeshEnable", ""),
            "dual_band_sync": basic.get("DualBandSync", ""),
            "mlo_enabled": basic.get("MLOEnable", ""),
            "wan_speed": basic.get("WANSpeed", ""),
            "connected_count": basic.get("AccessDevNum", ""),
            "ap_count": basic.get("TopoAPNum", ""),
            "wan_status": basic.get("WANStatus", ""),
            "wan_up_rate": basic.get("WANUpRate", ""),
            "wan_down_rate": basic.get("WANDownRate", ""),
            "manufacturer": devinfo.get("ManuFacturer", ""),
            "model_name": (devinfo.get("ModelName") or "").replace("&#32;", " "),
            "serial": devinfo.get("SerialNumber", ""),
            "hardware_ver": devinfo.get("HardwareVer", ""),
            "boot_ver": devinfo.get("BootVer", ""),
            "uptime_hours": int(devinfo.get("UpTime", 0)) // 3600 if devinfo.get("UpTime") else 0,
            "cpu": dt.get("cpuName", ""),
            "ports": dt.get("DeviceSummary", ""),
        }

    def get_wan_info(self) -> dict[str, Any]:
        """WAN 连接信息"""
        data = self._last_data
        wd = self._safe_get(data.get("wan_info", {}))
        wan = (wd.get("OBJ_ETHWANCIP_ID") or [{}])[0] if wd else {}
        return {
            "ipv4": wan.get("IPAddress", ""),
            "subnet_mask": wan.get("SubnetMask", ""),
            "gateway": wan.get("GateWay", ""),
            "mode": wan.get("WANCName", ""),
            "mtu": wan.get("MTU", ""),
            "nat": wan.get("IsNAT", ""),
            "mac": wan.get("WorkIFMac", ""),
            "online_minutes": int(wan.get("UpTime", 0)) // 60 if wan.get("UpTime") else 0,
            "dns1": wan.get("DNS1", ""),
            "overridden_dns": wan.get("OverridedDNS1", ""),
            "ip_mode": wan.get("IpMode", ""),
            "ipv6_gua": wan.get("Gua1", ""),
            "ipv6_pd": wan.get("Pd", ""),
            "ipv6_dns": wan.get("Dns1v6", ""),
            "ipv6_overridden_dns": wan.get("OverridedDns1v6", ""),
        }

    def get_wifi_config(self) -> list[dict[str, Any]]:
        """WiFi 主网络 + 访客网络配置"""
        data = self._last_data
        hd = self._safe_get(data.get("home_device", {}))
        wifis = []
        for cat, label in [("OBJ_WLANMAINSSID_ID", "主网络"), ("OBJ_WLANGUESTSSID_ID", "访客网络")]:
            for w in hd.get(cat, []):
                wifis.append({
                    "type": label,
                    "band": w.get("CardBand", ""),
                    "ssid": w.get("ESSID", ""),
                    "beacon_type": w.get("BeaconType", ""),
                    "encryption": w.get("EncrypType", ""),
                })
        return wifis

    def get_mesh_topo(self) -> dict[str, Any]:
        """Mesh 组网拓扑"""
        data = self._last_data
        topo = data.get("mesh_topo", {})
        if isinstance(topo, str):
            try:
                topo = _json.loads(topo)
            except Exception:
                topo = {}
        return topo if isinstance(topo, dict) else {}

    def get_acl_rules(self) -> list[dict[str, Any]]:
        """ACL 访问控制规则"""
        data = self._last_data
        acl = data.get("acl_rules", {})
        if isinstance(acl, str):
            try:
                acl = _json.loads(acl)
            except Exception:
                acl = {}
        if isinstance(acl, dict):
            return acl.get("data", {}).get("OBJ_ACLCFG_ID") or acl.get("OBJ_ACLCFG_ID") or []
        return []

    def get_ntp_info(self) -> dict[str, Any]:
        """NTP 时间信息"""
        data = self._last_data
        nt = self._safe_get(data.get("ntp_info", {}))
        ntp = (nt.get("OBJ_SNTP_ID") or [{}])[0] if nt else {}
        return {
            "current_time": ntp.get("CurrentLocalTime", ""),
            "zone": ntp.get("ZoneIndex", ""),
        }

    def get_user_config(self) -> dict[str, Any]:
        """用户配置"""
        data = self._last_data
        uc = data.get("user_config", {})
        if isinstance(uc, str):
            try:
                uc = _json.loads(uc)
            except Exception:
                uc = {}
        return uc if isinstance(uc, dict) else {}

    def get_offline_devices(self) -> list[dict[str, Any]]:
        """最近离线设备"""
        data = self._last_data
        lan = self._safe_get(data.get("lan_info", {}))
        devs = lan.get("OBJ_LAN_INFO_ID", [])
        offline = [d for d in devs if d.get("Active") == "0" and d.get("InactiveTime")]
        offline.sort(key=lambda d: d.get("InactiveTime", ""), reverse=True)
        return offline[:20]
