import time

from .crypto import decrypt_json
from .errors import ApiError
from .meta import outer_identity
from .store import Store, _i, _s

COMMENT_SORTS = {"likes": "", "hot": "recommend", "replies": "replies", "newest": "newst"}


def normalize_comment(raw: dict, question_id: str = "") -> dict:
    reply = raw.get("reply") if isinstance(raw.get("reply"), list) else []
    return {
        "comment_id": _s(raw.get("id")),
        "question_id": question_id or _s(raw.get("obj_id")),
        "user_id": _s(raw.get("user_id")),
        "nickname": _s(raw.get("nickname")),
        "avatar": _s(raw.get("avatar")),
        "school": _s(raw.get("school")),
        "content": _s(raw.get("content")),
        "praise_num": _i(raw.get("praise_num")),
        "oppose_num": _i(raw.get("oppose_num")),
        "replies": _i(raw.get("replies", raw.get("reply_num", 0))),
        "floor_num": _s(raw.get("floor_num"), "1"),
        "ctime": _s(raw.get("ctime")),
        "ctime_ts": _i(raw.get("ctime_timestamp")),
        "img_watermark": _s(raw.get("img_watermark")),
        "imgs": _s(raw.get("imgs")),
        "is_praise": _s(raw.get("is_praise"), "0"),
        "is_author": _s(raw.get("is_author"), "0"),
        "reply": reply,
    }


def harvest_comments(store: Store, comments: list[dict], question_id: str, current_user_id: str):
    for c in comments:
        if not c.get("comment_id"):
            continue
        if c.get("is_praise") == "1":
            store.upsert_comment(c, "praise")
        if c.get("is_author") == "1" or (
            current_user_id and c.get("user_id") == current_user_id
        ):
            store.upsert_comment(c, "my_comment")


def _comment_list_params(meta: dict, question_id: str, page: int, extra: dict | None = None) -> dict:
    params = {
        "subject_id": meta["subject_id"],
        "obj_id": question_id,
        "is_svip": "0",
        "module_type": "1",
        "identity_id": outer_identity(meta),
        "is_vip": "0",
        "comment_type": "2",
        "break_point": str(int(time.time())),
        "page": str(page),
        "app_id": meta["app_id"],
    }
    if extra:
        params.update(extra)
    return params


def _extract_comment_list(data) -> list[dict]:
    if not isinstance(data, dict):
        return []
    raws = []
    for key in ("hot", "time_line"):
        part = data.get(key)
        if isinstance(part, list):
            raws.extend(part)
    return [r for r in raws if isinstance(r, dict)]


async def pull_hot_comments(client, store: Store, question_id: str, meta: dict, sort: str = "likes", page: int = 1) -> list[dict]:
    params = _comment_list_params(meta, question_id, page, {"type": COMMENT_SORTS.get(sort, "")})
    resp = await client.request("/comment/main/hot", params)
    code = str(resp.get("code", ""))
    if code != "200":
        raise ApiError(code, str(resp.get("message") or "评论拉取失败"))
    items: list[dict] = []
    seen: set[str] = set()
    for raw in _extract_comment_list(resp.get("data")):
        c = normalize_comment(raw, question_id)
        cid = c["comment_id"]
        if not cid or cid in seen:
            continue
        seen.add(cid)
        items.append(c)
        store.upsert_comment(c, "hot")
    creds = store.credentials or {}
    harvest_comments(store, items, question_id, creds.get("user_id", ""))
    return items


async def pull_my_comments(client, store: Store, question_id: str, meta: dict, func: str) -> list[dict]:
    if func not in ("mypraise", "mycomment"):
        raise ValueError(f"未知 func: {func}")
    params = _comment_list_params(meta, question_id, 1, {"func": func})
    resp = await client.request("/Comment/Main/list", params)
    code = str(resp.get("code", ""))
    if code != "200":
        raise ApiError(code, str(resp.get("message") or "我的评论/点赞拉取失败"))
    category = "praise" if func == "mypraise" else "my_comment"
    items: list[dict] = []
    seen: set[str] = set()
    for raw in _extract_comment_list(resp.get("data")):
        c = normalize_comment(raw, question_id)
        cid = c["comment_id"]
        if not cid or cid in seen:
            continue
        seen.add(cid)
        items.append(c)
        store.upsert_comment(c, category)
    return items


