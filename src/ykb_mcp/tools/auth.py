from ..meta import flatten_identities
from . import guard
from ._helpers import ensure_tree


def register(mcp, client, store, login_manager):
    @mcp.tool
    @guard
    async def ykb_login(wait_seconds: int = 120) -> dict:
        """打开本地网页登录医考帮：在 127.0.0.1 启动一次性登录页并自动打开浏览器（结果中也附 URL）。手机号与密码由用户在浏览器中输入，由本地进程直接提交官方接口，全程不经过对话。严禁向用户索要手机号/密码。默认等待登录完成（120 秒）；返回 pending 时让用户继续操作，之后用 ykb_login_status 查询。凭据仅存本地 ~/.ykb-mcp/credentials.json（600 权限），不存储密码。"""
        info = await login_manager.start()
        result = await login_manager.wait(timeout=wait_seconds)
        result.setdefault("url", info["url"])
        return result

    @mcp.tool
    @guard
    async def ykb_login_status() -> dict:
        """查询本地网页登录的进度与结果（ykb_login 返回 pending 后使用）。logged_in=true 表示登录成功。"""
        return login_manager.status()

    @mcp.tool
    @guard
    async def ykb_whoami() -> dict:
        """查询当前医考帮登录状态与本地缓存统计（题目/做题记录/评论/笔记/收藏数量）。"""
        creds = store.credentials
        return {
            "logged_in": bool(creds),
            "user_id": (creds or {}).get("user_id", ""),
            "nickname": (creds or {}).get("nickname", ""),
            "data_dir": str(store.home),
            "cache": store.stats(),
        }

    @mcp.tool
    @guard
    async def ykb_logout() -> dict:
        """退出当前医考帮账号：清除本地凭据，保留缓存数据。"""
        store.clear_credentials()
        return {"ok": True, "message": "已清除本地凭据"}

    @mcp.tool
    @guard
    async def ykb_identities(refresh: bool = False) -> dict:
        """获取医考帮身份树（可用题库/学期，如临床期末、口腔期末、执业医师）。返回扁平身份列表：identity_id、名称、路径、是否叶子。做题记录/章节工具需要 identity_id；父身份会自动展开为叶子身份。默认读缓存，refresh=True 强制刷新。"""
        client.require_login()
        tree = await ensure_tree(client, store, refresh=refresh)
        nodes = flatten_identities(tree)
        return {"count": len(nodes), "identities": nodes}