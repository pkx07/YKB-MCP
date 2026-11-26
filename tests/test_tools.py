import json
import urllib.parse

import httpx
import pytest
from fastmcp import Client

from ykb_mcp.client import YkbClient
from ykb_mcp.crypto import encrypt_data
from ykb_mcp.server import create_app
from ykb_mcp.store import Store
from ykb_mcp.weblogin import WebLoginManager

TREE = [
    {
        "identity_id": "0",
        "title": "分组",
        "children": [
            {
                "identity_id": "20101",
                "title": "临床期末",
                "app_id": "40",
                "module_type": "1",
                "children": [
                    {"identity_id": "201010", "title": "内科学", "category": "chapter", "children": []},
                    {"identity_id": "201011", "title": "外科学", "category": "chapter", "children": []},
                ],
            }
        ],
    }
]

RECORDS = [
    {"id": "r1", "question_id": "588679", "answer": "A", "is_right": "0", "cut_question": "0", "update_time": "1700000000", "duration": "30"},
    {"id": "r2", "question_id": "588680", "answer": "B", "is_right": "1", "cut_question": "1", "update_time": "1700000100", "duration": "20"},
    {"id": "r3", "question_id": "588681", "answer": "", "is_right": "", "cut_question": "1", "update_time": "1700000200"},
]

SUBJECTS = [
    {
        "chapter_id": "s1",
        "title": "内科学",
        "children": [{"chapter_id": "c1", "title": "心血管", "count": 2, "updated_at": "1700000000"}],
    }
]

Q1 = {
    "id": "588679", "title": "测试题干1", "type": "1", "type_str": "A1", "year": "2023",
    "answer": "C", "option": [{"key": "A", "content": "选项A"}, {"key": "B", "content": "选项B"}],
    "explain": "解析1", "is_collection_question": "1", "cut_question": "0", "user_answer": "A",
    "native_identity_id": "201010", "native_app_id": "40",
}
Q2 = {
    "id": "588680", "title": "测试题干2", "type": "1", "type_str": "A1", "year": "2023",
    "answer": "B", "option": [], "explain": "解析2", "is_collection_question": "0",
    "cut_question": "1", "user_answer": "B", "native_identity_id": "201010", "native_app_id": "40",
}

C1 = {"id": "c1", "obj_id": "588679", "user_id": "u2", "content": "好题", "praise_num": "5", "oppose_num": "0", "replies": "1", "floor_num": "1", "ctime": "2天前", "ctime_timestamp": "1700000000", "nickname": "同学甲", "school": "温医大", "is_praise": "1", "is_author": "0", "reply": []}
C2 = {"id": "c2", "obj_id": "588679", "user_id": "u3", "content": "另一个评论", "praise_num": "1", "oppose_num": "0", "replies": "0", "floor_num": "2", "ctime": "1天前", "ctime_timestamp": "1700000050", "nickname": "同学乙", "school": "", "is_praise": "0", "is_author": "0", "reply": []}
C3 = {"id": "c3", "obj_id": "588679", "user_id": "u1", "content": "我的评论", "praise_num": "0", "oppose_num": "0", "replies": "0", "floor_num": "3", "ctime": "刚刚", "ctime_timestamp": "1700000200", "nickname": "我", "school": "", "is_praise": "0", "is_author": "1", "reply": []}

NOTE = {"id": "n1", "content": "笔记内容", "ctime": "1700000000", "img": [{"b_img": "http://x/b.png", "s_img": "http://x/s.png"}]}


def make_transport(state):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.replace("/index.php", "")
        if request.method == "POST":
            params = dict(urllib.parse.parse_qsl(request.content.decode()))
        else:
            params = dict(request.url.params)
        state["requests"].append({"path": path, "params": params})

        def ok(data):
            return httpx.Response(200, json={"code": "200", "data": data})

        if path == "/User/Main/login":
            if params.get("password") != "e10adc3949ba59abbe56e057f20f883e":
                return httpx.Response(200, json={"code": "400", "message": "密码错误"})
            return ok({"token": "t1", "secret": "s1", "user_id": "u1", "nickname": "测试昵称"})
        if state.get("expire"):
            return httpx.Response(200, json={"code": "309", "message": "会话过期"})
        if path == "/allQuestion/question/subjectV2":
            return ok(TREE)
        if path == "/allquestion/main/userAnswer":
            if params.get("category") == "collection":
                return ok([])
            return ok(RECORDS)
        if path == "/allquestion/question/chapter":
            return ok(SUBJECTS)
        if path == "/allquestion/question/list":
            if params.get("category") == "collection":
                return ok([])
            return ok(encrypt_data(json.dumps({"list": [Q1, Q2]}, ensure_ascii=False)))
        if path == "/allquestion/question/info":
            return httpx.Response(200, json={"code": "400", "message": "参数错误"})
        if path == "/comment/main/hot":
            return ok({"hot": [C1, C2], "time_line": [C3]})
        if path == "/Comment/Main/list":
            if params.get("func") == "mypraise":
                return ok({"hot": [C1], "time_line": []})
            return ok({"hot": [C3], "time_line": []})
        if path == "/allQuestion/Note/getNote":
            return ok([NOTE])
        if path == "/Comment/Main/praise":
            return ok({})
        if path == "/Comment/Main/publish":
            return ok({"id": "c9", "obj_id": params.get("obj_id"), "user_id": "u1", "content": params.get("content"), "is_author": "1", "ctime_timestamp": "1700000300"})
        if path == "/allQuestion/cutQuestion/cut":
            return ok({})
        return httpx.Response(200, json={"code": "404", "message": f"未知路径 {path}"})

    return httpx.MockTransport(handler)


