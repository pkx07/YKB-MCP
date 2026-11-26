import json

from ..errors import ApiError
from ..meta import get_tree
from ..pull import _s


async def ensure_tree(client, store, refresh: bool = False) -> list:
    tree = None if refresh else get_tree(store)
    if tree is None:
        creds = client.require_login()
        resp = await client.request(
            "/allQuestion/question/subjectV2",
            {"user_id": creds["user_id"]},
            method="GET",
        )
        if str(resp.get("code", "")) != "200":
            raise ApiError(str(resp.get("code", "")), "身份树拉取失败")
        tree = resp.get("data") or []
        store.kv_set("identity_tree", tree)
    return tree


def flatten_chapters(subjects) -> tuple[list[dict], dict[str, str]]:
    out: list[dict] = []
    chapter_subject: dict[str, str] = {}
    if not isinstance(subjects, list):
        return out, chapter_subject
    for subj in subjects:
        if not isinstance(subj, dict):
            continue
        sid = str(subj.get("chapter_id") or subj.get("id") or "")
        stitle = str(subj.get("title") or sid)
        chapters: list[dict] = []

        def walk(node: dict, path: list[str]):
            kids = node.get("children")
            nid = str(node.get("chapter_id") or node.get("id") or "")
            title = str(node.get("title") or nid)
            if isinstance(kids, list) and kids:
                for k in kids:
                    if isinstance(k, dict):
                        walk(k, [*path, title])
            elif nid:
                chapters.append(
                    {
                        "chapter_id": nid,
                        "title": title,
                        "path": " / ".join([*path, title]),
                        "count": int(node.get("count") or 0),
                        "updated_at": str(node.get("updated_at") or ""),
                    }
                )
                chapter_subject[nid] = sid

        kids = subj.get("children")
        if isinstance(kids, list) and kids:
            for k in kids:
                if isinstance(k, dict):
                    walk(k, [])
        else:
            walk(subj, [])
        out.append({"subject_id": sid, "subject_name": stitle, "chapters": chapters})
    return out, chapter_subject


async def ensure_chapters(client, store, identity_id: str, app_id: str = "", module_type: str = "", refresh: bool = False) -> list[dict]:
    from ..meta import find_node, flatten_identities

    cached = None if refresh else store.kv_get(f"chapters:{identity_id}")
    if cached is not None:
        return cached
    tree = await ensure_tree(client, store)
    nodes = flatten_identities(tree)
    node = find_node(nodes, identity_id)
    aid = app_id or (node.get("app_id") if node else "") or "40"
    mt = module_type or (node.get("module_type") if node else "") or "1"
    resp = await client.request(
        "/allquestion/question/chapter",
        {
            "identity_id": identity_id,
            "category": "chapter",
            "type": "all",
            "search_where": "[]",
            "module_type": mt,
            "app_id": aid,
            "am_pm": (node.get("am_pm") if node else "") or "",
        },
    )
    if str(resp.get("code", "")) != "200":
        raise ApiError(str(resp.get("code", "")), "章节目录拉取失败")
    subjects, chapter_subject = flatten_chapters(resp.get("data"))
    store.kv_set(f"chapters:{identity_id}", subjects)
    merged = store.kv_get("chapter_subject") or {}
    merged.update(chapter_subject)
    store.kv_set("chapter_subject", merged)
    return subjects


def _parse_option(option):
    if isinstance(option, str):
        try:
            return json.loads(option)
        except (ValueError, TypeError):
            return option
    return option or []


def format_question_raw(q: dict, full: bool = False) -> dict:
    out = {
        "id": _s(q.get("id")),
        "title": _s(q.get("title")),
        "type_str": _s(q.get("type_str")),
        "year": _s(q.get("year")),
        "answer": _s(q.get("answer")),
        "option": _parse_option(q.get("option")),
        "is_collection": _s(q.get("is_collection_question")) == "1",
        "is_cut": _s(q.get("cut_question")) in ("1", "cutted"),
        "user_answer": _s(q.get("user_answer")),
        "identity_id": _s(q.get("identity_id")),
        "subject_id": _s(q.get("subject_id")),
        "chapter_id": _s(q.get("chapter_id")),
        "app_id": _s(q.get("app_id")),
    }
    if full:
        out["explain"] = _s(q.get("explain"))
    return out


def format_question_row(row: dict, full: bool = True) -> dict:
    out = {
        "id": row.get("id", ""),
        "title": row.get("title", ""),
        "type_str": row.get("type_str", ""),
        "year": row.get("year", ""),
        "answer": row.get("answer", ""),
        "option": _parse_option(row.get("option_json")),
        "is_collection": bool(row.get("is_collection")),
        "is_cut": bool(row.get("is_cut")),
        "user_answer": row.get("user_answer", ""),
        "identity_id": row.get("identity_id", ""),
        "subject_id": row.get("subject_id", ""),
        "chapter_id": row.get("chapter_id", ""),
        "app_id": row.get("app_id", ""),
    }
    if full:
        out["explain"] = row.get("explain", "")
    return out