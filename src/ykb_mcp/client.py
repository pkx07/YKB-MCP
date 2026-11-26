import asyncio
import os
import random
import time

import httpx

from .crypto import encrypt_password, signature
from .errors import ApiError, NotLoggedInError, TokenExpiredError
from .store import Store

ROOT_URL = "https://api.yikaobang.com.cn/index.php"
DEVICE_UUID = "4f07ccb6e858592c"
CHANNEL = "10000"
APP_VERSION = "2801"
USER_AGENT = "Redmi_23078RKD5C"


class YkbClient:
    def __init__(
        self,
        store: Store,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        min_interval: float | None = None,
        jitter: float | None = None,
    ):
        self.store = store
        self.min_interval = (
            float(os.environ.get("YKB_MCP_MIN_INTERVAL", "1.2"))
            if min_interval is None
            else min_interval
        )
        self.jitter = (
            float(os.environ.get("YKB_MCP_JITTER", "0.8"))
            if jitter is None
            else jitter
        )
        self._http = httpx.AsyncClient(
            timeout=25.0, transport=transport, follow_redirects=True
        )
        self._pace_lock = asyncio.Lock()
        self._last_request = 0.0

    async def _pace(self):
        if self.min_interval <= 0 and self.jitter <= 0:
            return
        async with self._pace_lock:
            now = time.monotonic()
            delay = (
                self._last_request
                + self.min_interval
                + random.uniform(0, self.jitter)
                - now
            )
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = time.monotonic()

    async def request(self, path: str, params: dict | None = None, method: str = "POST") -> dict:
        p = {k: str(v) for k, v in (params or {}).items() if v is not None}
        creds = self.store.credentials
        if creds:
            p["token"] = creds["token"]
            p["secret"] = creds.get("secret", "")
            p["user_id"] = creds["user_id"]
        if not p.get("app_id"):
            p["app_id"] = "1"
        ts = str(int(time.time()))
        headers = {
            "User-Agent": USER_AGENT,
            "Connection": "Keep-Alive",
            "timestamp": ts,
            "signature": signature(ts, p),
            "client-type": "android",
            "app-version": APP_VERSION,
            "uuid": DEVICE_UUID,
            "channel": CHANNEL,
            "app-type": "ykb",
        }
        await self._pace()
        url = ROOT_URL + path
        try:
            if method.upper() == "GET":
                resp = await self._http.get(url, params=p, headers=headers)
            else:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                resp = await self._http.post(url, data=p, headers=headers)
        except httpx.HTTPError as e:
            raise ApiError("network_error", f"网络请求失败: {e}") from e
        if resp.status_code != 200:
            raise ApiError("http_error", f"HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as e:
            raise ApiError("protocol_error", "响应不是有效 JSON") from e
        if not isinstance(data, dict):
            raise ApiError("protocol_error", "响应格式异常")
        if str(data.get("code", "")) == "309":
            self.store.clear_credentials()
            raise TokenExpiredError("登录已过期 (309)，请重新调用 ykb_login")
        return data

    async def login(self, mobile: str, password: str) -> dict:
        resp = await self.request(
            "/User/Main/login",
            {
                "beta_version": "0",
                "mobile": mobile,
                "password": encrypt_password(password),
                "app_id": "1",
            },
        )
        if str(resp.get("code")) != "200":
            raise ApiError(
                str(resp.get("code", "")),
                str(resp.get("message") or resp.get("msg") or "登录失败"),
            )
        data = resp.get("data") or {}
        if not isinstance(data, dict) or not all(
            data.get(k) for k in ("token", "secret", "user_id")
        ):
            raise ApiError("login_invalid_response", "登录响应缺少 token/secret/user_id")
        self.store.save_credentials(data)
        return data

    def require_login(self) -> dict:
        creds = self.store.credentials
        if not creds:
            raise NotLoggedInError("未登录，请先调用 ykb_login(mobile, password)")
        return creds

    async def aclose(self):
        await self._http.aclose()