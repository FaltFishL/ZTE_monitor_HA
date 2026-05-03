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
    ):
        self.host = host
        self.username = username
        self.password = password
        self.reuse_session = reuse_session
        self.base = f"http://{host}"
        self.sess = requests.Session()
        self._logintoken: str = ""
        self._session_token: str = ""
        self._sid: Optional[str] = None
        self._login_time: float = 0.0
        self._last_data: dict[str, Any] = {}
        self._init_headers()

    def _init_headers(self) -> None:
        self.sess.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "Chrome/147.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

    @staticmethod
    def _ts() -> str:
        return str(int(time.time() * 1000))

    @staticmethod
    def _sha256(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    # ═══════════════════════════════════════════════════════
    # 登录 — 三步流程（你的测试已验证 [4][5]）
    # ═══════════════════════════════════════════════════════
    def login(self) -> bool:
        """三步加密登录，成功后 SID 自动写入 self.sess.cookies"""
        self._logintoken = ""
        self._session_token = ""

        # 第 1 步：GET initial_info_json → 提取 logintoken
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
            self._logintoken = env.get("logintoken", "")

            # 检查账号锁定
            err_key = f"{self.host}ErrNumEnv"
            err_val = env.get(err_key, "")
            if err_val:
                parts = err_val.split("_")
                if len(parts) >= 1 and parts[0] != "0":
                    return False
        except Exception:
            pass

        # 第 2 步：GET login_token_json → 提取 _sessionToken
        try:
            r = self.sess.get(
                f"{self.base}/",
                params={"_type": "loginsceneData", "_tag": "login_token_json"},
                headers={"Referer": f"{self.base}/"},
                timeout=10,
            )
            data = r.json()
            self._session_token = data.get("_sessionToken", "")
            lt = data.get("logintoken", "")
            if lt:
                self._logintoken = lt
        except Exception:
            pass

        # 第 3 步：POST login_entry → SHA256(密码) + 两个 token
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

        try:
            resp = r.json()
        except Exception:
            return False

        # 成功标识：result=="0" 或 login_need_refresh 存在
        if resp.get("result") == "0" or resp.get("login_need_refresh") is not None:
            self._login_time = time.time()
            for c in self.sess.cookies:
                if c.name in ("SID", "SID_HTTPS_"):
                    self._sid = c.value
            return True

        err_type = resp.get("loginErrType", "")
        return False if err_type else False

    def logout(self) -> None:
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
        """确保 SID 有效：复用 session 或重新登录"""
        from ..const import SESSION_MAX_AGE

        if self.reuse_session and self._sid:
            if time.time() - self._login_time < SESSION_MAX_AGE:
                return True
        return self.login()

    # ═══════════════════════════════════════════════════════
    # API 调用
    # ═══════════════════════════════════════════════════════
    def call_api(self, _type: str, _tag: str, **extra) -> Optional[requests.Response]:
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

    # ═══════════════════════════════════════════════════════
    # 便利数据提取
    # ═══════════════════════════════════════════════════════
    def get_connected_devices(self) -> list[dict[str, Any]]:
        data = self._last_data
        lan = data.get("lan_info", {})
        if isinstance(lan, str):
            lan = self._parse_xml(lan) or {}
        devs = lan.get("OBJ_LAN_INFO_ID", [])
        return [
            {
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
            }
            for d in devs
            if d.get("Active") == "1"
        ]

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