@pytest.fixture
async def env(tmp_path, monkeypatch):
    monkeypatch.setenv("YKB_MCP_NO_BROWSER", "1")
    store = Store(tmp_path)
    state = {"requests": []}
    client = YkbClient(store, transport=make_transport(state), min_interval=0, jitter=0)
    manager = WebLoginManager(client, store)
    state["manager"] = manager
    mcp = create_app(store, client, manager)
    async with Client(mcp) as c:
        yield c, store, state
    await client.aclose()
    store.close()


async def call(c, name, args=None):
    result = await c.call_tool(name, args or {})
    return result.data


async def login(c):
    data = await call(c, "ykb_login", {"wait_seconds": 0})
    assert data.get("pending") is True
    async with httpx.AsyncClient() as http:
        r = await http.post(
            data["url"], json={"mobile": "13800000000", "password": "123456"}
        )
        assert r.json()["ok"] is True
    status = await call(c, "ykb_login_status")
    assert status["ok"] is True
    return status


async def test_login_and_whoami(env):
    c, store, _ = env
    data = await login(c)
    assert data["ok"] is True and data["user_id"] == "u1"
    who = await call(c, "ykb_whoami")
    assert who["logged_in"] is True
    assert who["nickname"] == "测试昵称"


async def test_requires_login(env):
    c, _, _ = env
    data = await call(c, "ykb_answer_records", {"identity_id": "20101"})
    assert data["ok"] is False
    assert "未登录" in data["error"]


async def test_identities_flattens_grouping(env):
    c, _, _ = env
    await login(c)
    data = await call(c, "ykb_identities")
    ids = {n["identity_id"]: n for n in data["identities"]}
    assert set(ids) == {"20101", "201010", "201011"}
    assert ids["20101"]["is_leaf"] is False
    assert ids["201010"]["is_leaf"] is True
    assert ids["201010"]["app_id"] == "40"
    assert ids["201010"]["path"] == "临床期末 / 内科学"


async def test_answer_records_wrong_and_cut(env):
    c, store, _ = env
    await login(c)
    wrong = await call(c, "ykb_answer_records", {"identity_id": "20101", "filter": "wrong"})
    assert wrong["leaves_checked"] == 2
    assert wrong["fetched"] == 6
    assert {r["question_id"] for r in wrong["records"]} == {"588679"}
    cut = await call(c, "ykb_answer_records", {"identity_id": "20101", "filter": "cut", "refresh": False})
    assert {r["question_id"] for r in cut["records"]} == {"588680", "588681"}
    assert cut["source"] == "cache"


async def test_chapters_and_chapter_questions(env):
    c, store, _ = env
    await login(c)
    ch = await call(c, "ykb_chapters", {"identity_id": "201010"})
    assert ch["chapter_count"] == 1
    assert ch["subjects"][0]["chapters"][0]["chapter_id"] == "c1"
    qs = await call(c, "ykb_chapter_questions", {"identity_id": "201010", "chapter_id": "c1"})
    assert qs["count"] == 2
    assert qs["questions"][0]["title"] == "测试题干1"
    assert qs["questions"][0]["is_collection"] is True
    row = store.get_question("588679")
    assert row["subject_id"] == "s1" and row["chapter_id"] == "c1"
    full = await call(c, "ykb_question", {"question_id": "588679"})
    assert full["source"] == "cache"
    assert full["question"]["explain"] == "解析1"


