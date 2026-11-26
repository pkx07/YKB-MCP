from ..errors import ApiError, YkbError
from ..meta import resolve_meta
from ..pull import pull_my_comments, pull_notes


async def scan_scope(
    client,
    store,
    scope: str,
    budget: int,
    identity_id: str | None = None,
    func: str | None = None,
    is_notes: bool = False,
) -> dict:
    touched = store.touched_questions(identity_id)
    store.scan_ensure(scope, touched)
    pending = store.scan_pending(scope, budget)
    scanned = 0
    skipped = 0
    for qid in pending:
        try:
            meta = resolve_meta(store, qid)
        except YkbError:
            store.scan_mark(scope, qid)
            skipped += 1
            continue
        try:
            if is_notes:
                await pull_notes(client, store, qid, meta)
            else:
                await pull_my_comments(client, store, qid, meta, func)
        except ApiError as e:
            if e.code in ("203", "403"):
                store.scan_mark(scope, qid)
                skipped += 1
                continue
            raise
        store.scan_mark(scope, qid)
        scanned += 1
    return {
        "scanned_now": scanned,
        "skipped": skipped,
        "progress": store.scan_progress(scope),
    }