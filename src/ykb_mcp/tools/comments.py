from ..meta import resolve_meta
from ..pull import pull_hot_comments, pull_my_comments
from . import guard
from ._scan import scan_scope


async def _global_comments(client, store, category, func, limit, scan_budget, identity_id):
    scan = await scan_scope(
        client,
        store,
        category,
        scan_budget,
        identity_id=identity_id or None,
        func=func,
    )
    items = store.comments_list(category=category, limit=limit)
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


def register(mcp, client, store):
    @mcp.tool
    @guard
    async def ykb_comments(
        question_id: str,
        sort: str = "likes",
        page: int = 1,
        identity_id: str = "",
        subject_id: str = "",
        app_id: str = "",
    ) -> dict:
        """获取某题的热门评论。sort: likes=最多点赞, hot=最高热度, replies=最多回复, newest=最新发布。列表中本人已点赞/已发表的评论会自动归档到本地缓存。题目元数据优先从缓存解析，必要时显式传 identity_id/subject_id/app_id。"""
        client.require_login()
        meta = resolve_meta(
            store, question_id, identity_id=identity_id, subject_id=subject_id, app_id=app_id
        )
        items = await pull_hot_comments(client, store, question_id, meta, sort=sort, page=page)
        return {
            "question_id": question_id,
            "sort": sort,
            "page": page,
            "count": len(items),
            "comments": items,
        }

    @mcp.tool
    @guard
    async def ykb_my_praises(
        question_id: str, identity_id: str = "", subject_id: str = "", app_id: str = ""
    ) -> dict:
        """获取某题下我点赞过的评论（官方 func=mypraise），写入本地缓存。"""
        client.require_login()
        meta = resolve_meta(
            store, question_id, identity_id=identity_id, subject_id=subject_id, app_id=app_id
        )
        items = await pull_my_comments(client, store, question_id, meta, "mypraise")
        return {"question_id": question_id, "count": len(items), "items": items}

    @mcp.tool
    @guard
    async def ykb_my_comments(
        question_id: str, identity_id: str = "", subject_id: str = "", app_id: str = ""
    ) -> dict:
        """获取某题下我发表过的评论（官方 func=mycomment），写入本地缓存。"""
        client.require_login()
        meta = resolve_meta(
            store, question_id, identity_id=identity_id, subject_id=subject_id, app_id=app_id
        )
        items = await pull_my_comments(client, store, question_id, meta, "mycomment")
        return {"question_id": question_id, "count": len(items), "items": items}

    @mcp.tool
    @guard
    async def ykb_my_praises_all(
        limit: int = 50, scan_budget: int = 10, identity_id: str = ""
    ) -> dict:
        """全局「我点赞过的所有评论」列表：先读本地缓存，再对未扫描的已做题限速增量扫描（scan_budget=本次请求数）。remaining>0 时重复调用可续扫；全量同步用 ykb_sync(scope='praise')。identity_id 可选，限定某个题库。"""
        client.require_login()
        return await _global_comments(
            client, store, "praise", "mypraise", limit, scan_budget, identity_id
        )

    @mcp.tool
    @guard
    async def ykb_my_comments_all(
        limit: int = 50, scan_budget: int = 10, identity_id: str = ""
    ) -> dict:
        """全局「我发表过的所有评论」列表：先读本地缓存，再对未扫描的已做题限速增量扫描（scan_budget=本次请求数）。remaining>0 时重复调用可续扫；全量同步用 ykb_sync(scope='mycomment')。identity_id 可选，限定某个题库。"""
        client.require_login()
        return await _global_comments(
            client, store, "my_comment", "mycomment", limit, scan_budget, identity_id
        )