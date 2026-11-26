from .errors import YkbError
from .store import Store


def normalize_tree(nodes) -> list[dict]:
    out: list[dict] = []
    if not isinstance(nodes, list):
        return out
    for raw in nodes:
        if not isinstance(raw, dict):
            continue
        kids = normalize_tree(raw.get("children"))
        nid = str(raw.get("identity_id") or "")
        if nid in ("", "0"):
            out.extend(kids)
        else:
            out.append({**raw, "children": kids})
    return out


def flatten_identities(tree) -> list[dict]:
    nodes: list[dict] = []

    def walk(items, parent_id: str, path: list[str], app_id: str, module_type: str):
        for raw in items:
            nid = str(raw.get("identity_id") or "")
            name = str(raw.get("title") or nid)
            aid = str(raw.get("app_id") or "") or app_id
            mt = str(raw.get("module_type") or "") or module_type
            kids = raw.get("children") or []
            new_path = [*path, name]
            nodes.append(
                {
                    "identity_id": nid,
                    "name": name,
                    "parent_id": parent_id,
                    "path": " / ".join(new_path),
                    "app_id": aid or "40",
                    "module_type": mt or "1",
                    "category": str(raw.get("category") or "chapter"),
                    "am_pm": str(raw.get("am_pm") or ""),
                    "is_leaf": not kids,
                }
            )
            walk(kids, nid, new_path, aid, mt)

    walk(normalize_tree(tree), "-1", [], "", "1")
    return nodes


def find_node(nodes: list[dict], identity_id: str) -> dict | None:
    for n in nodes:
        if n["identity_id"] == str(identity_id):
            return n
    return None


def leaf_identities(nodes: list[dict], root_id: str) -> list[dict]:
    root = find_node(nodes, root_id)
    if root is None:
        raise YkbError(
            f"身份树中找不到 identity_id={root_id}，请先调用 ykb_identities 查看可用身份"
        )
    if root["is_leaf"]:
        return [root]
    children_map: dict[str, list[dict]] = {}
    for n in nodes:
        children_map.setdefault(n["parent_id"], []).append(n)
    leaves: list[dict] = []

    def visit(nid: str):
        kids = children_map.get(nid, [])
        if not kids:
            node = find_node(nodes, nid)
            if node:
                leaves.append(node)
            return
        for k in kids:
            visit(k["identity_id"])

    visit(root["identity_id"])
    return leaves or [root]


def tree_app_id(nodes: list[dict], identity_id: str, default: str = "40") -> str:
    node = find_node(nodes, identity_id)
    if node and node.get("app_id"):
        return node["app_id"]
    return default


def get_tree(store: Store) -> list | None:
    tree = store.kv_get("identity_tree")
    return tree if isinstance(tree, list) else None


def resolve_meta(
    store: Store,
    question_id: str,
    *,
    identity_id: str = "",
    subject_id: str = "",
    app_id: str = "",
    chapter_id: str = "",
) -> dict:
    q = store.get_question(question_id) or {}
    meta = {
        "subject_id": subject_id or q.get("subject_id", ""),
        "chapter_id": chapter_id or q.get("chapter_id", ""),
        "identity_id": identity_id or q.get("identity_id", ""),
        "app_id": app_id or q.get("app_id", ""),
    }
    if not meta["identity_id"]:
        meta["identity_id"] = store.answer_identity(question_id)
    if not meta["app_id"]:
        meta["app_id"] = tree_app_id(get_tree(store) or [], meta["identity_id"])
    if not meta["subject_id"]:
        meta["subject_id"] = meta["identity_id"]
    if not meta["identity_id"]:
        raise YkbError(
            f"无法解析题目 {question_id} 的元数据：请先用 ykb_chapter_questions 拉取该题所在章节，"
            "或显式传入 identity_id / subject_id / app_id"
        )
    return meta


def outer_identity(meta: dict) -> str:
    return meta.get("subject_id") or meta.get("identity_id", "")