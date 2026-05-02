"""
ZTE Router Client — 纯 requests，零浏览器依赖
================================================
三步登录 → 10 个 API → XML/JSON 双解析 → 会话管理

登录流程（已验证有效）:
  第 1 步: GET  hiddenScene/initial_info_json  → 提取 logintoken
  第 2 步: GET  login_token_json               → 提取 _sessionToken
  第 3 步: POST login_entry (SHA256(密码) + logintoken + _sessionToken)
           → 服务器返回认证成功 → 提取真实 SID cookie [4][5]
"""
import hashlib
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
    ):
        self.host = host
        self.username = username
        self.password = password
        self.reuse_session = reuse_session
        self.base = f"http://{host}"

        # ── 内部状态 ──
        self.sess = requests.Session()
        self._logintoken: str = ""
        self._session_token: str = ""
        self._sid: Optional[str] = None
        self._login_time: float = 0.0
        self._last_data: dict[str, Any] = {}

        self._init_headers()

    def _init_headers(self) -> None:
        """设置基础请求头"""
        self.sess.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "Chrome/147.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": f"{self.base}/",
        })

    # ═══════════════════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════════════════
    @staticmethod
    def _ts() -> str:
        return str(int(time.time() * 1000))

    @staticmethod
    def _sha256(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    # ═══════════════════════════════════════════════════════
    # 登录 — 三步流程（已验证有效 [4]）
    # ═══════════════════════════════════════════════════════
    def login(self) -> bool:
        """
        三步加密登录：
        1. GET initial_info_json  → 提取 logintoken
        2. GET login_token_json   → 提取 _sessionToken
        3. POST login_entry       → SHA256(密码) + 两个 token
                                  → 成功则 SID cookie 自动写入 self.sess
        """
        self._logintoken = ""
        self._session_token = ""

        # ── 第 1 步：获取 logintoken + 检查锁定状态 ──
        try:
            r = self.sess.get(
                f"{self.base}/",
                params={"_type": "hiddenScene", "_tag": "initial_info_json"},
                headers={"Referer": f"{self.base}/"},
                timeout=10,
            )
            info = r.json()
            data = info.get("data", {})
            env = data.get("OBJ_GLOBAL_ENV", {})

            # 提取 logintoken
            self._logintoken = env.get("logintoken", "")

            # 检查账号锁定
            err_key = f"{self.host}ErrNumEnv"
            err_val = env.get(err_key, "")
            if err_val:
                parts = err_val.split("_")
                if len(parts) >= 1 and parts[0] != "0":
                    # 账号被锁，放弃本次登录
                    return False
        except Exception:
            pass

        # ── 第 2 步：获取 _sessionToken ──
        try:
            r = self.sess.get(
                f"{self.base}/",
                params={"_type": "loginsceneData", "_tag": "login_token_json"},
                headers={"Referer": f"{self.base}/"},
                timeout=10,
            )
            data = r.json()
            self._session_token = data.get("_sessionToken", "")
            # 可能返回更新的 logintoken
            lt = data.get("logintoken", "")
            if lt:
                self._logintoken = lt
        except Exception:
            pass

        # ── 第 3 步：POST 密码登录 ──
        sha = self._sha256(self.password)

        r = self.sess.post(
            f"{self.base}/",
            params={"_type": "loginData", "_tag": "login_entry"},
            data={
                "Username": self.username,
                "Password": sha,
                "action": "login",
                "Frm_Logintoken": self._logintoken,
                "captchaCode": "",
                "_sessionTOKEN": self._session_token,
            },
            headers={
                "Referer": f"{self.base}/",
                "Origin": f"{self.base}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=15,
        )

        # ── 解析登录结果 ──
        try:
            resp = r.json()
        except Exception:
            return False

        # 登录成功的标识：result == "0" 或 login_need_refresh 存在 [4]
        if resp.get("result") == "0" or resp.get("login_need_refresh") is not None:
            self._login_time = time.time()
            # 从 session 提取真实 SID cookie
            for c in self.sess.cookies:
                if c.name in ("SID", "SID_HTTPS_"):
                    self._sid = c.value
            return True

        # 检查具体错误
        err_type = resp.get("loginErrType", "")
        if err_type:
            return False

        return False

    def logout(self) -> None:
        """登出，释放服务器端会话"""
        try:
            self.sess.get(
                f"{self.base}/",
                params={"_type": "loginData", "_tag": "logout_entry"},
                headers={"Referer": f"{self.base}/"},
                timeout=10,
            )
        except Exception:
            pass
        self._sid = None
        self._login_time = 0.0

    def ensure_auth(self) -> bool:
        """
        确保当前持有有效 SID。
        策略：
          1. 如果启用 session 复用且 SID 未超过 SESSION_MAX_AGE → 跳过登录
          2. 否则执行 login()
        """
        if self.reuse_session and self._sid:
            elapsed = time.time() - self._login_time
            if elapsed < SESSION_MAX_AGE:
                return True

        return self.login()

    # ═══════════════════════════════════════════════════════
    # 通用 API 调用
    # ═══════════════════════════════════════════════════════
    def call_api(self, _type: str, _tag: str, **extra) -> Optional[requests.Response]:
        """统一 API 调用，自动附加防缓存时间戳"""
        params = {"_type": _type, "_tag": _tag, "_": self._ts()}
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
    # 全量数据采集
    # ═══════════════════════════════════════════════════════
    def fetch_all(self) -> dict[str, Any]:
        """采集全部 API，返回结构化数据字典"""
        from ..const import API_DEFINITIONS

        results: dict[str, Any] = {}
        for name, typ, tag, extra in API_DEFINITIONS:
            r = self.call_api(_type=typ, _tag=tag, **extra)
            if r is None or r.status_code != 200:
                results[name] = None
                continue

            ct = r.headers.get("Content-Type", "")
            text = r.text

            # ── 检测 SID 过期（返回 HTML 登录页） ──
            if "<!DOCTYPE html>" in text or "<html" in text[:200].lower():
                results[name] = None
                continue

            # ── 按 Content-Type 解析 ──
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

    # ═══════════════════════════════════════════════════════
    # XML 解析
    # ═══════════════════════════════════════════════════════
    @staticmethod
    def _parse_xml(text: str) -> Optional[dict[str, Any]]:
        """XML → dict，展开 OBJ_/ID_/LUA_ 标签下的 Instance 数组"""
        try:
            root = ET.fromstring(text)
            out: dict[str, Any] = {}
            for el in root:
                tag = el.tag
                if tag.startswith("OBJ_") or tag.startswith("ID_") or tag.startswith("LUA_"):
                    arr = []
                    for inst in el.findall("Instance"):
                        d = {}
                        kids = list(inst)
                        for i in range(0, len(kids), 2):
                            if (
                                kids[i].tag == "ParaName"
                                and i + 1 < len(kids)
                                and kids[i + 1].tag == "ParaValue"
                            ):
                                d[kids[i].text] = kids[i + 1].text or ""
                        arr.append(d)
                    out[tag] = arr
            return out
        except ET.ParseError:
            return None

    # ═══════════════════════════════════════════════════════
    # 便利提取方法 — 全部 10 个 API 的数据结构化
    # ═══════════════════════════════════════════════════════

    def get_connected_devices(self) -> list[dict[str, Any]]:
        """在线设备列表（含品牌/型号/RSSI/MLO/AP归属）[6]"""
        data = self._last_data
        lan = data.get("lan_info", {})
        if isinstance(lan, str):
            lan = self._parse_xml(lan) or {}
        devs = lan.get("OBJ_LAN_INFO_ID", [])
        devices: list[dict[str, Any]] = []
        for d in devs:
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
        return devices

    def get_offline_devices(self) -> list[dict[str, Any]]:
        """最近离线设备"""
        data = self._last_data
        lan = data.get("lan_info", {})
        if isinstance(lan, str):
            lan = self._parse_xml(lan) or {}
        devs = lan.get("OBJ_LAN_INFO_ID", [])
        offline = [d for d in devs if d.get("Active") == "0" and d.get("InactiveTime")]
        offline.sort(key=lambda d: d.get("InactiveTime", ""), reverse=True)
        return offline[:20]

    def get_wifi_config(self) -> list[dict[str, Any]]:
        """WiFi 主网络 + 访客网络配置"""
        data = self._last_data
        hd = data.get("home_device", {})
        if isinstance(hd, str):
            hd = self._parse_xml(hd) or {}

        wifis = []
        for cat, label in [("OBJ_WLANMAINSSID_ID", "主"), ("OBJ_WLANGUESTSSID_ID", "访客")]:
            for w in hd.get(cat, []):
                wifis.append({
                    "type": label,
                    "band": w.get("CardBand", ""),
                    "ssid": w.get("ESSID", ""),
                    "beacon_type": w.get("BeaconType", ""),
                    "encryption": w.get("EncrypType", ""),
                })
        return wifis

    def get_router_info(self) -> dict[str, Any]:
        """路由器基础信息"""
        data = self._last_data

        hd = data.get("home_device", {})
        if isinstance(hd, str):
            hd = self._parse_xml(hd) or {}
        env = (hd.get("OBJ_GLOBAL_ENV") or [{}])[0]
        basic = (hd.get("OBJ_HOME_BASICINFO_ID") or [{}])[0]

        di = data.get("device_info", {})
        if isinstance(di, str):
            di = self._parse_xml(di) or {}
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
        wd = data.get("wan_info", {})
        if isinstance(wd, str):
            wd = self._parse_xml(wd) or {}
        wan = (wd.get("OBJ_ETHWANCIP_ID") or [{}])[0] if wd else {}
        return {
            "ipv4": wan.get("IPAddress", ""),
            "subnet": wan.get("SubnetMask", ""),
            "gateway": wan.get("GateWay", ""),
            "mode": wan.get("WANCName", ""),
            "mtu": wan.get("MTU", ""),
            "nat": wan.get("IsNAT", ""),
            "mac": wan.get("WorkIFMac", ""),
            "online_min": int(wan.get("UpTime", 0)) // 60 if wan.get("UpTime") else 0,
            "dns1": wan.get("DNS1", ""),
            "overridden_dns": wan.get("OverridedDNS1", ""),
            "ip_mode": wan.get("IpMode", ""),
            "ipv6_gua": wan.get("Gua1", ""),
            "ipv6_pd": wan.get("Pd", ""),
            "ipv6_dns": wan.get("Dns1v6", ""),
            "ipv6_overridden_dns": wan.get("OverridedDns1v6", ""),
        }

    def get_ntp_info(self) -> dict[str, Any]:
        """NTP 时间"""
        data = self._last_data
        nt = data.get("ntp_info", {})
        if isinstance(nt, str):
            nt = self._parse_xml(nt) or {}
        ntp = (nt.get("OBJ_SNTP_ID") or [{}])[0] if nt else {}
        return {
            "current_time": ntp.get("CurrentLocalTime", ""),
            "zone": ntp.get("ZoneIndex", ""),
        }

    def get_acl_rules(self) -> list[dict[str, Any]]:
        """ACL 规则"""
        data = self._last_data
        acl = data.get("acl_rules", {})
        if isinstance(acl, str):
            import json as _json
            try:
                acl = _json.loads(acl)
            except Exception:
                acl = {}
        if isinstance(acl, dict):
            return (acl.get("data", {}).get("OBJ_ACLCFG_ID")
                    or acl.get("OBJ_ACLCFG_ID")
                    or [])
        return []

    def get_mesh_topo(self) -> dict[str, Any]:
        """Mesh 拓扑"""
        data = self._last_data
        topo = data.get("mesh_topo", {})
        if isinstance(topo, str):
            import json as _json
            try:
                topo = _json.loads(topo)
            except Exception:
                topo = {}
        return topo if isinstance(topo, dict) else {}

    def get_user_config(self) -> dict[str, Any]:
        """用户配置"""
        data = self._last_data
        uc = data.get("user_config", {})
        return uc if isinstance(uc, dict) else {}
