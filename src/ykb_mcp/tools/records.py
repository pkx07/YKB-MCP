from ..crypto import decrypt_json
from ..errors import ApiError, YkbError
from ..meta import find_node, flatten_identities, leaf_identities
from ..pull import fetch_chapter_questions, parse_answer_record
from . import guard
from ._helpers import (
    ensure_chapters,
    ensure_tree,
    format_question_raw,
    format_question_row,
)


def register(mcp, client, store):
    @mcp.tool
    @guard
    async def ykb_answer_records(
        identity_id: str,
        filter: str = "all",
        app_id: str = "",
        refresh: bool = True,
        limit: int = 200,
    ) -> dict:
        """拉取账号在指定身份（题库）下的做题记录。filter: all=全部, wrong=错题, cut=已斩题, right=做对的题。记录含 question_id、我的答案、对错、已斩状态、用时、更新时间；写入本地缓存。identity_id 来自 ykb_identities，父身份自动展开为叶子身份逐个拉取（限速）。refresh=False 仅读缓存。"""
        client.require_login()
        if not refresh:
            rows = store.answers(filter=filter, identity_id=identity_id, limit=limit)
            return {
                "source": "cache",
                "identity_id": identity_id,
                "filter": filter,
                "returned": len(rows),
                "records": rows,
            }
        tree = await ensure_tree(client, store)
        nodes = flatten_identities(tree)
        leaves = leaf_identities(nodes, identity_id)
        fetched = 0
        restricted: list[str] = []
        for leaf in leaves:
            aid = app_id or leaf.get("app_id") or "40"
            resp = await client.request(
                "/allquestion/main/userAnswer",
                {
                    "app_id": aid,
                    "module_type": leaf.get("module_type") or "1",
                    "identity_id": leaf["identity_id"],
                    "category": "chapter",
                    "type": "all",
                    "is_vip": "0",
                    "is_svip": "0",
                },
                method="GET",
            )
            code = str(resp.get("code", ""))
            if code == "203":
                restricted.append(leaf["identity_id"])
                continue
            if code != "200":
                raise ApiError(
                    code,
                    f"身份 {leaf['identity_id']} 做题记录拉取失败: {resp.get('message', '')}",
                )
            data = resp.get("data")
            if not isinstance(data, list):
                continue
            for raw in data:
                rec = parse_answer_record(raw, leaf["identity_id"], identity_id)
                if rec:
                    store.upsert_answer(rec)
                    fetched += 1
        rows = store.answers(filter=filter, identity_id=identity_id, limit=limit)
        return {
            "identity_id": identity_id,
            "leaves_checked": len(leaves),
            "restricted_leaves": restricted,
            "fetched": fetched,
            "filter": filter,
            "returned": len(rows),
            "records": rows,
            "hint": "用 ykb_question(question_id) 获取题目内容；返回受 limit 限制，可调大",
        }

    @mcp.tool
    @guard
    async def ykb_chapters(
        identity_id: str, app_id: str = "", module_type: str = "", refresh: bool = False
    ) -> dict:
        """获取指定身份下的科目/章节目录（含每章题量），用于定位 ykb_chapter_questions 的 chapter_id。identity_id 建议用 ykb_identities 中的叶子身份或可选学科节点。"""
        client.require_login()
        subjects = await ensure_chapters(
            client, store, identity_id, app_id, module_type, refresh=refresh
        )
        total = sum(len(s["chapters"]) for s in subjects)
        return {"identity_id": identity_id, "subject_count": len(subjects), "chapter_count": total, "subjects": subjects}

    @mcp.tool
    @guard
    async def ykb_chapter_questions(
        identity_id: str,
        chapter_id: str,
        app_id: str = "",
        module_type: str = "1",
        am_pm: str = "",
        full: bool = False,
    ) -> dict:
        """拉取并解密一个章节的全部题目（题干、选项、答案、收藏/已斩标记），写入本地缓存。full=True 时额外包含解析（内容较长）。chapter_id 来自 ykb_chapters。无权限章节返回 203 提示。"""
        client.require_login()
        tree = await ensure_tree(client, store)
        nodes = flatten_identities(tree)
        node = find_node(nodes, identity_id)
        aid = app_id or (node.get("app_id") if node else "") or "40"
        subject_id = (store.kv_get("chapter_subject") or {}).get(chapter_id, "")
        questions = await fetch_chapter_questions(
            client, store, identity_id, chapter_id, aid, module_type, am_pm, subject_id
        )
        if questions is None:
            return {
                "ok": False,
                "error": "该章节无查看权限 (203)，可能需要 VIP 或购买题库",
                "chapter_id": chapter_id,
            }
        out = [format_question_raw(q, full=full) for q in questions]
        return {
            "identity_id": identity_id,
            "chapter_id": chapter_id,
            "count": len(out),
            "questions": out,
        }

    @mcp.tool
    @guard
    async def ykb_question(
        question_id: str, identity_id: str = "", chapter_id: str = "", app_id: str = ""
    ) -> dict:
        """获取单题完整内容（题干、选项、答案、解析）。优先读缓存；未命中时尝试官方 question/info 接口；提供 identity_id+chapter_id 可整章定位。"""
        client.require_login()
        row = store.get_question(question_id)
        if row and row.get("title"):
            return {"source": "cache", "question": format_question_row(row)}
        if chapter_id and identity_id:
            subject_id = (store.kv_get("chapter_subject") or {}).get(chapter_id, "")
            questions = await fetch_chapter_questions(
                client, store, identity_id, chapter_id, app_id or "40", subject_id=subject_id
            )
            for q in questions or []:
                if str(q.get("id")) == str(question_id):
                    return {"source": "chapter", "question": format_question_raw(q, full=True)}
        for key in ("question_id", "id"):
            params = {key: question_id, "app_id": app_id or "40", "module_type": "1"}
            if identity_id:
                params["identity_id"] = identity_id
            resp = await client.request("/allquestion/question/info", params)
            if str(resp.get("code", "")) != "200":
                continue
            data = resp.get("data")
            if isinstance(data, str):
                try:
                    data = decrypt_json(data)
                except (ValueError, TypeError):
                    continue
            if isinstance(data, dict):
                if isinstance(data.get("info"), dict):
                    data = data["info"]
                elif isinstance(data.get("list"), list) and data["list"]:
                    data = data["list"][0]
            if isinstance(data, dict) and (data.get("id") or data.get("title")):
                q = dict(data)
                q.setdefault("id", question_id)
                q["identity_id"] = str(q.get("native_identity_id") or identity_id)
                q["app_id"] = str(q.get("native_app_id") or app_id or "40")
                store.upsert_question(q)
                return {"source": "info", "question": format_question_raw(q, full=True)}
        return {
            "ok": False,
            "error": f"未获取到题目 {question_id}：请提供 identity_id 与 chapter_id，或先用 ykb_chapter_questions 拉取该题所在章节",
        }

    @mcp.tool
    @guard
    async def ykb_collections(identity_id: str = "", refresh: bool = False) -> dict:
        """获取账号收藏的题目。优先读本地缓存；refresh=True 时探测官方收藏列表接口（实验性）。探测不到时用 ykb_collections_scan 按章节扫描收藏标记。"""
        if not refresh:
            items = store.collections_list(identity_id or None)
            if items:
                return {"source": "cache", "count": len(items), "items": items}
        client.require_login()
        tree = await ensure_tree(client, store)
        nodes = flatten_identities(tree)
        if identity_id:
            leaves = leaf_identities(nodes, identity_id)
        else:
            leaves = [n for n in nodes if n["is_leaf"]]
        if not leaves:
            raise YkbError("身份树为空，无法探测收藏接口")
        leaf = leaves[0]
        aid = leaf.get("app_id") or "40"
        probes: list[dict] = []
        found_items: list[dict] = []
        variants = [
            (
                "/allquestion/main/userAnswer",
                {
                    "app_id": aid,
                    "module_type": "1",
                    "identity_id": leaf["identity_id"],
                    "category": "collection",
                    "type": "all",
                    "is_vip": "0",
                    "is_svip": "0",
                },
                "GET",
            ),
            (
                "/allquestion/question/list",
                {
                    "identity_id": leaf["identity_id"],
                    "primary_id": "",
                    "category": "collection",
                    "type": "all",
                    "module_type": "1",
                    "am_pm": "",
                    "app_id": aid,
                },
                "POST",
            ),
        ]
        for path, params, method in variants:
            resp = await client.request(path, params, method=method)
            code = str(resp.get("code", ""))
            data = resp.get("data")
            if isinstance(data, str):
                try:
                    data = decrypt_json(data)
                except (ValueError, TypeError):
                    data = None
            raws = None
            if isinstance(data, list):
                raws = data
            elif isinstance(data, dict) and isinstance(data.get("list"), list):
                raws = data["list"]
            count = 0
            if code == "200" and raws:
                for raw in raws:
                    if not isinstance(raw, dict):
                        continue
                    qid = str(raw.get("question_id") or raw.get("id") or "")
                    if not qid:
                        continue
                    count += 1
                    store.upsert_collection(
                        qid,
                        identity_id=identity_id or leaf["identity_id"],
                        subject_id=str(raw.get("subject_id") or ""),
                        chapter_id=str(raw.get("chapter_id") or ""),
                        source="probe",
                    )
                    if raw.get("title"):
                        q = dict(raw)
                        q.setdefault("id", qid)
                        store.upsert_question(q)
                    found_items.append(raw)
            probes.append({"path": path, "code": code, "found": count})
            if count:
                break
        store.kv_set("collection_probe", probes)
        items = store.collections_list(identity_id or None)
        return {
            "count": len(items),
            "items": items,
            "probe": probes,
            "hint": "若为空，运行 ykb_collections_scan(identity_id) 按章节扫描收藏标记（限速、可续跑）",
        }

    @mcp.tool
    @guard
    async def ykb_collections_scan(identity_id: str, budget: int = 10) -> dict:
        """按章节扫描指定身份下的收藏标记（is_collection_question），结果写入本地缓存。budget=本次最多扫描章节数（每章 1 请求，自动限速）；断点续传，重复调用直到 remaining=0。"""
        client.require_login()
        subjects = await ensure_chapters(client, store, identity_id)
        chapter_ids = [c["chapter_id"] for s in subjects for c in s["chapters"]]
        scope = f"collections:{identity_id}"
        store.scan_ensure(scope, chapter_ids)
        pending = store.scan_pending(scope, budget)
        chapter_subject = store.kv_get("chapter_subject") or {}
        tree = await ensure_tree(client, store)
        nodes = flatten_identities(tree)
        node = find_node(nodes, identity_id)
        aid = (node.get("app_id") if node else "") or "40"
        found_new = 0
        restricted = 0
        for chapter_id in pending:
            questions = await fetch_chapter_questions(
                client,
                store,
                identity_id,
                chapter_id,
                aid,
                subject_id=chapter_subject.get(chapter_id, ""),
            )
            if questions is None:
                restricted += 1
            else:
                for q in questions:
                    if str(q.get("is_collection_question")) == "1":
                        store.upsert_collection(
                            str(q.get("id")),
                            identity_id=identity_id,
                            subject_id=str(q.get("subject_id") or ""),
                            chapter_id=chapter_id,
                            source="scan",
                        )
                        found_new += 1
            store.scan_mark(scope, chapter_id)
        return {
            "scanned_now": len(pending),
            "found_new": found_new,
            "restricted_chapters": restricted,
            "progress": store.scan_progress(scope),
            "items": store.collections_list(identity_id),
        }