async def test_comments_and_harvest(env):
    c, store, _ = env
    await login(c)
    await call(c, "ykb_chapter_questions", {"identity_id": "201010", "chapter_id": "c1"})
    data = await call(c, "ykb_comments", {"question_id": "588679", "sort": "likes"})
    assert data["count"] == 3
    praise = store.comments_list(category="praise")
    mine = store.comments_list(category="my_comment")
    assert [x["comment_id"] for x in praise] == ["c1"]
    assert [x["comment_id"] for x in mine] == ["c3"]
    mp = await call(c, "ykb_my_praises", {"question_id": "588679"})
    assert mp["count"] == 1
    mc = await call(c, "ykb_my_comments", {"question_id": "588679"})
    assert mc["count"] == 1


async def test_global_praises_scan_and_resume(env):
    c, store, _ = env
    await login(c)
    await call(c, "ykb_answer_records", {"identity_id": "20101"})
    data = await call(c, "ykb_my_praises_all", {"scan_budget": 2})
    assert data["scanned_now"] == 2
    assert data["remaining"] == 1
    data2 = await call(c, "ykb_my_praises_all", {"scan_budget": 5})
    assert data2["remaining"] == 0
    assert any(x["comment_id"] == "c1" for x in data2["items"])
    comments_all = await call(c, "ykb_my_comments_all", {"scan_budget": 10})
    assert comments_all["remaining"] == 0
    assert any(x["comment_id"] == "c3" for x in comments_all["items"])


async def test_notes_and_notes_all(env):
    c, store, _ = env
    await login(c)
    await call(c, "ykb_chapter_questions", {"identity_id": "201010", "chapter_id": "c1"})
    data = await call(c, "ykb_notes", {"question_id": "588679"})
    assert data["count"] == 1
    assert data["items"][0]["imgs"][0]["b_img"] == "http://x/b.png"
    await call(c, "ykb_answer_records", {"identity_id": "20101"})
    all_notes = await call(c, "ykb_notes_all", {"scan_budget": 10})
    assert all_notes["remaining"] == 0
    assert len(all_notes["items"]) >= 1


async def test_sync_and_search_local(env):
    c, store, _ = env
    await login(c)
    await call(c, "ykb_answer_records", {"identity_id": "20101"})
    await call(c, "ykb_chapter_questions", {"identity_id": "201010", "chapter_id": "c1"})
    data = await call(c, "ykb_sync", {"scope": "all", "budget": 10})
    assert set(data["results"]) == {"praise", "mycomment", "notes"}
    assert all(r["progress"]["remaining"] == 0 for r in data["results"].values())
    hits = await call(c, "ykb_search_local", {"keyword": "测试题干"})
    assert len(hits["results"]["questions"]) == 2
    hits2 = await call(c, "ykb_search_local", {"keyword": "笔记", "kind": "notes"})
    assert len(hits2["results"]["notes"]) >= 1


async def test_collections_probe_and_scan(env):
    c, store, _ = env
    await login(c)
    probe = await call(c, "ykb_collections", {"refresh": True})
    assert probe["count"] == 0
    assert all(p["found"] == 0 for p in probe["probe"])
    scan = await call(c, "ykb_collections_scan", {"identity_id": "201010", "budget": 5})
    assert scan["found_new"] == 1
    assert scan["progress"]["remaining"] == 0
    assert scan["items"][0]["question_id"] == "588679"
    cached = await call(c, "ykb_collections")
    assert cached["source"] == "cache"


async def test_write_tools(env):
    c, store, _ = env
    await login(c)
    await call(c, "ykb_chapter_questions", {"identity_id": "201010", "chapter_id": "c1"})
    praise = await call(c, "ykb_praise_comment", {"comment_id": "c2", "question_id": "588679"})
    assert praise["ok"] is True
    assert store.get_comment("c2")["category"] == "praise"
    publish = await call(c, "ykb_publish_comment", {"question_id": "588679", "content": "新评论"})
    assert publish["ok"] is True and publish["comment_id"] == "c9"
    cut = await call(c, "ykb_cut_question", {"question_id": "588679", "cut": True})
    assert cut["ok"] is True
    assert store.get_question("588679")["is_cut"] == 1
    uncut = await call(c, "ykb_cut_question", {"question_id": "588679", "cut": False})
    assert uncut["ok"] is True
    assert store.get_question("588679")["is_cut"] == 0


async def test_token_expired_clears_credentials(env):
    c, store, state = env
    await login(c)
    state["expire"] = True
    data = await call(c, "ykb_answer_records", {"identity_id": "20101"})
    assert data["ok"] is False
    assert "309" in data["error"]
    assert store.credentials is None


async def test_logout(env):
    c, store, _ = env
    await login(c)
    await call(c, "ykb_logout")
    assert store.credentials is None