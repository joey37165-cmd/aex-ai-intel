from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from collections.abc import Mapping
from typing import Any

from app.adapters.langfuse.prompts import (
    PromptProvider,
    build_dedup_prompt_provider,
    build_digest_prompt_provider,
    build_prompt_provider,
)
from app.domain.deduplication import are_semantic_duplicates
from app.domain.models import (
    AnalysisResult, ContentItem, DeduplicationResult, DigestCandidate, DigestReport,
    EventFeatures, ReportWindow,
)


def _clean_text(value: Any, fallback: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or fallback)).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit - 1].rstrip()}…"


def _clean_multiline_text(value: Any, fallback: str, limit: int) -> str:
    lines = []
    for line in str(value or fallback).replace("\r\n", "\n").split("\n"):
        cleaned = re.sub(r"[ \t]+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    text = "\n".join(lines).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit - 1].rstrip()}…"


_EVENT_TYPES = {
    "model_release", "model_update", "api_update", "pricing_change", "tool_release",
    "workflow_update", "research_result", "security_incident",
    "policy_or_industry_change", "business_or_funding", "other",
}
_EVENT_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _optional_text(value: Any, limit: int = 120) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:limit].rstrip() or None


def _event_features(data: dict[str, Any], summary: str) -> EventFeatures:
    value = data.get("event")
    event = value if isinstance(value, dict) else {}
    event_type = str(event.get("event_type", "other")).strip().lower()
    if event_type not in _EVENT_TYPES:
        event_type = "other"
    event_time = _optional_text(event.get("event_time"), 10)
    if event_time and not _EVENT_DATE_RE.fullmatch(event_time):
        event_time = None
    return EventFeatures(
        event_type=event_type,
        organization=_optional_text(event.get("organization")),
        product=_optional_text(event.get("product")),
        version=_optional_text(event.get("version"), 60),
        core_claim=_clean_text(event.get("core_claim"), summary, 160),
        event_time=event_time,
    )


def _result(data: dict[str, Any], item: ContentItem) -> AnalysisResult:
    decision = str(data.get("decision", "ignore")).lower()
    if decision not in {"notify", "ignore"}:
        decision = "ignore"
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
    summary = _clean_multiline_text(data.get("summary"), item.summary or item.title, 200)
    return AnalysisResult(
        decision=decision,
        priority=priority,
        category=raw_category,
        summary=summary,
        why_it_matters=_clean_text(data.get("why_it_matters"), "值得结合原文进一步判断。", 300),
        suggested_action=_clean_text(data.get("suggested_action"), "查看原文", 80),
        confidence=confidence,
        raw=data,
        display_title=_clean_text(data.get("display_title", data.get("title")), item.title, 180),
        event=_event_features(data, summary),
    )


def _dedup_result(data: dict[str, Any]) -> DeduplicationResult:
    relationship = str(data.get("relationship", "independent")).strip().lower()
    if relationship not in {"duplicate", "update", "independent"}:
        relationship = "independent"
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return DeduplicationResult(
        relationship=relationship,
        confidence=confidence,
        reason=_clean_text(data.get("reason"), "证据不足，按独立事件处理。", 160),
        raw=data,
    )


