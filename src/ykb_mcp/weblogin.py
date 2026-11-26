"""本地网页登录：仅监听 127.0.0.1 的一次性页面，密码不经过 agent 对话。"""

import asyncio
import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .client import YkbClient
from .errors import YkbError
from .store import Store

_PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>医考帮登录</title>
<style>
 body{font-family:system-ui,-apple-system,sans-serif;background:#f6f7f9;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}
 .card{background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.08);padding:32px;width:320px}
 h1{font-size:18px;margin:0 0 4px}
 p.sub{color:#888;font-size:12px;margin:0 0 20px}
 input[type=text],input[type=password]{width:100%;box-sizing:border-box;padding:10px;margin:6px 0;border:1px solid #ddd;border-radius:8px;font-size:14px}
 button{width:100%;padding:10px;margin-top:12px;background:#2f6fed;color:#fff;border:0;border-radius:8px;font-size:15px;cursor:pointer}
 button:disabled{opacity:.6}
 .show{font-size:12px;color:#666;display:flex;align-items:center;gap:4px;margin-top:4px}
 #msg{margin-top:12px;font-size:13px;min-height:18px}
 .ok{color:#1a9c4b}.err{color:#d4380d}
</style></head><body>
<div class="card">
 <h1>医考帮登录</h1>
 <p class="sub">仅本机可访问 · 密码不经过 AI 对话 · 不保存密码</p>
 <form id="f">
  <input id="mobile" type="text" inputmode="numeric" autocomplete="off" placeholder="手机号" required>
  <input id="password" type="password" autocomplete="new-password" placeholder="密码" required>
  <label class="show"><input type="checkbox" id="show">显示密码</label>
  <button id="btn" type="submit">登录</button>
 </form>
 <div id="msg"></div>
</div>
<script>
const f=document.getElementById('f'),msg=document.getElementById('msg'),btn=document.getElementById('btn');
document.getElementById('show').onchange=e=>{document.getElementById('password').type=e.target.checked?'text':'password'};
f.onsubmit=async e=>{
 e.preventDefault();btn.disabled=true;msg.textContent='登录中…';msg.className='';
 try{
  const r=await fetch(location.pathname,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mobile:document.getElementById('mobile').value.trim(),password:document.getElementById('password').value})});
  const d=await r.json();
  if(d.ok){msg.textContent='登录成功（'+(d.nickname||d.user_id)+'），可以关闭此页面。';msg.className='ok';f.style.display='none';}
  else{msg.textContent=d.error||'登录失败';msg.className='err';btn.disabled=false;}
 }catch(err){msg.textContent='请求失败：'+err;msg.className='err';btn.disabled=false;}
};
</script>
</body></html>"""


class WebLoginSession:
    LIFETIME = 300
    MAX_FAILURES = 5

    def __init__(self, client: YkbClient, store: Store, loop: asyncio.AbstractEventLoop):
        self.client = client
        self.store = store
        self.loop = loop
        self.token = secrets.token_urlsafe(24)
        self.result: dict | None = None
        self.last_error = ""
        self.failures = 0
        self.expired = False
        self._done = threading.Event()
        self._lock = threading.Lock()
        session = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                session._handle_get(self)

            def do_POST(self):
                session._handle_post(self)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/login/{self.token}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._timer = threading.Timer(self.LIFETIME, self._expire)
        self._timer.daemon = True

    def start(self):
        self._thread.start()
        self._timer.start()

    @property
    def alive(self) -> bool:
        return not self._done.is_set() and not self.expired

    def _host_ok(self, handler) -> bool:
        host = (handler.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _path_ok(self, handler) -> bool:
        return handler.path.split("?")[0] == f"/login/{self.token}"

    def _send(self, handler, code: int, body: str, content_type: str):
        data = body.encode("utf-8")
        handler.send_response(code)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(data)

    def _send_json(self, handler, code: int, payload: dict):
        self._send(handler, code, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")

    def _handle_get(self, handler):
        if not self._host_ok(handler) or not self._path_ok(handler):
            self._send(handler, 404, "not found", "text/plain; charset=utf-8")
            return
        if not self.alive:
            self._send(handler, 410, "登录页已关闭", "text/plain; charset=utf-8")
            return
        self._send(handler, 200, _PAGE, "text/html; charset=utf-8")

    def _handle_post(self, handler):
        if not self._host_ok(handler) or not self._path_ok(handler):
            self._send_json(handler, 404, {"ok": False, "error": "not found"})
            return
        if not self.alive:
            self._send_json(handler, 410, {"ok": False, "error": "登录页已关闭，请重新发起登录"})
            return
        try:
            length = int(handler.headers.get("Content-Length") or 0)
            if length <= 0 or length > 16384:
                raise ValueError("bad length")
            payload = json.loads(handler.rfile.read(length).decode("utf-8"))
            mobile = str(payload.get("mobile") or "").strip()
            password = str(payload.get("password") or "")
            if not mobile or not password:
                raise ValueError("手机号和密码不能为空")
        except (ValueError, TypeError, json.JSONDecodeError):
            self._send_json(handler, 400, {"ok": False, "error": "请求格式错误"})
            return
        with self._lock:
            if self.failures >= self.MAX_FAILURES:
                self._send_json(handler, 403, {"ok": False, "error": "失败次数过多，登录页已关闭"})
                threading.Timer(0.3, self._expire).start()
                return
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self.client.login(mobile, password), self.loop
                )
                data = future.result(timeout=40)
            except YkbError as e:
                self.failures += 1
                self.last_error = str(e)
                self._send_json(handler, 200, {"ok": False, "error": str(e)})
                if self.failures >= self.MAX_FAILURES:
                    threading.Timer(0.3, self._expire).start()
                return
            except Exception:
                self.failures += 1
                self.last_error = "登录请求异常，请重试"
                self._send_json(handler, 200, {"ok": False, "error": self.last_error})
                if self.failures >= self.MAX_FAILURES:
                    threading.Timer(0.3, self._expire).start()
                return
            self.result = {
                "user_id": str(data.get("user_id", "")),
                "nickname": str(data.get("nickname", "")),
            }
            self._done.set()
            self._send_json(handler, 200, {"ok": True, **self.result})
            threading.Timer(0.3, self._shutdown).start()

    def _shutdown(self):
        try:
            self._server.shutdown()
            self._server.server_close()
        except OSError:
            pass
        self._timer.cancel()

    def _expire(self):
        self.expired = True
        self._done.set()
        self._shutdown()


class WebLoginManager:
    def __init__(self, client: YkbClient, store: Store):
        self.client = client
        self.store = store
        self._session: WebLoginSession | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> dict:
        async with self._lock:
            if self._session and self._session.alive:
                return {"url": self._session.url, "port": self._session.port, "already_running": True}
            loop = asyncio.get_running_loop()
            self._session = WebLoginSession(self.client, self.store, loop)
            self._session.start()
        if not os.environ.get("YKB_MCP_NO_BROWSER"):
            try:
                webbrowser.open(self._session.url)
            except Exception:
                pass
        return {
            "url": self._session.url,
            "port": self._session.port,
            "expires_in": WebLoginSession.LIFETIME,
            "already_running": False,
        }

    async def wait(self, timeout: float = 120) -> dict:
        session = self._session
        if session is None:
            return {"ok": False, "error": "没有进行中的登录，请先调用 ykb_login"}
        deadline = time.monotonic() + max(timeout, 0)
        while True:
            if session.result:
                return {
                    "ok": True,
                    "logged_in": True,
                    **session.result,
                    "message": "登录成功，凭据已保存到本地",
                }
            if not session.alive:
                if session.failures >= WebLoginSession.MAX_FAILURES:
                    return {"ok": False, "error": "失败次数过多，登录页已关闭，请重新调用 ykb_login"}
                return {"ok": False, "error": "登录页已关闭，请重新调用 ykb_login"}
            if time.monotonic() >= deadline:
                return {
                    "ok": False,
                    "pending": True,
                    "url": session.url,
                    "message": "登录页仍在等待输入；用户完成后调用 ykb_login_status 查询结果",
                }
            await asyncio.sleep(0.2)

    def status(self) -> dict:
        session = self._session
        if session and session.result:
            return {"ok": True, "logged_in": True, **session.result}
        creds = self.store.credentials
        if creds:
            return {
                "ok": True,
                "logged_in": True,
                "user_id": creds.get("user_id", ""),
                "nickname": creds.get("nickname", ""),
            }
        if session and session.alive:
            return {"ok": False, "logged_in": False, "pending": True, "url": session.url}
        out = {"ok": False, "logged_in": False, "pending": False}
        if session and session.last_error:
            out["error"] = session.last_error
        return out


async def _amain():
    store = Store()
    client = YkbClient(store)
    manager = WebLoginManager(client, store)
    try:
        info = await manager.start()
        print(f"登录页已启动: {info['url']}")
        print("请在浏览器中完成登录（5 分钟内有效）…")
        result = await manager.wait(timeout=WebLoginSession.LIFETIME)
        print(json.dumps(result, ensure_ascii=False))
    finally:
        await client.aclose()
        store.close()


def main():
    asyncio.run(_amain())


if __name__ == "__main__":
    main()