async def pull_notes(client, store: Store, question_id: str, meta: dict, page: int = 1, size: int = 20) -> list[dict]:
    params = {
        "question_id": question_id,
        "subject_id": meta["subject_id"],
        "identity_id": meta["identity_id"],
        "app_id": meta["app_id"],
        "module_type": "1",
        "page": str(page),
        "size": str(size),
        "is_vip": "0",
        "is_svip": "0",
    }
    resp = await client.request("/allQuestion/Note/getNote", params, method="GET")
    code = str(resp.get("code", ""))
    if code != "200":
        raise ApiError(code, str(resp.get("message") or "笔记拉取失败"))
    data = resp.get("data")
    items: list[dict] = []
    if isinstance(data, list):
        for raw in data:
            if not isinstance(raw, dict):
                continue
            note = {
                "id": _s(raw.get("id")),
                "question_id": question_id,
                "content": _s(raw.get("content")),
                "ctime": _i(raw.get("ctime")),
                "imgs": raw.get("img") if isinstance(raw.get("img"), list) else [],
            }
            if note["id"]:
                store.upsert_note(note)
                items.append(note)
    return items


async def fetch_chapter_questions(
    client,
    store: Store,
    identity_id: str,
    chapter_id: str,
    app_id: str,
    module_type: str = "1",
    am_pm: str = "",
    subject_id: str = "",
) -> list[dict] | None:
    params = {
        "identity_id": identity_id,
        "primary_id": chapter_id,
        "category": "chapter",
        "type": "all",
        "module_type": module_type,
        "am_pm": am_pm,
        "app_id": app_id,
    }
    resp = await client.request("/allquestion/question/list", params)
    code = str(resp.get("code", ""))
    if code == "203":
        return None
    if code != "200":
        raise ApiError(code, str(resp.get("message") or "章节题目拉取失败"))
    data = resp.get("data")
    if isinstance(data, str):
        decoded = decrypt_json(data)
        raws = decoded.get("list") if isinstance(decoded, dict) else decoded
    elif isinstance(data, dict):
        raws = data.get("list")
    else:
        raws = data
    questions: list[dict] = []
    if isinstance(raws, list):
        for raw in raws:
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            q = dict(raw)
            q["identity_id"] = _s(raw.get("native_identity_id")) or identity_id
            q["subject_id"] = subject_id or _s(raw.get("chapter_parent_id"))
            q["chapter_id"] = chapter_id
            q["app_id"] = _s(raw.get("native_app_id")) or app_id
            store.upsert_question(q)
            questions.append(q)
    return questions


def parse_answer_record(raw: dict, identity_id: str, root_id: str) -> dict | None:
    if not isinstance(raw, dict):
        return None
    qid = _s(raw.get("question_id"))
    answer = _s(raw.get("answer"))
    is_right = _s(raw.get("is_right"))
    cut_raw = _s(raw.get("cut_question")) or _s(raw.get("is_cut"), "0")
    is_cut = cut_raw in ("1", "cutted")
    has_answer = bool(answer) and is_right in ("0", "1")
    if not qid or (not has_answer and not is_cut):
        return None
    ts = _i(raw.get("update_time") or raw.get("ctime") or raw.get("create_time"))
    if ts > 1000000000000:
        ts //= 1000
    return {
        "question_id": qid,
        "identity_id": identity_id,
        "root_id": root_id,
        "answer": answer,
        "is_right": is_right,
        "is_cut": is_cut,
        "duration": _i(raw.get("duration")),
        "remote_id": _s(raw.get("id")),
        "update_time": ts,
    }