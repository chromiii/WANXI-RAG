"""Local-only RAG/agent demo server with observable run logging."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .config import ROOT, runtime_data_dir
from .demo_cases import ui_project1_cases
from .runlog import RunLogger
from .service import Workbench


def make_handler(workbench, logger=None, data_dir=None):
    sessions, session_lock = {}, threading.Lock()
    private_dir = Path(data_dir) if data_dir is not None else runtime_data_dir()
    private_dir = private_dir.expanduser().resolve()
    logger = logger or RunLogger(private_dir)

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
        if not sid or result.get("status") != "ok":
            return
        with session_lock:
            if len(sessions) >= 64 and sid not in sessions:
                oldest = min(sessions, key=lambda k: sessions[k]["time"])
                del sessions[oldest]
            sessions[sid] = {
                "history": (history + [question])[-10:],
                "result": result,
                "time": time.monotonic(),
            }

    class Handler(BaseHTTPRequestHandler):
        server_version = f"TrendeeDemo/{__version__}"

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

        def file_response(self, file, mime):
            file = Path(file)
            if not file.exists() or not file.is_file():
                self.json_response({"error": "Not found"}, 404)
                return
            body = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if mime.startswith("text/html"):
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "img-src 'self' data:; connect-src 'self'; frame-src 'self'; "
                    "object-src 'none'; base-uri 'none'; form-action 'self'"
                )
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/info":
                info = workbench.info()
                info["rag_log"] = {
                    "enabled": True,
                    "relative_path": "logs/rag_runs.jsonl",
                }
                self.json_response(info)
                return
            if path == "/api/cases":
                self.json_response({"cases": ui_project1_cases()})
                return
            if path == "/api/logs":
                params = parse_qs(parsed.query)
                try:
                    limit = int(params.get("limit", ["20"])[0])
                except ValueError:
                    raise_value = {"error": "limit must be an integer"}
                    self.json_response(raise_value, 400)
                    return
                self.json_response({"runs": logger.recent(limit), "limit": max(1, min(limit, 100))})
                return
            if path == "/source.pdf":
                self.file_response(private_dir / "trendee_brand.pdf", "application/pdf")
                return
            match = re.fullmatch(r"/assets/pages/(p\d{3}\.png)", path)
            if match:
                self.file_response(private_dir / "assets" / "pages" / match.group(1), "image/png")
                return

            files = {
                "/": (ROOT / "web/index.html", "text/html; charset=utf-8"),
                "/app.js": (ROOT / "web/app.js", "text/javascript; charset=utf-8"),
                "/styles.css": (ROOT / "web/styles.css", "text/css; charset=utf-8"),
            }
            if path not in files:
                self.json_response({"error": "Not found"}, 404)
                return
            self.file_response(*files[path])

        def do_POST(self):
            path = urlparse(self.path).path
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                self.json_response({"error": "Cross-origin requests are not accepted"}, 403)
                return

            run_id = None
            started = time.perf_counter()
            payload = {}
            loggable = path in {"/api/write", "/api/search"}
            if loggable:
                run_id = logger.new_run_id()

            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0 or size > 100_000:
                    raise ValueError("Invalid request size")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("JSON body must be an object")
                mode = payload.get("mode", "auto")

                if path == "/api/write":
                    result = workbench.write(
                        payload.get("topic", ""),
                        payload.get("audience", "中国出海品牌的市场与运营团队"),
                        payload.get("content_type", "auto"),
                        mode,
                        int(payload.get("top_k", 6)),
                    )
                elif path == "/api/route":
                    result = workbench.route(
                        payload.get("question", ""),
                        payload.get("history", []),
                        mode,
                        payload.get("router", "rules"),
                    )
                elif path == "/api/agents":
                    sid, history, prior = session_context(payload)
                    result = workbench.collaborate(
                        payload.get("question", ""),
                        history,
                        mode,
                        payload.get("router", "rules"),
                        prior_result=prior,
                    )
                    save_session(sid, history, payload.get("question", ""), result)
                elif path == "/api/search":
                    query = workbench.check_input(payload.get("query", ""))
                    top_k = int(payload.get("top_k", 6))
                    if payload.get("source") == "website":
                        if workbench.site_index is None:
                            raise FileNotFoundError("Website snapshot is not prepared.")
                        result = {
                            "status": "ok",
                            "query": query,
                            "hits": workbench.site_index.search(query, top_k),
                        }
                    else:
                        result = workbench.search_pdf(query, mode=mode, top_k=top_k)
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
                        result = workbench.collaborate(
                            payload.get("question", ""),
                            history,
                            mode,
                            payload.get("router", "rules"),
                            on_event=event,
                            prior_result=prior,
                        )
                        save_session(sid, history, payload.get("question", ""), result)
                    except (ValueError, RuntimeError) as exc:
                        event({"type": "error", "message": str(exc)})
                    return
                else:
                    self.json_response({"error": "Not found"}, 404)
                    return

                duration_ms = round((time.perf_counter() - started) * 1000)
                if run_id:
                    result = dict(result)
                    result["run_id"] = run_id
                    logger.record(
                        run_id,
                        path,
                        payload,
                        result=result,
                        http_status=200,
                        duration_ms=duration_ms,
                    )
                self.json_response(result)
            except (ValueError, KeyError, TypeError, FileNotFoundError) as exc:
                duration_ms = round((time.perf_counter() - started) * 1000)
                if run_id:
                    logger.record(
                        run_id,
                        path,
                        payload,
                        error=str(exc),
                        http_status=400,
                        duration_ms=duration_ms,
                    )
                self.json_response({"error": str(exc), "run_id": run_id}, 400)
            except RuntimeError as exc:
                duration_ms = round((time.perf_counter() - started) * 1000)
                if run_id:
                    logger.record(
                        run_id,
                        path,
                        payload,
                        error=str(exc),
                        http_status=502,
                        duration_ms=duration_ms,
                    )
                self.json_response({"error": str(exc), "run_id": run_id}, 502)
            except (BrokenPipeError, ConnectionResetError):
                return

    return Handler


def serve(host="127.0.0.1", port=8000):
    private_dir = runtime_data_dir()
    logger = RunLogger(private_dir)
    workbench = Workbench(data_dir=private_dir)
    server = ThreadingHTTPServer(
        (host, port),
        make_handler(workbench, logger=logger, data_dir=private_dir),
    )
    print(f"Trendee RAG Interactive Review: http://{host}:{port}", flush=True)
    print(f"RAG run log: {logger.path}", flush=True)
    if workbench.config.api_key:
        print(f"LLM: LIVE ready ({workbench.config.model})", flush=True)
    else:
        print("LLM: OFFLINE only (DEEPSEEK_API_KEY is not configured)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
