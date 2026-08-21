from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from string import Formatter


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class TemplateDefinition:
    template_id: str
    name: str
    description: str
    file_path: Path
    allowed_variables: tuple[str, ...]
    required_variables: tuple[str, ...]


TEMPLATE_DEFINITIONS = {
    "realtime": TemplateDefinition(
        template_id="realtime",
        name="日常情报",
        description="新消息筛选后即时推送到 Telegram",
        file_path=ROOT / "config" / "templates" / "telegram.html",
        allowed_variables=(
            "category_line", "title", "summary", "why_it_matters", "links_line",
        ),
        required_variables=("category_line", "title", "summary", "links_line"),
    ),
    "digest": TemplateDefinition(
        template_id="digest",
        name="日报 / 周报",
        description="日报与周报共用，按标题自动区分",
        file_path=ROOT / "config" / "templates" / "telegram_digest.html",
        allowed_variables=(
            "report_title", "period_label", "overview", "frontier_items",
            "application_items", "key_takeaways", "source_links", "my_x_link",
        ),
        required_variables=("report_title", "period_label", "overview"),
    ),
}


class TemplateValidationError(ValueError):
    pass


class _TelegramHTMLValidator(HTMLParser):
    ALLOWED_TAGS = {
        "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
        "a", "code", "pre", "blockquote", "tg-spoiler",
    }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in self.ALLOWED_TAGS:
            raise TemplateValidationError(f"Telegram 模板不支持 <{tag}> 标签")
        if tag == "a":
            unsupported = [name for name, _ in attrs if name != "href"]
            if unsupported:
                raise TemplateValidationError("链接标签只允许 href 属性")
        elif attrs:
            raise TemplateValidationError(f"<{tag}> 标签不允许属性")
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1] != tag:
            raise TemplateValidationError(f"HTML 标签闭合顺序错误: </{tag}>")
        self.stack.pop()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.stack.pop()


def validate_template(template_id: str, content: str) -> str:
    definition = TEMPLATE_DEFINITIONS.get(template_id)
    if definition is None:
        raise TemplateValidationError(f"未知模板: {template_id}")
    normalized = content.replace("\r\n", "\n").strip()
    if not normalized:
        raise TemplateValidationError("模板内容不能为空")
    if len(normalized) > 10_000:
        raise TemplateValidationError("模板内容不能超过 10000 个字符")

    try:
        parsed_fields = list(Formatter().parse(normalized))
        if any(format_spec or conversion for _, _, format_spec, conversion in parsed_fields):
            raise TemplateValidationError("模板变量不支持格式化参数或类型转换")
        fields = {field_name for _, field_name, _, _ in parsed_fields if field_name is not None}
    except ValueError as exc:
        raise TemplateValidationError(f"模板变量格式错误: {exc}") from exc
    unknown = fields.difference(definition.allowed_variables)
    if unknown:
        raise TemplateValidationError(f"包含未知变量: {', '.join(sorted(unknown))}")
    missing = set(definition.required_variables).difference(fields)
    if missing:
        raise TemplateValidationError(f"缺少必要变量: {', '.join(sorted(missing))}")

    validator = _TelegramHTMLValidator(convert_charrefs=False)
    try:
        validator.feed(normalized)
        validator.close()
        if validator.stack:
            raise TemplateValidationError(f"HTML 标签未闭合: <{validator.stack[-1]}>")
    except TemplateValidationError:
        raise
    except Exception as exc:
        raise TemplateValidationError(f"HTML 格式错误: {exc}") from exc
    return normalized


def seed_templates(store) -> None:
    for definition in TEMPLATE_DEFINITIONS.values():
        content = definition.file_path.read_text(encoding="utf-8").strip()
        store.initialize_template(
            definition.template_id,
            definition.name,
            definition.description,
            validate_template(definition.template_id, content),
        )
