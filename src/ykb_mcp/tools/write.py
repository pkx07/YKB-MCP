from ..errors import ApiError, YkbError
from ..meta import outer_identity, resolve_meta
from ..pull import normalize_comment
from . import guard


def register(mcp, client, store):
    @mcp.tool
    @guard
    async def ykb_praise_comment(
        comment_id: str,
        question_id: str,
        identity_id: str = "",
        subject_id: str = "",
        app_id: str = "",
    ) -> dict:
        """【写操作】给一条评论点赞，会改动账号数据，请谨慎使用。成功后自动归档到本地「我的点赞」。comment_id 可来自 ykb_comments。"""
        client.require_login()
        meta = resolve_meta(
            store, question_id, identity_id=identity_id, subject_id=subject_id, app_id=app_id
        )
        resp = await client.request(
            "/Comment/Main/praise",
            {
                "id": comment_id,
                "obj_id": question_id,
                "type": "1",
                "comment_type": "2",
                "module_type": "1",
                "subject_id": meta["subject_id"],
                "identity_id": outer_identity(meta),
                "app_id": meta["app_id"],
                "is_vip": "0",
                "is_svip": "0",
            },
        )
        code = str(resp.get("code", ""))
        if code != "200":
            raise ApiError(code, str(resp.get("message") or "点赞失败"))
        existing = store.get_comment(comment_id)
        item = {
            "comment_id": comment_id,
            "question_id": question_id,
            "content": existing["content"] if existing else "",
            "nickname": existing["nickname"] if existing else "",
            "user_id": existing["user_id"] if existing else "",
            "praise_num": (existing["praise_num"] + 1) if existing else 0,
            "ctime_ts": existing["ctime_ts"] if existing else 0,
            "is_praise": "1",
        }
        store.upsert_comment(item, "praise")
        return {"ok": True, "comment_id": comment_id, "question_id": question_id}

    @mcp.tool
    @guard
    async def ykb_publish_comment(
        question_id: str,
        content: str,
        identity_id: str = "",
        subject_id: str = "",
        app_id: str = "",
    ) -> dict:
        """【写操作】在某题下发表评论，会改动账号数据，请谨慎使用。成功后自动归档到本地「我的评论」。"""
        client.require_login()
        if not content.strip():
            raise YkbError("评论内容不能为空")
        meta = resolve_meta(
            store, question_id, identity_id=identity_id, subject_id=subject_id, app_id=app_id
        )
        resp = await client.request(
            "/Comment/Main/publish",
            {
                "subject_id": meta["subject_id"],
                "obj_id": question_id,
                "is_svip": "0",
                "module_type": "1",
                "identity_id": outer_identity(meta),
                "is_vip": "0",
                "content": content,
                "comment_type": "2",
                "app_id": meta["app_id"],
            },
        )
        code = str(resp.get("code", ""))
        if code != "200":
            raise ApiError(code, str(resp.get("message") or "评论发表失败"))
        data = resp.get("data")
        if isinstance(data, dict) and data.get("id"):
            item = normalize_comment(data, question_id)
        else:
            creds = store.credentials or {}
            item = {
                "comment_id": "",
                "question_id": question_id,
                "user_id": creds.get("user_id", ""),
                "nickname": creds.get("nickname", ""),
                "content": content,
                "is_author": "1",
            }
        if item.get("comment_id"):
            store.upsert_comment(item, "my_comment")
        return {
            "ok": True,
            "question_id": question_id,
            "comment_id": item.get("comment_id", ""),
            "message": "评论已发表",
        }

    @mcp.tool
    @guard
    async def ykb_cut_question(
        question_id: str,
        cut: bool = True,
        identity_id: str = "",
        subject_id: str = "",
        chapter_id: str = "",
        app_id: str = "",
    ) -> dict:
        """【写操作】斩题/取消斩题（标记该题已掌握），会改动账号数据，请谨慎使用。需要 chapter_id（题目已缓存时自动读取，否则请显式传入）。"""
        client.require_login()
        meta = resolve_meta(
            store,
            question_id,
            identity_id=identity_id,
            subject_id=subject_id,
            app_id=app_id,
            chapter_id=chapter_id,
        )
        if not meta["chapter_id"]:
            raise YkbError(
                "缺少 chapter_id：请先用 ykb_chapter_questions 拉取该题所在章节，或显式传入 chapter_id"
            )
        resp = await client.request(
            "/allQuestion/cutQuestion/cut",
            {
                "subject_id": meta["subject_id"],
                "identity_id": meta["identity_id"],
                "module_type": "1",
                "is_vip": "0",
                "is_svip": "0",
                "question_id": question_id,
                "operate": "add" if cut else "del",
                "chapter_id": meta["chapter_id"],
                "unit_id": "",
                "app_id": meta["app_id"],
            },
        )
        code = str(resp.get("code", ""))
        if code != "200":
            raise ApiError(code, str(resp.get("message") or "斩题操作失败"))
        store.set_cut(question_id, cut)
        return {"ok": True, "question_id": question_id, "cut": cut}