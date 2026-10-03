"""Local-only stdlib HTTP app. Static files are explicitly allowlisted."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from .config import ROOT
from .service import Workbench


def make_handler(workbench):
    sessions, session_lock = {}, threading.Lock()
    def session_context(payload):
        sid = payload.get("session_id", "")
        if sid and not re.fullmatch(r"[A-Za-z0-9-]{16,64}", sid):
            raise ValueError("Invalid session_id")
        with session_lock:
            for key in list(sessions):
                if time.monotonic() - sessions[key]["time"] > 7200:
                    del sessions[key]
            stored = sessions.get(sid, {})
            return sid, stored.get("history", payload.get("history", [])), stored.get("result")
    def save_session(sid, history, question, result):
        if not sid or result.get("status") != "ok": return
        with session_lock:
            if len(sessions) >= 64 and sid not in sessions:
                oldest = min(sessions, key=lambda k: sessions[k]["time"])
                del sessions[oldest]
            sessions[sid] = {"history": (history + [question])[-10:], "result": result, "time": time.monotonic()}
    class Handler(BaseHTTPRequestHandler):
        server_version = "TrendeeDemo/1.0"

        def log_message(self, format, *args):
            return

        def json_response(self, value, status=200):
            data = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/info":
                self.json_response(workbench.info())
                return
            files = {"/": (ROOT / "web/index.html", "text/html; charset=utf-8"),
                     "/app.js": (ROOT / "web/app.js", "text/javascript; charset=utf-8"),
                     "/styles.css": (ROOT / "web/styles.css", "text/css; charset=utf-8"),
                     "/source.pdf": (ROOT / "data/trendee_brand.pdf", "application/pdf")}
            if path not in files:
                self.json_response({"error": "Not found"}, 404)
                return
            file, mime = files[path]
            if not file.exists():
                self.json_response({"error": "Source PDF is not included in the public repository. The validated page cache remains available to RAG."}, 404)
                return
            body = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            if mime.startswith("text/html"):
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            path = urlparse(self.path).path
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                self.json_response({"error": "Cross-origin requests are not accepted"}, 403)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0 or size > 100_000:
                    raise ValueError("Invalid request size")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("JSON body must be an object")
                mode = payload.get("mode", "auto")
                if path == "/api/write":
                    result = workbench.write(payload.get("topic", ""), payload.get("audience", "中国出海品牌的市场与运营团队"),
                                             payload.get("content_type", "Blog"), mode, int(payload.get("top_k", 6)))
                elif path == "/api/route":
                    result = workbench.route(payload.get("question", ""), payload.get("history", []), mode, payload.get("router", "rules"))
                elif path == "/api/agents":
                    sid, history, prior = session_context(payload)
                    result = workbench.collaborate(payload.get("question", ""), history, mode, payload.get("router", "rules"), prior_result=prior)
                    save_session(sid, history, payload.get("question", ""), result)
                elif path == "/api/search":
                    query = workbench.check_input(payload.get("query", ""))
                    index = workbench.site_index if payload.get("source") == "website" else workbench.pdf_index
                    result = {"hits": index.search(query, int(payload.get("top_k", 6)))}
                elif path == "/api/agents/stream":
                    sid, history, prior = session_context(payload)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.close_connection = True
                    def event(item):
                        self.wfile.write((json.dumps(item, ensure_ascii=False) + "\n").encode("utf-8"))
                        self.wfile.flush()
                    try:
                        result = workbench.collaborate(payload.get("question", ""), history, mode,
                                                      payload.get("router", "rules"), on_event=event, prior_result=prior)
                        save_session(sid, history, payload.get("question", ""), result)
                    except (ValueError, RuntimeError) as exc:
                        event({"type": "error", "message": str(exc)})
                    return
                else:
                    self.json_response({"error": "Not found"}, 404)
                    return
                self.json_response(result)
            except (ValueError, KeyError, TypeError) as exc:
                self.json_response({"error": str(exc)}, 400)
            except RuntimeError as exc:
                self.json_response({"error": str(exc)}, 502)
            except (BrokenPipeError, ConnectionResetError):
                return
    return Handler


def serve(host="127.0.0.1", port=8000):
    server = ThreadingHTTPServer((host, port), make_handler(Workbench()))
    print(f"Trendee Evidence Studio: http://{host}:{port}", flush=True)
    print("Offline mode runs without a key. Configure .env and restart for live DeepSeek generation.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
