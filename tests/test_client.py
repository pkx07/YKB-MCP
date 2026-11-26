import json
import urllib.parse

import httpx
import pytest

from ykb_mcp.client import YkbClient
from ykb_mcp.crypto import signature
from ykb_mcp.errors import ApiError, TokenExpiredError
from ykb_mcp.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path)
    yield s
    s.close()


def make_client(store, handler):
    return YkbClient(
        store, transport=httpx.MockTransport(handler), min_interval=0, jitter=0
    )


async def test_login_saves_credentials_and_headers(store):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["params"] = dict(urllib.parse.parse_qsl(request.content.decode()))
        return httpx.Response(
            200,
            json={
                "code": "200",
                "data": {"token": "t1", "secret": "s1", "user_id": "u1", "nickname": "昵称"},
            },
        )

    client = make_client(store, handler)
    data = await client.login("13800000000", "123456")
    assert data["user_id"] == "u1"
    assert store.credentials["token"] == "t1"
    assert captured["params"]["password"] == "e10adc3949ba59abbe56e057f20f883e"
    h = captured["headers"]
    assert h["app-type"] == "ykb"
    assert h["client-type"] == "android"
    assert h["app-version"] == "2801"
    assert h["uuid"] == "4f07ccb6e858592c"
    assert h["user-agent"] == "Redmi_23078RKD5C"
    assert h["signature"] == signature(h["timestamp"], captured["params"])
    await client.aclose()


async def test_request_injects_credentials_and_default_app_id(store):
    store.save_credentials({"token": "t", "secret": "s", "user_id": "u"})
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(urllib.parse.parse_qsl(request.content.decode()))
        return httpx.Response(200, json={"code": "200", "data": {}})

    client = make_client(store, handler)
    await client.request("/some/path", {"x": "1"})
    p = captured["params"]
    assert p["token"] == "t" and p["secret"] == "s" and p["user_id"] == "u"
    assert p["app_id"] == "1"
    await client.aclose()


async def test_get_uses_query_params(store):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        captured["method"] = request.method
        return httpx.Response(200, json={"code": "200", "data": []})

    client = make_client(store, handler)
    await client.request("/some/path", {"a": "b"}, method="GET")
    assert captured["method"] == "GET"
    assert captured["params"]["a"] == "b"
    await client.aclose()


async def test_309_clears_credentials(store):
    store.save_credentials({"token": "t", "secret": "s", "user_id": "u"})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": "309", "message": "会话过期"})

    client = make_client(store, handler)
    with pytest.raises(TokenExpiredError):
        await client.request("/some/path")
    assert store.credentials is None
    await client.aclose()


async def test_login_failure_raises(store):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": "400", "message": "密码错误"})

    client = make_client(store, handler)
    with pytest.raises(ApiError) as ei:
        await client.login("13800000000", "bad")
    assert ei.value.code == "400"
    assert store.credentials is None
    await client.aclose()


async def test_http_error_raises(store):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="oops")

    client = make_client(store, handler)
    with pytest.raises(ApiError) as ei:
        await client.request("/some/path")
    assert ei.value.code == "http_error"
    await client.aclose()