from . import guard
from ._scan import scan_scope

_SCOPES = {
    "praise": ("praise", "mypraise", False),
    "mycomment": ("my_comment", "mycomment", False),
    "notes": ("notes", None, True),
}


def register(mcp, client, store):
    @mcp.tool
    @guard
    async def ykb_sync(scope: str = "all", identity_id: str = "", budget: int = 30) -> dict:
        """批量同步我的点赞/我的评论/我的笔记到本地缓存（限速、断点续传）。scope: praise|mycomment|notes|all。budget=每个类别本次最多扫描题数。重复调用直到各类别 remaining=0。扫描范围=已做题∪已缓存题目∪已有评论/笔记的题目。"""
        client.require_login()
        names = list(_SCOPES) if scope == "all" else [scope]
        if scope != "all" and scope not in _SCOPES:
            return {"ok": False, "error": f"未知 scope: {scope}，可选 praise|mycomment|notes|all"}
        results = {}
        for name in names:
            category, func, is_notes = _SCOPES[name]
            results[name] = await scan_scope(
                client,
                store,
                category,
                budget,
                identity_id=identity_id or None,
                func=func,
                is_notes=is_notes,
            )
        return {
            "scope": scope,
            "results": results,
            "cache": store.stats(),
            "hint": "任一类别 remaining>0 时再次调用继续；之后可用 ykb_my_praises_all / ykb_my_comments_all / ykb_notes_all / ykb_search_local 查询",
        }

    @mcp.tool
    @guard
    async def ykb_search_local(keyword: str, kind: str = "all", limit: int = 20) -> dict:
        """在本地缓存中按关键词搜索（questions=题干, comments=评论内容, notes=笔记内容, all=全部）。数据来自此前拉取/同步过的内容，不发起网络请求。"""
        if kind not in ("all", "questions", "comments", "notes"):
            return {"ok": False, "error": f"未知 kind: {kind}"}
        return {"keyword": keyword, "kind": kind, "results": store.search(keyword, kind, limit)}