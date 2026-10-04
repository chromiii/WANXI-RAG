"""Small OpenAI-compatible JSON client, with bounded retries and no secret logging."""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class ModelError(RuntimeError):
    pass


def repair_instruction(error):
    base = "上次 JSON 未通过校验：" + error + "。"
    if "numbers absent from cited evidence" in error:
        return base + "删除被引用证据中不存在的数字，或改写为不含该数字的事实表述。仅返回完整 JSON。"
    if "unknown citations" in error:
        return base + "所有 citation id 只能使用原上下文 evidence 中已经给出的 id。仅返回完整 JSON。"
    if "unsupported guarantee" in error:
        return base + "删除或明确否定任何未经资料支持的推荐率、排名、增长或永久记忆保证。仅返回完整 JSON。"
    return base + "请严格依据原上下文修正 JSON，删除无依据事实和数据；不要补造资料。仅返回完整 JSON。"


class Client:
    def __init__(self, config):
        self.config = config
        self.calls = []

    def json(self, system, user, validator=None, purpose="generation"):
        self.config.validate_api()
        if not self.config.api_key:
            raise ModelError("DEEPSEEK_API_KEY is not configured")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last_error = ""
        for repair in range(2):
            call_purpose = purpose if repair == 0 else purpose + ":repair"
            data = self._request(messages, purpose=call_purpose)
            message = data.get("choices", [{}])[0]
            content = message.get("message", {}).get("content", "")
            try:
                if message.get("finish_reason") == "length":
                    raise ValueError("response truncated; reduce output length or increase LLM_MAX_TOKENS")
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("empty model response")
                if content.strip().startswith("```"):
                    content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                value = json.loads(content)
                if not isinstance(value, dict):
                    raise ValueError("JSON response must be an object")
                if validator:
                    validator(value)
                return value
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                last_error = str(exc)[:1200]
                if repair == 0:
                    messages.extend([
                        {"role": "assistant", "content": content[:24000] if isinstance(content, str) else "{}"},
                        {"role": "user", "content": repair_instruction(last_error)},
                    ])
        raise ModelError("模型输出两次未通过校验：" + last_error)

    def _request(self, messages, purpose="generation"):
        payload = {"model": self.config.model, "messages": messages,
                   "response_format": {"type": "json_object"},
                   "temperature": .2, "max_tokens": self.config.max_tokens, "stream": False}
        if urlparse(self.config.base_url).hostname == "api.deepseek.com":
            payload["thinking"] = {"type": "disabled"}
        req = Request(self.config.base_url + "/chat/completions",
                      data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                      headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.config.api_key})
        for attempt in range(3):
            started = time.perf_counter()
            try:
                with urlopen(req, timeout=self.config.timeout) as response:
                    raw = response.read(5_000_001)
                    if len(raw) > 5_000_000:
                        raise ModelError("Model response exceeded the size limit")
                    data = json.loads(raw)
                if not data.get("choices"):
                    raise ModelError("API returned no choices")
                self.calls.append({"purpose": purpose, "model": self.config.model, "usage": data.get("usage", {}),
                                   "duration_ms": round((time.perf_counter()-started)*1000),
                                   "attempt": attempt + 1})
                return data
            except HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(.5 * (attempt + 1))
                    continue
                friendly = {401: "模型认证失败，请检查本地密钥。", 402: "模型账户余额不足。",
                            400: "模型参数被拒绝，请检查模型名称及兼容接口。", 429: "模型服务限流，请稍后重试。"}
                raise ModelError(friendly.get(exc.code, f"模型服务返回 HTTP {exc.code}。")) from None
            except (URLError, TimeoutError) as exc:
                if attempt < 2:
                    time.sleep(.5 * (attempt + 1))
                    continue
                raise ModelError("模型连接失败或超时；请检查网络与 LLM_BASE_URL。") from None
            except json.JSONDecodeError:
                raise ModelError("API returned malformed JSON") from None
        raise ModelError("Model request failed")
