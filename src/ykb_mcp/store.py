import json
import os
import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    identity_id TEXT NOT NULL DEFAULT '',
    subject_id TEXT NOT NULL DEFAULT '',
    chapter_id TEXT NOT NULL DEFAULT '',
    app_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '',
    type_str TEXT NOT NULL DEFAULT '',
    year TEXT NOT NULL DEFAULT '',
    answer TEXT NOT NULL DEFAULT '',
    option_json TEXT NOT NULL DEFAULT '',
    explain TEXT NOT NULL DEFAULT '',
    is_collection INTEGER DEFAULT 0,
    is_cut INTEGER DEFAULT 0,
    user_answer TEXT NOT NULL DEFAULT '',
    raw_json TEXT NOT NULL DEFAULT '',
    updated_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS answer_records (
    question_id TEXT NOT NULL,
    identity_id TEXT NOT NULL,
    root_id TEXT NOT NULL DEFAULT '',
    answer TEXT NOT NULL DEFAULT '',
    is_right TEXT NOT NULL DEFAULT '',
    is_cut INTEGER NOT NULL DEFAULT 0,
    duration INTEGER NOT NULL DEFAULT 0,
    remote_id TEXT NOT NULL DEFAULT '',
    update_time INTEGER NOT NULL DEFAULT 0,
    fetched_at INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (question_id, identity_id)
);
CREATE INDEX IF NOT EXISTS idx_answers_root ON answer_records(root_id);
CREATE TABLE IF NOT EXISTS comments (
    id TEXT PRIMARY KEY,
    comment_id TEXT NOT NULL,
    question_id TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT '',
    nickname TEXT NOT NULL DEFAULT '',
    avatar TEXT NOT NULL DEFAULT '',
    school TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    praise_num INTEGER NOT NULL DEFAULT 0,
    oppose_num INTEGER NOT NULL DEFAULT 0,
    replies INTEGER NOT NULL DEFAULT 0,
    floor_num TEXT NOT NULL DEFAULT '1',
    ctime TEXT NOT NULL DEFAULT '',
    ctime_ts INTEGER NOT NULL DEFAULT 0,
    img_watermark TEXT NOT NULL DEFAULT '',
    imgs TEXT NOT NULL DEFAULT '',
    is_praise TEXT NOT NULL DEFAULT '0',
    is_author TEXT NOT NULL DEFAULT '0',
    reply_json TEXT NOT NULL DEFAULT '[]',
    updated_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_comments_cat ON comments(category, ctime_ts DESC);
CREATE INDEX IF NOT EXISTS idx_comments_question ON comments(question_id);
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    imgs_json TEXT NOT NULL DEFAULT '[]',
    ctime INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS collections (
    question_id TEXT PRIMARY KEY,
    identity_id TEXT NOT NULL DEFAULT '',
    subject_id TEXT NOT NULL DEFAULT '',
    chapter_id TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    updated_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS scan_queue (
    scope TEXT NOT NULL,
    question_id TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (scope, question_id)
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def default_home() -> Path:
    return Path(os.environ.get("YKB_MCP_HOME", "~/.ykb-mcp")).expanduser()


def _now() -> int:
    return int(time.time())


def _s(v, default: str = "") -> str:
    return default if v is None else str(v)


def _i(v, default: int = 0) -> int:
    try:
        return int(str(v))
    except (TypeError, ValueError):
        return default


class Store:
    def __init__(self, home: Path | None = None):
        self.home = Path(home) if home is not None else default_home()
        self.home.mkdir(parents=True, exist_ok=True)
        self._cred_path = self.home / "credentials.json"
        self._db = sqlite3.connect(self.home / "cache.db", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def close(self):
        self._db.close()

    @property
    def credentials(self) -> dict | None:
        if not self._cred_path.exists():
            return None
        try:
            data = json.loads(self._cred_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict) or not data.get("token") or not data.get("user_id"):
            return None
        return data

    def save_credentials(self, data: dict):
        payload = {k: str(data[k]) for k in ("token", "secret", "user_id") if data.get(k)}
        for k in ("user_uuid", "nickname", "avatar", "school"):
            if data.get(k):
                payload[k] = str(data[k])
        payload["saved_at"] = _now()
        self._cred_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._cred_path.chmod(0o600)

    def clear_credentials(self):
        if self._cred_path.exists():
            self._cred_path.unlink()

    def upsert_question(self, q: dict):
        qid = _s(q.get("id"))
        if not qid:
            return
        option = q.get("option")
        option_json = option if isinstance(option, str) else json.dumps(option or [], ensure_ascii=False)
        self._db.execute(
            """
            INSERT INTO questions (id, identity_id, subject_id, chapter_id, app_id,
                title, type, type_str, year, answer, option_json, explain,
                is_collection, is_cut, user_answer, raw_json, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                identity_id = COALESCE(NULLIF(excluded.identity_id,''), questions.identity_id),
                subject_id = COALESCE(NULLIF(excluded.subject_id,''), questions.subject_id),
                chapter_id = COALESCE(NULLIF(excluded.chapter_id,''), questions.chapter_id),
                app_id = COALESCE(NULLIF(excluded.app_id,''), questions.app_id),
                title = COALESCE(NULLIF(excluded.title,''), questions.title),
                type = COALESCE(NULLIF(excluded.type,''), questions.type),
                type_str = COALESCE(NULLIF(excluded.type_str,''), questions.type_str),
                year = COALESCE(NULLIF(excluded.year,''), questions.year),
                answer = COALESCE(NULLIF(excluded.answer,''), questions.answer),
                option_json = COALESCE(NULLIF(excluded.option_json,''), questions.option_json),
                explain = COALESCE(NULLIF(excluded.explain,''), questions.explain),
                is_collection = COALESCE(excluded.is_collection, questions.is_collection),
                is_cut = COALESCE(excluded.is_cut, questions.is_cut),
                user_answer = COALESCE(NULLIF(excluded.user_answer,''), questions.user_answer),
                raw_json = excluded.raw_json,
                updated_at = excluded.updated_at
            """,
            (
                qid,
                _s(q.get("identity_id")),
                _s(q.get("subject_id")),
                _s(q.get("chapter_id")),
                _s(q.get("app_id")),
                _s(q.get("title")),
                _s(q.get("type")),
                _s(q.get("type_str")),
                _s(q.get("year")),
                _s(q.get("answer")),
                option_json,
                _s(q.get("explain")),
                (1 if _s(q.get("is_collection_question")) == "1" else 0)
                if "is_collection_question" in q
                else None,
                (1 if _s(q.get("cut_question")) in ("1", "cutted") else 0)
                if "cut_question" in q
                else None,
                _s(q.get("user_answer")),
                json.dumps(q, ensure_ascii=False),
                _now(),
            ),
        )
        self._db.commit()

    def get_question(self, question_id: str) -> dict | None:
        row = self._db.execute(
            "SELECT * FROM questions WHERE id = ?", (str(question_id),)
        ).fetchone()
        return dict(row) if row else None

    def set_cut(self, question_id: str, cut: bool):
        flag = 1 if cut else 0
        self._db.execute(
            "UPDATE questions SET is_cut = ?, updated_at = ? WHERE id = ?",
            (flag, _now(), str(question_id)),
        )
        self._db.execute(
            "UPDATE answer_records SET is_cut = ?, fetched_at = ? WHERE question_id = ?",
            (flag, _now(), str(question_id)),
        )
        self._db.commit()

    def upsert_answer(self, rec: dict):
        self._db.execute(
            """
            INSERT OR REPLACE INTO answer_records
                (question_id, identity_id, root_id, answer, is_right, is_cut,
                 duration, remote_id, update_time, fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                _s(rec.get("question_id")),
                _s(rec.get("identity_id")),
                _s(rec.get("root_id")),
                _s(rec.get("answer")),
                _s(rec.get("is_right")),
                1 if rec.get("is_cut") else 0,
                _i(rec.get("duration")),
                _s(rec.get("remote_id")),
                _i(rec.get("update_time")),
                _now(),
            ),
        )
        self._db.commit()

    def answers(self, filter: str = "all", identity_id: str | None = None, limit: int = 200) -> list[dict]:
        cond, args = [], []
        if filter == "wrong":
            cond.append("a.is_right = '0'")
        elif filter == "right":
            cond.append("a.is_right = '1'")
        elif filter == "cut":
            cond.append("a.is_cut = 1")
        if identity_id:
            cond.append("(a.identity_id = ? OR a.root_id = ?)")
            args.extend([identity_id, identity_id])
        where = f"WHERE {' AND '.join(cond)}" if cond else ""
        rows = self._db.execute(
            f"""
            SELECT a.*, q.title AS question_title
            FROM answer_records a LEFT JOIN questions q ON q.id = a.question_id
            {where}
            ORDER BY a.update_time DESC LIMIT ?
            """,
            (*args, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def answer_identity(self, question_id: str) -> str:
        row = self._db.execute(
            "SELECT identity_id FROM answer_records WHERE question_id = ? LIMIT 1",
            (str(question_id),),
        ).fetchone()
        return row["identity_id"] if row else ""

    def upsert_comment(self, item: dict, category: str):
        cid = _s(item.get("comment_id"))
        if not cid:
            return
        self._db.execute(
            """
            INSERT OR REPLACE INTO comments
                (id, comment_id, question_id, category, user_id, nickname, avatar,
                 school, content, praise_num, oppose_num, replies, floor_num,
                 ctime, ctime_ts, img_watermark, imgs, is_praise, is_author,
                 reply_json, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                f"{category}_{cid}",
                cid,
                _s(item.get("question_id")),
                category,
                _s(item.get("user_id")),
                _s(item.get("nickname")),
                _s(item.get("avatar")),
                _s(item.get("school")),
                _s(item.get("content")),
                _i(item.get("praise_num")),
                _i(item.get("oppose_num")),
                _i(item.get("replies")),
                _s(item.get("floor_num"), "1"),
                _s(item.get("ctime")),
                _i(item.get("ctime_ts")),
                _s(item.get("img_watermark")),
                _s(item.get("imgs")),
                _s(item.get("is_praise"), "0"),
                _s(item.get("is_author"), "0"),
                json.dumps(item.get("reply") or [], ensure_ascii=False),
                _now(),
            ),
        )
        self._db.commit()

    def get_comment(self, comment_id: str) -> dict | None:
        row = self._db.execute(
            "SELECT * FROM comments WHERE comment_id = ? ORDER BY updated_at DESC LIMIT 1",
            (str(comment_id),),
        ).fetchone()
        return dict(row) if row else None

    def comments_list(
        self,
        category: str | None = None,
        question_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        cond, args = [], []
        if category:
            cond.append("c.category = ?")
            args.append(category)
        if question_id:
            cond.append("c.question_id = ?")
            args.append(str(question_id))
        where = f"WHERE {' AND '.join(cond)}" if cond else ""
        rows = self._db.execute(
            f"""
            SELECT c.*, q.title AS question_title
            FROM comments c LEFT JOIN questions q ON q.id = c.question_id
            {where}
            ORDER BY c.ctime_ts DESC, c.updated_at DESC LIMIT ? OFFSET ?
            """,
            (*args, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_note(self, note: dict):
        nid = _s(note.get("id"))
        if not nid:
            return
        self._db.execute(
            """
            INSERT OR REPLACE INTO notes (id, question_id, content, imgs_json, ctime, updated_at)
            VALUES (?,?,?,?,?,?)
            """,
            (
                nid,
                _s(note.get("question_id")),
                _s(note.get("content")),
                json.dumps(note.get("imgs") or [], ensure_ascii=False),
                _i(note.get("ctime")),
                _now(),
            ),
        )
        self._db.commit()

    def notes_list(self, question_id: str | None = None, limit: int = 50) -> list[dict]:
        if question_id:
            rows = self._db.execute(
                """
                SELECT n.*, q.title AS question_title FROM notes n
                LEFT JOIN questions q ON q.id = n.question_id
                WHERE n.question_id = ? ORDER BY n.ctime DESC LIMIT ?
                """,
                (str(question_id), limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                """
                SELECT n.*, q.title AS question_title FROM notes n
                LEFT JOIN questions q ON q.id = n.question_id
                ORDER BY n.ctime DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def upsert_collection(self, question_id: str, identity_id: str = "", subject_id: str = "", chapter_id: str = "", source: str = ""):
        self._db.execute(
            """
            INSERT OR REPLACE INTO collections
                (question_id, identity_id, subject_id, chapter_id, source, updated_at)
            VALUES (?,?,?,?,?,?)
            """,
            (str(question_id), identity_id, subject_id, chapter_id, source, _now()),
        )
        self._db.commit()

    def collections_list(self, identity_id: str | None = None, limit: int = 200) -> list[dict]:
        if identity_id:
            rows = self._db.execute(
                """
                SELECT c.*, q.title AS question_title FROM collections c
                LEFT JOIN questions q ON q.id = c.question_id
                WHERE c.identity_id = ? OR c.identity_id = ''
                ORDER BY c.updated_at DESC LIMIT ?
                """,
                (identity_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                """
                SELECT c.*, q.title AS question_title FROM collections c
                LEFT JOIN questions q ON q.id = c.question_id
                ORDER BY c.updated_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def scan_ensure(self, scope: str, ids: list[str]):
        self._db.executemany(
            "INSERT OR IGNORE INTO scan_queue (scope, question_id, done) VALUES (?,?,0)",
            [(scope, str(i)) for i in ids if i],
        )
        self._db.commit()

    def scan_pending(self, scope: str, limit: int) -> list[str]:
        rows = self._db.execute(
            "SELECT question_id FROM scan_queue WHERE scope = ? AND done = 0 LIMIT ?",
            (scope, limit),
        ).fetchall()
        return [r["question_id"] for r in rows]

    def scan_mark(self, scope: str, question_id: str):
        self._db.execute(
            "UPDATE scan_queue SET done = 1 WHERE scope = ? AND question_id = ?",
            (scope, str(question_id)),
        )
        self._db.commit()

    def scan_progress(self, scope: str) -> dict:
        row = self._db.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(done),0) AS done FROM scan_queue WHERE scope = ?",
            (scope,),
        ).fetchone()
        total, done = row["total"], row["done"]
        return {"total": total, "done": done, "remaining": total - done}

    def kv_set(self, key: str, value):
        self._db.execute(
            "INSERT OR REPLACE INTO kv (key, value) VALUES (?,?)",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        self._db.commit()

    def kv_get(self, key: str):
        row = self._db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return None

    def touched_questions(self, identity_id: str | None = None) -> list[str]:
        if identity_id:
            rows = self._db.execute(
                """
                SELECT question_id AS id FROM answer_records
                WHERE identity_id = ? OR root_id = ?
                UNION SELECT id FROM questions WHERE identity_id = ?
                """,
                (identity_id, identity_id, identity_id),
            ).fetchall()
        else:
            rows = self._db.execute(
                """
                SELECT id FROM questions
                UNION SELECT question_id FROM answer_records
                UNION SELECT question_id FROM comments
                UNION SELECT question_id FROM notes
                """
            ).fetchall()
        return [r["id"] for r in rows if r["id"]]

    def search(self, keyword: str, kind: str = "all", limit: int = 20) -> dict:
        like = f"%{keyword}%"
        out: dict = {}
        if kind in ("all", "questions"):
            out["questions"] = [
                dict(r)
                for r in self._db.execute(
                    "SELECT id, title, type_str, year, answer, identity_id, chapter_id FROM questions WHERE title LIKE ? LIMIT ?",
                    (like, limit),
                )
            ]
        if kind in ("all", "comments"):
            out["comments"] = [
                dict(r)
                for r in self._db.execute(
                    "SELECT comment_id, question_id, category, nickname, content, praise_num, ctime FROM comments WHERE content LIKE ? ORDER BY ctime_ts DESC LIMIT ?",
                    (like, limit),
                )
            ]
        if kind in ("all", "notes"):
            out["notes"] = [
                dict(r)
                for r in self._db.execute(
                    "SELECT id, question_id, content, ctime FROM notes WHERE content LIKE ? ORDER BY ctime DESC LIMIT ?",
                    (like, limit),
                )
            ]
        return out

    def stats(self) -> dict:
        tables = ("questions", "answer_records", "comments", "notes", "collections")
        out = {}
        for t in tables:
            out[t] = self._db.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
        return out