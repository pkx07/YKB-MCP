"""真实账号只读冒烟测试：python -m ykb_mcp.smoke

密码通过 getpass 在本机输入，不写入任何文件；仅调用只读接口。
"""

import asyncio
import getpass

from .client import YkbClient
from .meta import flatten_identities, leaf_identities, resolve_meta
from .pull import (
    fetch_chapter_questions,
    pull_hot_comments,
    pull_my_comments,
    pull_notes,
)
from .store import Store
from .tools._helpers import ensure_chapters, ensure_tree


async def run():
    store = Store()
    client = YkbClient(store)
    try:
        if not store.credentials:
            mobile = input("医考帮手机号: ").strip()
            password = getpass.getpass("密码（仅本次登录使用，不存储）: ")
            data = await client.login(mobile, password)
            print(f"[1/7] 登录成功 user_id={data.get('user_id')}")
        else:
            print(f"[1/7] 使用已保存凭据 user_id={store.credentials['user_id']}")

        tree = await ensure_tree(client, store, refresh=True)
        nodes = flatten_identities(tree)
        leaves = [n for n in nodes if n["is_leaf"]]
        print(f"[2/7] 身份树: {len(nodes)} 个节点, {len(leaves)} 个叶子")
        for n in nodes[:10]:
            print(f"    {n['identity_id']}  {n['path']}  leaf={n['is_leaf']}")
        if not leaves:
            print("身份树为空，终止")
            return

        root = next((n for n in nodes if not n["is_leaf"]), leaves[0])
        target_leaves = leaf_identities(nodes, root["identity_id"])
        leaf = target_leaves[0]
        resp = await client.request(
            "/allquestion/main/userAnswer",
            {
                "app_id": leaf.get("app_id") or "40",
                "module_type": leaf.get("module_type") or "1",
                "identity_id": leaf["identity_id"],
                "category": "chapter",
                "type": "all",
                "is_vip": "0",
                "is_svip": "0",
            },
            method="GET",
        )
        records = resp.get("data") if isinstance(resp.get("data"), list) else []
        wrong = [r for r in records if str(r.get("is_right")) == "0"]
        cut = [r for r in records if str(r.get("cut_question") or r.get("is_cut")) in ("1", "cutted")]
        print(f"[3/7] 做题记录({leaf['identity_id']}): code={resp.get('code')} 共{len(records)}条 错题{len(wrong)} 已斩{len(cut)}")

        subjects = await ensure_chapters(client, store, leaf["identity_id"], refresh=True)
        chapters = [c for s in subjects for c in s["chapters"]]
        print(f"[4/7] 章节目录: {len(subjects)} 科目 {len(chapters)} 章")
        questions = []
        if chapters:
            ch = chapters[0]
            questions = await fetch_chapter_questions(
                client, store, leaf["identity_id"], ch["chapter_id"],
                leaf.get("app_id") or "40", subject_id=ch.get("subject_id", ""),
            ) or []
            print(f"    首章《{ch['title']}》拉取 {len(questions)} 题（DES 解密成功）")

        qid = None
        if questions:
            qid = str(questions[0]["id"])
        elif records:
            qid = str(records[0].get("question_id"))
        if qid:
            try:
                meta = resolve_meta(store, qid)
            except Exception:
                meta = {
                    "subject_id": leaf["identity_id"],
                    "identity_id": leaf["identity_id"],
                    "chapter_id": "",
                    "app_id": leaf.get("app_id") or "40",
                }
            comments = await pull_hot_comments(client, store, qid, meta)
            print(f"[5/7] 题目 {qid} 热门评论: {len(comments)} 条")
            praises = await pull_my_comments(client, store, qid, meta, "mypraise")
            mine = await pull_my_comments(client, store, qid, meta, "mycomment")
            print(f"    我的点赞 {len(praises)} 条 / 我的评论 {len(mine)} 条")
            notes = await pull_notes(client, store, qid, meta)
            print(f"[6/7] 题目 {qid} 笔记: {len(notes)} 条")
        else:
            print("[5/7][6/7] 跳过：无可用题目")

        print(f"[7/7] 缓存统计: {store.stats()}")
        print("冒烟完成。可启动 MCP：uv run ykb-mcp")
    finally:
        await client.aclose()
        store.close()


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()