def _candidate_value(candidate: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        return candidate[key]
    except (KeyError, IndexError):
        return default


def _chat_json(api_key: str, model: str, base_url: str, timeout: float, messages: list[dict[str, str]]) -> dict:
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Aex-AI-Intel/0.1",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    content = re.sub(r"^```(?:json)?|```$", "", content.strip()).strip()
    result = json.loads(content)
    if not isinstance(result, dict):
        raise ValueError("DeepSeek 结构化输出必须是 JSON 对象")
    return result


def _digest_lines(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for entry in value[:limit]:
        text = _clean_text(entry, "", 180)
        if text:
            lines.append(text)
    return lines


def _numbered(lines: list[str], empty: str) -> str:
    return "\n".join(f"{index}. {line}" for index, line in enumerate(lines, start=1)) or empty


def _digest_result(data: dict[str, Any], window: ReportWindow, item_count: int) -> DigestReport:
    max_items = 8 if window.report_type == "weekly" else 5
    frontier = _digest_lines(data.get("frontier_items"), max_items)
    applications = _digest_lines(data.get("application_items"), max_items)
    report_title = "AI 周报" if window.report_type == "weekly" else "AI 日报"
    return DigestReport(
        report_title=report_title,
        period_label="",
        overview=_clean_text(data.get("overview"), f"本周期共整理 {item_count} 条高价值 AI 情报。", 350),
        frontier_items=_numbered(frontier, "本周期暂无值得单独列出的前沿更新。"),
        application_items=_numbered(applications, "本周期暂无值得单独列出的应用更新。"),
        key_takeaways=_clean_text(data.get("key_takeaways"), "本周期暂无更多综合观察。", 600),
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
        return _result(_chat_json(self.api_key, self.model, self.base_url, self.timeout, messages), item)


class DeepSeekDeduplicationJudge:
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
        self.prompt_version = os.environ.get("DEDUP_PROMPT_VERSION", "local-v1")
        self.prompt_provider = prompt_provider or build_dedup_prompt_provider()

    def judge(
        self,
        item: ContentItem,
        result: AnalysisResult,
        candidate: Mapping[str, Any],
    ) -> DeduplicationResult:
        prompt_messages, self.prompt_version = self.prompt_provider.get_prompt()
        try:
            candidate_event = json.loads(str(_candidate_value(candidate, "event_json") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            candidate_event = {}
        if not isinstance(candidate_event, dict):
            candidate_event = {}
        content_json = json.dumps({
            "new_item": {
                "source": item.source_name,
                "published_at": item.published_at.isoformat() if item.published_at else None,
                "title": item.title,
                "summary": item.summary[:1200],
                "event": {
                    "event_type": result.event.event_type,
                    "organization": result.event.organization,
                    "product": result.event.product,
                    "version": result.event.version,
                    "core_claim": result.event.core_claim,
                    "event_time": result.event.event_time,
                },
            },
            "historical_item": {
                "source": str(_candidate_value(candidate, "source_name") or ""),
                "published_at": str(_candidate_value(candidate, "published_at") or ""),
                "title": str(_candidate_value(candidate, "display_title") or _candidate_value(candidate, "title") or ""),
                "summary": str(_candidate_value(candidate, "analysis_summary") or _candidate_value(candidate, "summary") or "")[:1200],
                "event": candidate_event,
            },
        }, ensure_ascii=False)
        messages = [
            {"role": message["role"], "content": message["content"].replace("{{content_json}}", content_json)}
            for message in prompt_messages
        ]
        for attempt in range(3):
            try:
                return _dedup_result(_chat_json(self.api_key, self.model, self.base_url, self.timeout, messages))
            except (OSError, ValueError, KeyError):
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)


class DeepSeekDigestGenerator:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float = 60.0,
        prompt_provider: PromptProvider | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.prompt_version = os.environ.get("DIGEST_PROMPT_VERSION", "local-v1")
        self.prompt_provider = prompt_provider or build_digest_prompt_provider()

    def generate(self, window: ReportWindow, items: list[DigestCandidate]) -> DigestReport:
        if not items:
            return RuleBasedDigestGenerator().generate(window, items)
        prompt_messages, self.prompt_version = self.prompt_provider.get_prompt()
        content_json = json.dumps({
            "report_type": window.report_type,
            "period_start": window.period_start.isoformat(),
            "period_end": window.period_end.isoformat(),
            "items": [{
                "index": index,
                "source": item.source_name,
                "category": item.category,
                "priority": item.priority,
                "occurred_at": item.occurred_at.isoformat(),
                "title": item.title,
                "summary": item.summary[:500],
                "why_it_matters": item.why_it_matters[:500],
            } for index, item in enumerate(items, start=1)],
        }, ensure_ascii=False)
        messages = [
            {"role": message["role"], "content": message["content"].replace("{{content_json}}", content_json)}
            for message in prompt_messages
        ]
        return _digest_result(
            _chat_json(self.api_key, self.model, self.base_url, self.timeout, messages),
            window,
            len(items),
        )


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
            display_title=item.title,
            event=EventFeatures(
                core_claim=_clean_text(item.summary, item.title, 160),
                event_time=item.published_at.date().isoformat() if item.published_at else None,
            ),
        )


class RuleBasedDeduplicationJudge:
    model_name = "rules"
    prompt_version = "dedup-rules-v1"

    def judge(self, item: ContentItem, result: AnalysisResult, candidate: Mapping[str, Any]) -> DeduplicationResult:
        candidate_title = str(_candidate_value(candidate, "display_title") or _candidate_value(candidate, "title") or "")
        candidate_summary = str(_candidate_value(candidate, "analysis_summary") or _candidate_value(candidate, "summary") or "")
        duplicate = are_semantic_duplicates(item.title, item.summary, candidate_title, candidate_summary)
        return DeduplicationResult(
            relationship="duplicate" if duplicate else "independent",
            confidence=0.9 if duplicate else 0.55,
            reason="本地规则判断核心标题和摘要高度重合。" if duplicate else "本地规则未确认两条内容是同一事件。",
            raw={"mode": "rules", "heuristic_duplicate": duplicate},
        )


class RuleBasedDigestGenerator:
    prompt_version = "digest-rules-v1"

    def generate(self, window: ReportWindow, items: list[DigestCandidate]) -> DigestReport:
        max_items = 8 if window.report_type == "weekly" else 5

        def lines(category: str) -> list[str]:
            selected = [item for item in items if item.category == category][:max_items]
            return [_clean_text(f"{item.title}：{item.summary}", item.title, 180) for item in selected]

        frontier = lines("AI 前沿信息")
        applications = lines("AI 应用")
        return DigestReport(
            report_title="AI 周报" if window.report_type == "weekly" else "AI 日报",
            period_label="",
            overview=f"本周期共整理 {len(items)} 条高价值 AI 情报。" if items else "本周期暂无符合推送标准的高价值 AI 情报。",
            frontier_items=_numbered(frontier, "本周期暂无值得单独列出的前沿更新。"),
            application_items=_numbered(applications, "本周期暂无值得单独列出的应用更新。"),
            key_takeaways="高价值信息以报告所列条目为准，后续可结合原文继续跟踪。" if items else "本周期暂无更多综合观察。",
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


def build_deduplication_judge():
    mode = os.environ.get("AI_MODE", "deepseek").strip().lower()
    if mode == "rules":
        return RuleBasedDeduplicationJudge()
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if mode != "deepseek":
        raise RuntimeError(f"不支持的 AI_MODE: {mode}")
    if not api_key:
        raise RuntimeError("AI_MODE=deepseek 时必须配置 DEEPSEEK_API_KEY；本地测试请明确设置 AI_MODE=rules")
    return DeepSeekDeduplicationJudge(
        api_key=api_key,
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )


def build_digest_generator():
    mode = os.environ.get("AI_MODE", "deepseek").strip().lower()
    if mode == "rules":
        return RuleBasedDigestGenerator()
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if mode != "deepseek":
        raise RuntimeError(f"不支持的 AI_MODE: {mode}")
    if not api_key:
        raise RuntimeError("AI_MODE=deepseek 时必须配置 DEEPSEEK_API_KEY")
    return DeepSeekDigestGenerator(
        api_key=api_key,
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )
