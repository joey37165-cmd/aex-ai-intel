from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from threading import Lock
from typing import Any


DEFAULT_USER_PROMPT = """请根据系统规则评估以下 AI 情报候选，只返回规定的 JSON 对象。

<untrusted_content>
{{content_json}}
</untrusted_content>"""


class PromptProvider:
    def get_prompt(self) -> tuple[list[dict[str, str]], str]:
        raise NotImplementedError


class LocalPromptProvider(PromptProvider):
    def __init__(self, path: Path, user_path: Path | None = None) -> None:
        self.path = path
        self.user_path = user_path

    def get_prompt(self) -> tuple[list[dict[str, str]], str]:
        try:
            system_prompt = self.path.read_text(encoding="utf-8")
        except OSError:
            system_prompt = "你是 AI 情报编辑。只输出合法 JSON，不要 Markdown。判断这条消息是否值得推送。"
        try:
            user_prompt = self.user_path.read_text(encoding="utf-8") if self.user_path else DEFAULT_USER_PROMPT
        except OSError:
            user_prompt = DEFAULT_USER_PROMPT
        version = os.environ.get("PROMPT_VERSION", "local-v2") if self.path.exists() else "local-fallback"
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ], version


def _normalize_chat_prompt(value: list[Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for message in value:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "")).lower()
        content = message.get("content", "")
        if role in {"system", "user", "assistant"} and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content.strip()})
    if not messages:
        raise ValueError("Langfuse Chat Prompt 没有有效消息")
    return messages


class LangfusePromptProvider(PromptProvider):
    """Fetch a production-labelled prompt and fall back to the local copy."""

    def __init__(
        self,
        local: LocalPromptProvider,
        host: str,
        public_key: str,
        secret_key: str,
        name: str,
        label: str = "production",
        cache_seconds: int = 60,
        timeout: float = 10.0,
    ) -> None:
        self.local = local
        self.host = host.rstrip("/")
        self.public_key = public_key
        self.secret_key = secret_key
        self.name = name
        self.label = label
        self.cache_seconds = max(0, cache_seconds)
        self.timeout = timeout
        self._cached: tuple[list[dict[str, str]], str] | None = None
        self._cached_at = 0.0
        self._lock = Lock()

    def get_prompt(self) -> tuple[list[dict[str, str]], str]:
        now = time.monotonic()
        with self._lock:
            if self._cached is not None and now - self._cached_at < self.cache_seconds:
                return self._cached
            try:
                result = self._fetch()
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                result = self.local.get_prompt()
            self._cached = result
            self._cached_at = now
            return result

    def _fetch(self) -> tuple[list[dict[str, str]], str]:
        name = urllib.parse.quote(self.name, safe="")
        label = urllib.parse.quote(self.label, safe="")
        request = urllib.request.Request(
            f"{self.host}/api/public/v2/prompts/{name}?label={label}",
            headers={
                "Authorization": "Basic " + base64.b64encode(f"{self.public_key}:{self.secret_key}".encode()).decode(),
                "Accept": "application/json",
                "User-Agent": "Aex-AI-Intel/0.1",
            },
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        prompt = data.get("prompt")
        if isinstance(prompt, list):
            messages = _normalize_chat_prompt(prompt)
        elif isinstance(prompt, str) and prompt.strip():
            _, user_message = self.local.get_prompt()[0]
            messages = [{"role": "system", "content": prompt.strip()}, user_message]
        else:
            raise ValueError("Langfuse 返回的 prompt 为空或格式不支持")
        version = str(data.get("version") or data.get("id") or "remote")
        return messages, f"langfuse:{version}"


def build_prompt_provider() -> PromptProvider:
    path = Path(os.environ.get("PROMPT_PATH", "config/prompts/intelligence_filter.md"))
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[3] / path
    user_path = Path(os.environ.get("USER_PROMPT_PATH", "config/prompts/intelligence_filter_user.md"))
    if not user_path.is_absolute():
        user_path = Path(__file__).resolve().parents[3] / user_path
    local = LocalPromptProvider(path, user_path)
    enabled = os.environ.get("LANGFUSE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    if not enabled or not public_key or not secret_key:
        return local
    try:
        cache_seconds = int(os.environ.get("LANGFUSE_CACHE_SECONDS", "60"))
    except ValueError:
        cache_seconds = 60
    return LangfusePromptProvider(
        local=local,
        host=os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        public_key=public_key,
        secret_key=secret_key,
        name=os.environ.get("LANGFUSE_PROMPT_NAME", "ai-intelligence-filter"),
        label=os.environ.get("LANGFUSE_PROMPT_LABEL", "production"),
        cache_seconds=cache_seconds,
    )
