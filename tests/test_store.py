import stat

import pytest

from ykb_mcp.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path)
    yield s
    s.close()


def test_credentials_roundtrip_and_permissions(store):
    assert store.credentials is None
    store.save_credentials({"token": "t", "secret": "s", "user_id": "u", "nickname": "n"})
    creds = store.credentials
    assert creds["token"] == "t" and creds["user_id"] == "u"
    mode = stat.S_IMODE((store.home / "credentials.json").stat().st_mode)
    assert mode == 0o600
    store.clear_credentials()
    assert store.credentials is None


def test_question_upsert_keeps_meta(store):
    store.upsert_question(
        {"id": "q1", "title": "题干", "identity_id": "201010", "subject_id": "s1", "chapter_id": "c1", "app_id": "40", "option": [{"key": "A"}], "is_collection_question": "1"}
    )
    store.upsert_question({"id": "q1", "title": "题干新"})
    q = store.get_question("q1")
    assert q["title"] == "题干新"
    assert q["identity_id"] == "201010"
    assert q["chapter_id"] == "c1"
    assert q["is_collection"] == 1


def test_answers_filters(store):
    store.upsert_answer({"question_id": "q1", "identity_id": "201010", "root_id": "20101", "answer": "A", "is_right": "0", "update_time": 100})
    store.upsert_answer({"question_id": "q2", "identity_id": "201010", "root_id": "20101", "answer": "B", "is_right": "1", "is_cut": True, "update_time": 200})
    store.upsert_answer({"question_id": "q3", "identity_id": "201011", "root_id": "20101", "answer": "", "is_right": "", "is_cut": True, "update_time": 300})
    assert len(store.answers()) == 3
    assert [r["question_id"] for r in store.answers(filter="wrong")] == ["q1"]
    assert {r["question_id"] for r in store.answers(filter="cut")} == {"q2", "q3"}
    assert [r["question_id"] for r in store.answers(filter="right")] == ["q2"]
    assert len(store.answers(identity_id="20101")) == 3
    assert len(store.answers(identity_id="201010")) == 2
    assert store.answer_identity("q1") == "201010"


def test_comments_categories_and_search(store):
    store.upsert_comment({"comment_id": "c1", "question_id": "q1", "content": "好题", "ctime_ts": 100}, "praise")
    store.upsert_comment({"comment_id": "c2", "question_id": "q1", "content": "我的想法", "ctime_ts": 200}, "my_comment")
    assert len(store.comments_list(category="praise")) == 1
    assert len(store.comments_list(category="my_comment")) == 1
    assert store.get_comment("c1")["content"] == "好题"
    hits = store.search("好题")
    assert len(hits["comments"]) == 1


def test_notes_and_collections(store):
    store.upsert_note({"id": "n1", "question_id": "q1", "content": "笔记", "ctime": 100, "imgs": [{"b_img": "x"}]})
    assert store.notes_list()[0]["content"] == "笔记"
    store.upsert_collection("q1", identity_id="201010", source="scan")
    assert store.collections_list()[0]["question_id"] == "q1"
    assert store.collections_list("201010")[0]["question_id"] == "q1"


def test_scan_queue_resume(store):
    store.scan_ensure("praise", ["q1", "q2", "q3"])
    store.scan_ensure("praise", ["q3", "q4"])
    assert store.scan_progress("praise") == {"total": 4, "done": 0, "remaining": 4}
    assert store.scan_pending("praise", 2) == ["q1", "q2"]
    store.scan_mark("praise", "q1")
    assert store.scan_pending("praise", 2) == ["q2", "q3"]
    assert store.scan_progress("praise")["remaining"] == 3


def test_kv_and_touched(store):
    store.kv_set("tree", [{"a": 1}])
    assert store.kv_get("tree") == [{"a": 1}]
    assert store.kv_get("missing") is None
    store.upsert_answer({"question_id": "q1", "identity_id": "i1"})
    store.upsert_question({"id": "q2"})
    store.upsert_note({"id": "n1", "question_id": "q3", "content": "x"})
    assert set(store.touched_questions()) == {"q1", "q2", "q3"}
    assert store.touched_questions("i1") == ["q1"]


def test_set_cut_updates_both_tables(store):
    store.upsert_question({"id": "q1", "title": "t"})
    store.upsert_answer({"question_id": "q1", "identity_id": "i1"})
    store.set_cut("q1", True)
    assert store.get_question("q1")["is_cut"] == 1
    assert store.answers()[0]["is_cut"] == 1
    store.set_cut("q1", False)
    assert store.get_question("q1")["is_cut"] == 0