from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent


def load_env(path=ROOT / ".env"):
    """Read the small documented .env format without executing shell expressions."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key.replace("_", "").isalnum() and key[0].isalpha():
            os.environ.setdefault(key, value.strip("\"'"))


@dataclass(frozen=True)
class Config:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    timeout: int = 90
    max_tokens: int = 5000

    @classmethod
    def from_env(cls):
        load_env()
        return cls(
            api_key=os.getenv("DEEPSEEK_API_KEY", os.getenv("LLM_API_KEY", "")),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            model=os.getenv("LLM_MODEL", "deepseek-flash"),
            timeout=int(os.getenv("LLM_TIMEOUT_SECONDS", "90")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "5000")),
        )

    def mode(self, requested="auto"):
        if requested not in {"auto", "live", "offline"}:
            raise ValueError("mode must be auto, live or offline")
        value = ("live" if self.api_key else "offline") if requested == "auto" else requested
        if value == "live" and not self.api_key:
            raise ValueError("未配置 DEEPSEEK_API_KEY。请填入本地 .env 后重启，或选择离线模式。")
        return value

    def validate_api(self):
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("LLM_BASE_URL must be an HTTPS URL without embedded credentials")
