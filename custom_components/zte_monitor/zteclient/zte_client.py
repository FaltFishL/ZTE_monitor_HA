import hashlib
import json as _json
import time
import xml.etree.ElementTree as ET
from typing import Any, Optional

import requests


class ZTERouterClient:
    """ZTE 路由器 HTTP 客户端（与 zte_tracker 登录逻辑一致）"""

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
        """递增 GUID，与 zte_tracker 一致"""
        g = self._guid_counter
        self._guid_counter += 1
        return g

    @staticmethod
    def _sha256(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    # ═══════════════════════════════════════════════════════
    # 登录 — 与 zte_tracker 完全一致
    # ═══════════════════════════════════════════════════════
    def login(self) -> bool:
        """
        登录流程（与 zte_tracker SR7410/E2631 一致）:
          1. GET loginData&_tag=login_entry → JSON → sess_token
          2. GET loginData&_tag=login_token → XML  → login_token
          3. POST loginData&_tag=login_entry → SHA256(password+login_token)
        """
        # ── 第 1 步：GET login_entry 获取 sess_token ──
        try:
            r = self.sess.get(
                f"{self.base}/",
                params={"_type": "loginData", "_tag": "login_entry"},
                headers={"Referer": f"{self.base}/"},
                timeout=10,
            )
            data = r.json()
            locking = data.get("lockingTime", 1)
            if locking != 0:
                return False
            self._session_token = data.get("sess_token", "")
            if not self._session_token:
                return False
        except Exception:
            return False

        # ── 第 2 步：GET login_token 获取 XML 中的 login_token ──
        try:
            r = self.sess.get(
                f"{self.base}/",
                params={
                    "_type": "loginData",
                    "_tag": "login_token",
                    "_": self._guid(),
                },
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

        # ── 第 3 步：POST login_entry → SHA256(密码 + login_token) ──
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

        # ── 成功判定（与 zte_tracker 一致） ──
        locking = resp.get("lockingTime", 0)
        if locking == -1 or locking > 0:
            return False
        err_msg = resp.get("loginErrMsg", "")
        if err_msg and "password" in err_msg.lower():
            return False

        # 登录成功
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
    # 全量采集 — 使用 E2631/SR7410 的 vueData API
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

    # ═══════════════════════════════════════════════════════
    # 数据提取 — SR7410 使用 E2631 的 OBJ_LAN_INFO_ID 和 OBJ_CLIENTS_ID
    # ═══════════════════════════════════════════════════════
    def get_connected_devices(self) -> list[dict[str, Any]]:
        data = self._last_data
        devices: list[dict[str, Any]] = []

        # LAN 设备: OBJ_LAN_INFO_ID
        lan = data.get("lan_info", {})
        if isinstance(lan, str):
            lan = self._parse_xml(lan) or {}
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
                    "brand": d.get("Brand", ""),
                    "model": d.get("Model", ""),
                    "mlo_enabled": d.get("MLOEnable") == "1",
                })

        # WiFi 客户端: OBJ_CLIENTS_ID
        clients = data.get("clients_brief", {})
        if isinstance(clients, str):
            clients = self._parse_xml(clients) or {}
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
                    "brand": "",
                    "model": "",
                    "mlo_enabled": False,
                })

        return devices

    def get_router_info(self) -> dict[str, Any]:
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
        return {
            "title": (env.get("WEBTitle") or "").replace("&#32;", " "),
            "firmware": env.get("SoftwareVer", ""),
            "model_name": (devinfo.get("ModelName") or "").replace("&#32;", " "),
            "serial": devinfo.get("SerialNumber", ""),
            "uptime_hours": int(devinfo.get("UpTime", 0)) // 3600 if devinfo.get("UpTime") else 0,
            "connected_count": basic.get("AccessDevNum", ""),
        }

    def get_wan_info(self) -> dict[str, Any]:
        data = self._last_data
        wd = data.get("wan_info", {})
        if isinstance(wd, str):
            wd = self._parse_xml(wd) or {}
        wan = (wd.get("OBJ_ETHWANCIP_ID") or [{}])[0] if wd else {}
        return {
            "ipv4": wan.get("IPAddress", ""),
            "gateway": wan.get("GateWay", ""),
            "online_min": int(wan.get("UpTime", 0)) // 60 if wan.get("UpTime") else 0,
        }
