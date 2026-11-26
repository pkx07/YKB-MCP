from ..meta import resolve_meta
from ..pull import pull_notes
from . import guard
from ._scan import scan_scope


def register(mcp, client, store):
    @mcp.tool
    @guard
    async def ykb_notes(
        question_id: str,
        identity_id: str = "",
        subject_id: str = "",
        app_id: str = "",
        page: int = 1,
        size: int = 20,
    ) -> dict:
        """获取某题下我的笔记（官方 getNote，含笔记图片 URL），写入本地缓存。题目元数据优先从缓存解析，必要时显式传 identity_id/subject_id/app_id。"""
        client.require_login()
        meta = resolve_meta(
            store, question_id, identity_id=identity_id, subject_id=subject_id, app_id=app_id
        )
        items = await pull_notes(client, store, question_id, meta, page=page, size=size)
        return {"question_id": question_id, "count": len(items), "items": items}

    @mcp.tool
    @guard
    async def ykb_notes_all(
        limit: int = 50, scan_budget: int = 10, identity_id: str = ""
    ) -> dict:
        """全局「我的所有笔记」列表：先读本地缓存，再对未扫描的已做题限速增量扫描（scan_budget=本次请求数）。remaining>0 时重复调用可续扫；全量同步用 ykb_sync(scope='notes')。identity_id 可选，限定某个题库。"""
        client.require_login()
        scan = await scan_scope(
            client, store, "notes", scan_budget, identity_id=identity_id or None, is_notes=True
        )
        items = store.notes_list(limit=limit)
        remaining = scan["progress"]["remaining"]
        return {
            "returned": len(items),
            "items": items,
            "scanned_now": scan["scanned_now"],
            "skipped": scan["skipped"],
            "remaining": remaining,
            "hint": (
                "remaining>0 表示还有题目未扫描，可再次调用继续；批量全量用 ykb_sync"
                if remaining
                else "扫描已完成，items 为本地归纳的全部结果（受 limit 限制）"
            ),
        }