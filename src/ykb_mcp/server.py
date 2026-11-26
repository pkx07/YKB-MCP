from fastmcp import FastMCP

from .client import YkbClient
from .store import Store
from .tools import auth, comments, notes, records, sync, write
from .weblogin import WebLoginManager

_INSTRUCTIONS = """医考帮（yikaobang）个人账号数据 MCP。

使用流程：
1. 调用 ykb_login() 打开本地网页登录（127.0.0.1 一次性页面，自动开浏览器）。
   手机号/密码由用户在浏览器输入，绝不经过对话——严禁向用户索要密码。
   返回 pending 时用 ykb_login_status 查询结果。凭据仅存本地 ~/.ykb-mcp/。
2. ykb_identities 查看可用题库身份；ykb_answer_records(identity_id, filter=wrong|cut|...) 拉取错题/已斩/做题记录。
3. ykb_chapters + ykb_chapter_questions 获取题目内容；ykb_question 查单题。
4. ykb_comments / ykb_my_praises / ykb_my_comments / ykb_notes 按题读取；
   ykb_my_praises_all / ykb_my_comments_all / ykb_notes_all 全局归纳（缓存+限速增量扫描）；
   ykb_sync 批量同步；ykb_search_local 搜索本地缓存。
5. ykb_collections / ykb_collections_scan 获取收藏题目。

注意：
- 所有网络请求自动限速（约 1.2~2 秒/请求），批量扫描请耐心续跑，不要并发轰炸。
- 标注【写操作】的工具（ykb_praise_comment / ykb_publish_comment / ykb_cut_question）会改动账号数据，执行前应向用户确认。
- 登录过期（309）时重新调用 ykb_login；203 表示该章节无权限（VIP/题库未购买）。
- 本服务仅供个人账号数据读取与学习用途，请遵守医考帮用户协议，勿传播题库内容。
"""


def create_app(
    store: Store | None = None,
    client: YkbClient | None = None,
    login_manager: WebLoginManager | None = None,
) -> FastMCP:
    store = store if store is not None else Store()
    client = client if client is not None else YkbClient(store)
    login_manager = (
        login_manager if login_manager is not None else WebLoginManager(client, store)
    )
    mcp = FastMCP("ykb-mcp", instructions=_INSTRUCTIONS)
    auth.register(mcp, client, store, login_manager)
    for module in (records, comments, notes, sync, write):
        module.register(mcp, client, store)
    return mcp


def main():
    create_app().run()


if __name__ == "__main__":
    main()