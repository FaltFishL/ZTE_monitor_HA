# -*- coding: utf-8 -*-
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
        host="192.168.5.1",
        username="admin",
        password="",
        reuse_session=True,
        model="SR7410",
    ):
        self.host = host
        self.username = username
        self.password = password
        self.reuse_session = reuse_session
        self.model = model
        self.base = "http://" + host
        self.sess = requests.Session()
        self._login_token = ""
        self._session_token = ""
        self._sid = None  # type: Optional[str]
        self._login_time = 0.0
        self._last_data = {}  # type: dict
        self._guid_counter = int(time.time() * 1000)
        self._init_headers()

    def _init_headers(self):
        self.sess.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

    def _guid(self):
        """生成递增 GUID"""
        g = self._guid_counter
        self._guid_counter += 1
        return g

    @staticmethod
    def _sha256(text):
        """SHA256 哈希"""
        return hashlib.sha256(text.encode()).hexdigest()

    # ============================================================
    # 登录
    # ============================================================
    def login(self):
        """三步加密登录"""
        self._login_token = ""
        self._session_token = ""

        # 第 1 步: GET login_entry 获取 sess_token
        url1 = self.base + "/"
        try:
            r = self.sess.get(
                url1,
                params={"_type": "loginData", "_tag": "login_entry"},
                headers={"Referer": url1},
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

        # 第 2 步: GET login_token 获取 XML 中的 login_token
        try:
            r = self.sess.get(
                url1,
                params={
                    "_type": "loginData",
                    "_tag": "login_token",
                    "_": self._guid(),
                },
                headers={"Referer": url1},
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

        # 第 3 步: POST login_entry (SHA256(密码 + login_token))
        pass_hash = self._sha256(self.password + self._login_token)
        try:
            r = self.sess.post(
                url1,
                params={"_type": "loginData", "_tag": "login_entry"},
                data={
                    "action": "login",
                    "Password": pass_hash,
                    "Username": self.username,
                    "_sessionTOKEN": self._session_token,
                },
                headers={
                    "Referer": url1,
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

    def logout(self):
        """登出"""
        url1 = self.base + "/"
        try:
            self.sess.post(
                url1,
                params={"_type": "loginData", "_tag": "logout_entry"},
                data={"IF_LogOff": "1"},
                headers={"Referer": url1},
                timeout=10,
            )
        except Exception:
            pass
        self._sid = None
        self._login_time = 0.0

    def ensure_auth(self):
        """确保认证有效"""
        from ..const import SESSION_MAX_AGE
        if self.reuse_session and self._sid:
            if time.time() - self._login_time < SESSION_MAX_AGE:
                return True
        return self.login()

    # ============================================================
    # API 调用
    # ============================================================
    def call_api(self, _type, _tag, **extra):
        """统一 API 调用"""
        url1 = self.base + "/"
        params = {"_type": _type, "_tag": _tag, "_": self._guid()}
        params.update(extra)
        try:
            return self.sess.get(
                url1,
                params=params,
                headers={"Referer": url1},
                timeout=30,
            )
        except requests.RequestException:
            return None

    # ============================================================
    # 全量采集
    # ============================================================
    def fetch_all(self):
        """采集全部 API"""
        from ..const import API_DEFINITIONS
        results = {}
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
    def _parse_xml(text):
        """XML 解析"""
        try:
            root = ET.fromstring(text)
            out = {}
            for el in root:
                tag = el.tag
                if (tag.startswith("OBJ_")
                        or tag.startswith("ID_")
                        or tag.startswith("LUA_")):
                    arr = []
                    for inst in el.findall("Instance"):
                        d = {}
                        kids = list(inst)
                        for i in range(0, len(kids), 2):
                            if (kids[i].tag == "ParaName"
                                    and i + 1 < len(kids)
                                    and kids[i + 1].tag == "ParaValue"):
                                d[kids[i].text] = kids[i + 1].text or ""
                        arr.append(d)
                    out[tag] = arr
            return out
        except ET.ParseError:
            return None

    def _safe_get(self, data):
        """安全获取 dict"""
        if isinstance(data, str):
            return self._parse_xml(data) or {}
        return data if isinstance(data, dict) else {}

    # ============================================================
    # 流量单位格式化
    # ============================================================
    @staticmethod
    def _format_bytes(b):
        """字节数 -> 可读字符串"""
        if b >= 1073741824:
            return "{:.2f} GB".format(b / 1073741824)
        elif b >= 1048576:
            return "{:.2f} MB".format(b / 1048576)
        elif b >= 1024:
            return "{:.2f} KB".format(b / 1024)
        else:
            return "{} B".format(b)

    @staticmethod
    def _format_speed(s):
        """速率值 -> 可读字符串"""
        if s >= 1000:
            return "{:.1f} MB/s".format(s / 1000)
        elif s > 0:
            return "{} KB/s".format(s)
        else:
            return "0"

    # ============================================================
    # 数据提取方法
    # ============================================================

    def get_connected_devices(self):
        """在线设备列表（含实时速率 + 累计流量）"""
        data = self._last_data
        devices = []

        lan = self._safe_get(data.get("lan_info", {}))
        for d in lan.get("OBJ_LAN_INFO_ID", []):
            if d.get("Active") == "1":
                bytes_recv = int(d.get("BytesReceived", "0"))
                bytes_sent = int(d.get("BytesSend", "0"))
                down_speed = int(d.get("DownloadSpeed", "0"))
                up_speed = int(d.get("UploadSpeed", "0"))

                conn_type = "LAN"
                if d.get("DirectBand", "0") != "0":
                    conn_type = "WLAN"

                # 安全获取 hostname，处理 &#32; 转义
                raw_host = d.get("HostName") or d.get("DevName") or "Unknown"
                # 替换 HTML 空格实体
                raw_host = raw_host.replace("&#32;", " ").replace("&nbsp;", " ")
                raw_host = raw_host.strip()

                devices.append({
                    "mac": d.get("MACAddress", ""),
                    "ip": d.get("IPAddress", ""),
                    "hostname": raw_host,
                    "connection_type": conn_type,
                    "band": d.get("DirectBand", ""),
                    "rssi": d.get("DirectRssi", "0"),
                    "parent_ap": d.get("ParentDeviceName", ""),
                    "interface": d.get("IFAliasName", ""),
                    "brand": d.get("Brand", ""),
                    "model": d.get("Model", ""),
                    "mlo_enabled": d.get("MLOEnable") == "1",
                    "inactive_time": d.get("InactiveTime", ""),
                    "link_time": d.get("LinkTime", ""),
                    "download_speed": down_speed,
                    "upload_speed": up_speed,
                    "download_speed_str": self._format_speed(down_speed),
                    "upload_speed_str": self._format_speed(up_speed),
                    "bytes_received": bytes_recv,
                    "bytes_sent": bytes_sent,
                    "bytes_total": bytes_recv + bytes_sent,
                    "bytes_received_str": self._format_bytes(bytes_recv),
                    "bytes_sent_str": self._format_bytes(bytes_sent),
                    "bytes_total_str": self._format_bytes(
                        bytes_recv + bytes_sent
                    ),
                })

        clients = self._safe_get(data.get("clients_brief", {}))
        for d in clients.get("OBJ_CLIENTS_ID", []):
            mac = d.get("MACAddress", "")
            already_added = False
            for dev in devices:
                if dev["mac"] == mac:
                    already_added = True
                    break
            if mac and not already_added:
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
                    "download_speed": 0,
                    "upload_speed": 0,
                    "download_speed_str": "0",
                    "upload_speed_str": "0",
                    "bytes_received": 0,
                    "bytes_sent": 0,
                    "bytes_total": 0,
                    "bytes_received_str": "0 B",
                    "bytes_sent_str": "0 B",
                    "bytes_total_str": "0 B",
                })
        return devices

    def get_router_info(self):
        """路由器基础信息"""
        data = self._last_data
        hd = self._safe_get(data.get("home_device", {}))
        env = (hd.get("OBJ_GLOBAL_ENV") or [{}])[0]
        basic = (hd.get("OBJ_HOME_BASICINFO_ID") or [{}])[0]
        di = self._safe_get(data.get("device_info", {}))
        devinfo = (di.get("OBJ_DEVINFO_ID") or [{}])[0] if di else {}
        init = data.get("initial_info", {}) or {}
        dt = init.get("data", {}) if isinstance(init, dict) else {}

        # 安全获取各字段
        title = (env.get("WEBTitle") or "").replace("&#32;", " ")
        model_name = (devinfo.get("ModelName") or "").replace("&#32;", " ")

        uptime_val = devinfo.get("UpTime")
        uptime_hours = 0
        if uptime_val:
            uptime_hours = int(uptime_val) // 3600

        return {
            "title": title,
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
            "model_name": model_name,
            "serial": devinfo.get("SerialNumber", ""),
            "hardware_ver": devinfo.get("HardwareVer", ""),
            "boot_ver": devinfo.get("BootVer", ""),
            "uptime_hours": uptime_hours,
            "cpu": dt.get("cpuName", ""),
            "ports": dt.get("DeviceSummary", ""),
        }

    def get_wan_info(self):
        """WAN 连接信息"""
        data = self._last_data
        wd = self._safe_get(data.get("wan_info", {}))
        wan = (wd.get("OBJ_ETHWANCIP_ID") or [{}])[0] if wd else {}

        uptime_val = wan.get("UpTime")
        online_min = 0
        if uptime_val:
            online_min = int(uptime_val) // 60

        return {
            "ipv4": wan.get("IPAddress", ""),
            "subnet_mask": wan.get("SubnetMask", ""),
            "gateway": wan.get("GateWay", ""),
            "mode": wan.get("WANCName", ""),
            "mtu": wan.get("MTU", ""),
            "nat": wan.get("IsNAT", ""),
            "mac": wan.get("WorkIFMac", ""),
            "online_minutes": online_min,
            "dns1": wan.get("DNS1", ""),
            "overridden_dns": wan.get("OverridedDNS1", ""),
            "ip_mode": wan.get("IpMode", ""),
            "ipv6_gua": wan.get("Gua1", ""),
            "ipv6_pd": wan.get("Pd", ""),
            "ipv6_dns": wan.get("Dns1v6", ""),
            "ipv6_overridden_dns": wan.get("OverridedDns1v6", ""),
        }

    def get_wifi_config(self):
        """WiFi 配置"""
        data = self._last_data
        hd = self._safe_get(data.get("home_device", {}))
        wifis = []
        pairs = [
            ("OBJ_WLANMAINSSID_ID", "主网络"),
            ("OBJ_WLANGUESTSSID_ID", "访客网络"),
        ]
        for cat, label in pairs:
            for w in hd.get(cat, []):
                wifis.append({
                    "type": label,
                    "band": w.get("CardBand", ""),
                    "ssid": w.get("ESSID", ""),
                    "beacon_type": w.get("BeaconType", ""),
                    "encryption": w.get("EncrypType", ""),
                })
        return wifis

    def get_mesh_topo(self):
        """Mesh 拓扑"""
        data = self._last_data
        topo = data.get("mesh_topo", {})
        if isinstance(topo, str):
            try:
                topo = _json.loads(topo)
            except Exception:
                topo = {}
        return topo if isinstance(topo, dict) else {}

    def get_acl_rules(self):
        """ACL 规则"""
        data = self._last_data
        acl = data.get("acl_rules", {})
        if isinstance(acl, str):
            try:
                acl = _json.loads(acl)
            except Exception:
                acl = {}
        if isinstance(acl, dict):
            inner = acl.get("data", {})
            if isinstance(inner, dict):
                return inner.get("OBJ_ACLCFG_ID") or []
            return acl.get("OBJ_ACLCFG_ID") or []
        return []

    def get_ntp_info(self):
        """NTP 时间"""
        data = self._last_data
        nt = self._safe_get(data.get("ntp_info", {}))
        ntp = (nt.get("OBJ_SNTP_ID") or [{}])[0] if nt else {}
        return {
            "current_time": ntp.get("CurrentLocalTime", ""),
            "zone": ntp.get("ZoneIndex", ""),
        }

    def get_user_config(self):
        """用户配置"""
        data = self._last_data
        uc = data.get("user_config", {})
        if isinstance(uc, str):
            try:
                uc = _json.loads(uc)
            except Exception:
                uc = {}
        return uc if isinstance(uc, dict) else {}

    def get_offline_devices(self):
        """最近离线设备"""
        data = self._last_data
        lan = self._safe_get(data.get("lan_info", {}))
        devs = lan.get("OBJ_LAN_INFO_ID", [])
        offline = []
        for d in devs:
            if d.get("Active") == "0" and d.get("InactiveTime"):
                offline.append(d)
        offline.sort(key=lambda d: d.get("InactiveTime", ""), reverse=True)
        return offline[:20]
