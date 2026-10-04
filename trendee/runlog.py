"""Append-only local JSONL audit log for RAG demo runs.

The logger records complete request/result payloads for reproducibility while
redacting credential-shaped fields. Logs live under WANXI_DATA_DIR and are
therefore excluded from Git.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import uuid
from typing import Any


SENSITIVE_KEYS = {
    "api_key", "authorization", "password", "secret",
    "deepseek_api_key", "llm_api_key", "hf_token",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("[REDACTED]" if str(key).lower() in SENSITIVE_KEYS else _redact(child))
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class RunLogger:
    def __init__(self, data_dir: str | Path):
        self.path = Path(data_dir) / "logs" / "rag_runs.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @staticmethod
    def new_run_id() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        return f"rag-{stamp}-{uuid.uuid4().hex[:8]}"

    def record(
        self,
        run_id: str,
        endpoint: str,
        request: dict[str, Any],
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        http_status: int = 200,
        duration_ms: int | None = None,
    ) -> dict[str, Any]:
        record = {
            "run_id": run_id,
            "logged_at_utc": _now(),
            "endpoint": endpoint,
            "http_status": http_status,
            "duration_ms": duration_ms,
            "request": _redact(request),
            "result": _redact(result) if result is not None else None,
            "error": error,
        }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return record

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        if not self.path.exists():
            return []
        # The demo log is local and bounded in UI. Reading lines keeps the
        # on-disk record complete while returning only recent runs to browser.
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        output = []
        for line in lines[-limit:][::-1]:
            if not line.strip():
                continue
            try:
                output.append(json.loads(line))
            except json.JSONDecodeError:
                output.append({"error": "malformed_log_line"})
        return output
