import functools

from ..errors import YkbError


def guard(fn):
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except YkbError as e:
            return {"ok": False, "error": str(e)}

    return wrapper