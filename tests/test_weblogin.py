import asyncio
import urllib.parse

import httpx
import pytest

from ykb_mcp.client import YkbClient
from ykb_mcp.store import Store
from ykb_mcp.weblogin import WebLoginManager, WebLoginSession


def login_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(urllib.parse.parse_qsl(request.content.decode()))
        if params.get("password") == "e10adc3949ba59abbe56e057f20f883e":
            return httpx.Response(
                200,
                json={
                    "code": "200",
                    "data": {"token": "t", "secret": "s", "user_id": "u1", "nickname": "昵称"},
                },
            )
        return httpx.Response(200, json={"code": "400", "message": "密码错误"})

    return httpx.MockTransport(handler)


@pytest.fixture
async def env(tmp_path, monkeypatch):
    monkeypatch.setenv("YKB_MCP_NO_BROWSER", "1")
    store = Store(tmp_path)
    client = YkbClient(store, transport=login_transport(), min_interval=0, jitter=0)
    manager = WebLoginManager(client, store)
    yield manager, store
    await client.aclose()
    store.close()


async def post(url, mobile="13800000000", password="123456", headers=None):
    async with httpx.AsyncClient() as http:
        return await http.post(
            url, json={"mobile": mobile, "password": password}, headers=headers
        )


async def test_page_served_and_login_success(env):
    manager, store = env
    info = await manager.start()
    url = info["url"]
    assert url.startswith("http://127.0.0.1:")
    async with httpx.AsyncClient() as http:
        page = await http.get(url)
        assert page.status_code == 200
        assert "医考帮登录" in page.text
        assert page.headers["cache-control"] == "no-store"
        bad = await http.get(url.rsplit("/", 1)[0] + "/wrong-token")
        assert bad.status_code == 404
    r = await post(url)
    assert r.json()["ok"] is True
    assert store.credentials["user_id"] == "u1"
    result = await manager.wait(timeout=1)
    assert result["ok"] is True and result["user_id"] == "u1"
    status = manager.status()
    assert status["logged_in"] is True


async def test_wrong_password_retry(env):
    manager, store = env
    info = await manager.start()
    r = await post(info["url"], password="bad")
    assert r.json()["ok"] is False
    assert "密码错误" in r.json()["error"]
    assert store.credentials is None
    r2 = await post(info["url"])
    assert r2.json()["ok"] is True
    assert store.credentials is not None


async def test_failure_limit_closes_page(env):
    manager, _ = env
    info = await manager.start()
    for _ in range(WebLoginSession.MAX_FAILURES):
        r = await post(info["url"], password="bad")
        assert r.json()["ok"] is False
    r = await post(info["url"], password="bad")
    assert r.status_code == 403
    await asyncio.sleep(0.5)
    assert manager._session.alive is False
    result = await manager.wait(timeout=1)
    assert result["ok"] is False
    assert "失败次数过多" in result["error"]


async def test_host_header_rejected(env):
    manager, _ = env
    info = await manager.start()
    r = await post(info["url"], headers={"Host": "evil.com"})
    assert r.status_code == 404
    async with httpx.AsyncClient() as http:
        page = await http.get(info["url"], headers={"Host": "evil.com"})
        assert page.status_code == 404


async def test_wait_blocks_until_browser_login(env):
    manager, store = env
    info = await manager.start()
    task = asyncio.create_task(manager.wait(timeout=10))
    await asyncio.sleep(0.1)
    r = await post(info["url"])
    assert r.json()["ok"] is True
    result = await task
    assert result["ok"] is True
    assert store.credentials["token"] == "t"


async def test_pending_then_status(env):
    manager, _ = env
    info = await manager.start()
    pending = await manager.wait(timeout=0)
    assert pending["pending"] is True
    assert pending["url"] == info["url"]
    status = manager.status()
    assert status["pending"] is True and status["logged_in"] is False
    await post(info["url"])
    assert manager.status()["logged_in"] is True


async def test_expire_closes(env):
    manager, _ = env
    await manager.start()
    manager._session._expire()
    result = await manager.wait(timeout=1)
    assert result["ok"] is False
    assert "已关闭" in result["error"]
    info2 = await manager.start()
    assert info2["already_running"] is False


async def test_status_without_session(env):
    manager, _ = env
    status = manager.status()
    assert status["logged_in"] is False and status["pending"] is False


async def test_relogin_after_success(env):
    manager, store = env
    info = await manager.start()
    await post(info["url"])
    await asyncio.sleep(0.5)
    info2 = await manager.start()
    assert info2["already_running"] is False
    assert info2["url"] != info["url"]
    r = await post(info2["url"])
    assert r.json()["ok"] is True