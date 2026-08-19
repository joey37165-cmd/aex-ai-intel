from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

from app.adapters.langfuse.prompts import PromptProvider, build_prompt_provider
from app.domain.models import AnalysisResult, ContentItem


def _clean_text(value: Any, fallback: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or fallback)).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit - 1].rstrip()}…"


def _result(data: dict[str, Any], item: ContentItem) -> AnalysisResult:
    decision = str(data.get("decision", "review")).lower()
    if decision not in {"notify", "review", "ignore"}:
        decision = "review"
    priority = str(data.get("priority", "A")).upper()
    if priority not in {"S", "A", "B"}:
        priority = "B"
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5
    raw_category = _clean_text(data.get("category"), "AI 前沿信息", 20)
    if raw_category not in {"AI 前沿信息", "AI 应用"}:
        app_terms = ("工作流", "agent", "github", "工具", "应用", "变现", "workflow")
        raw_category = "AI 应用" if any(term in raw_category.lower() for term in app_terms) else "AI 前沿信息"
    return AnalysisResult(
        decision=decision,
        priority=priority,
        category=raw_category,
        summary=_clean_text(data.get("summary"), item.summary or item.title, 240),
        why_it_matters=_clean_text(data.get("why_it_matters"), "值得结合原文进一步判断。", 300),
        suggested_action=_clean_text(data.get("suggested_action"), "查看原文", 80),
        confidence=confidence,
        raw=data,
    )


class DeepSeekAnalyzer:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float = 45.0,
        prompt_provider: PromptProvider | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.model_name = model
        self.prompt_version = os.environ.get("PROMPT_VERSION", "local-v2")
        self.prompt_provider = prompt_provider or build_prompt_provider()

    def analyze(self, item: ContentItem) -> AnalysisResult:
        prompt_messages, self.prompt_version = self.prompt_provider.get_prompt()
        content_json = json.dumps({
            "source": item.source_name,
            "source_category": item.category,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "title": item.title,
            "summary": item.summary[:4000],
            "url": item.url,
        }, ensure_ascii=False)
        messages = [
            {"role": message["role"], "content": message["content"].replace("{{content_json}}", content_json)}
            for message in prompt_messages
        ]
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "User-Agent": "Aex-AI-Intel/0.1"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?|```$", "", content.strip()).strip()
        return _result(json.loads(content), item)


class RuleBasedAnalyzer:
    """Deterministic fallback for local tests and outages; production should use DeepSeek."""

    keywords = ("model", "release", "api", "open source", "github", "agent", "inference", "模型", "发布", "更新", "开源", "价格")
    model_name = "rules"
    prompt_version = "rules-v1"

    def analyze(self, item: ContentItem) -> AnalysisResult:
        text = f"{item.title} {item.summary}".lower()
        matches = sum(1 for word in self.keywords if word in text)
        priority = "S" if matches >= 2 else "A" if matches == 1 else "B"
        decision = "notify" if matches else "ignore"
        return AnalysisResult(
            decision=decision, priority=priority, category=item.category,
            summary=_clean_text(item.summary, item.title, 240),
            why_it_matters="规则模式命中 AI 主题关键词，请查看原文核验。" if matches else "未命中当前主题规则。",
            suggested_action="查看原文" if matches else "忽略", confidence=0.8,
            raw={"mode": "rules", "matches": matches},
        )


def build_analyzer():
    mode = os.environ.get("AI_MODE", "deepseek").strip().lower()
    if mode == "rules":
        return RuleBasedAnalyzer()
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if mode != "deepseek":
        raise RuntimeError(f"不支持的 AI_MODE: {mode}")
    if not api_key:
        raise RuntimeError("AI_MODE=deepseek 时必须配置 DEEPSEEK_API_KEY；本地测试请明确设置 AI_MODE=rules")
    if api_key:
        return DeepSeekAnalyzer(
            api_key=api_key,
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
    raise RuntimeError("无法创建 DeepSeek 分析器")
