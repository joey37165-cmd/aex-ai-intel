from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCES = ROOT / "config" / "sources.json"
DEFAULT_STATE = ROOT / "data" / "telegram_poc_state.json"
USER_AGENT = "AI-Intel-Telegram-PoC/0.1"
CHINA_TIMEZONE = timezone(timedelta(hours=8))


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)

    def text(self) -> str:
        return " ".join(self.parts)


@dataclass(frozen=True)
class FeedItem:
    item_id: str
    source: str
    category: str
    title: str
    url: str
    summary: str
    published_at: datetime | None


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Ignore an existing empty variable so a later, valid .env value wins.
        if key and (key not in os.environ or not os.environ[key].strip()):
            os.environ[key] = value


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def direct_child_text(node: ET.Element, names: set[str]) -> str:
    for child in list(node):
        if local_name(child.tag) in names:
            return "".join(child.itertext()).strip()
    return ""


def entry_link(node: ET.Element) -> str:
    for child in list(node):
        if local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href", "").strip()
        rel = child.attrib.get("rel", "alternate")
        if href and rel in {"alternate", ""}:
            return href
        text = "".join(child.itertext()).strip()
        if text:
            return text
    return ""


def html_to_text(value: str) -> str:
    parser = TextExtractor()
    try:
        parser.feed(value)
    except Exception:
        return re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(parser.text())).strip()


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def make_item_id(source: str, external_id: str, url: str, title: str) -> str:
    basis = external_id or url or title
    return hashlib.sha256(f"{source}\n{basis}".encode("utf-8")).hexdigest()


def parse_feed(payload: bytes, source: dict[str, Any]) -> list[FeedItem]:
    root = ET.fromstring(payload)
    nodes = [node for node in root.iter() if local_name(node.tag) in {"item", "entry"}]
    items: list[FeedItem] = []

    for node in nodes:
        title = html_to_text(direct_child_text(node, {"title"}))
        url = entry_link(node)
        external_id = direct_child_text(node, {"guid", "id"})
        summary_html = direct_child_text(node, {"description", "summary", "content", "encoded"})
        summary = html_to_text(summary_html)
        published_raw = direct_child_text(node, {"pubdate", "published", "updated", "date"})
        published_at = parse_datetime(published_raw)

        if not title or not url:
            continue

        items.append(
            FeedItem(
                item_id=make_item_id(source["name"], external_id, url, title),
                source=source["name"],
                category=source.get("category", "AI 情报"),
                title=title,
                url=url,
                summary=summary,
                published_at=published_at,
            )
        )

    return sorted(
        items,
        key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


def http_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None
    headers = {"User-Agent": USER_AGENT}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {response_body[:500]}") from exc


def fetch_feed(source: dict[str, Any]) -> list[FeedItem]:
    # `feed_url` is the explicit field for new source records; keep `url`
    # as a fallback so older local configurations continue to work.
    feed_url = source.get("feed_url") or source.get("url")
    if not feed_url:
        raise ValueError(f"{source.get('name', '未命名来源')} 缺少 feed_url")
    request = urllib.request.Request(feed_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return parse_feed(response.read(), source)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{source['name']} 返回 HTTP {exc.code}") from exc


def load_sources(path: Path) -> list[dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    sources = document.get("sources", [])
    return [source for source in sources if source.get("enabled", True)]


def collect_items(sources: list[dict[str, Any]]) -> tuple[list[FeedItem], list[str]]:
    all_items: list[FeedItem] = []
    errors: list[str] = []
    for source in sources:
        try:
            all_items.extend(fetch_feed(source))
        except Exception as exc:
            errors.append(f"{source['name']}: {exc}")
    return sorted(
        all_items,
        key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    ), errors


def format_time(value: datetime | None) -> str:
    if value is None:
        return "时间未知"
    return value.astimezone(CHINA_TIMEZONE).strftime("%Y-%m-%d %H:%M")


def shorten(value: str, limit: int = 520) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def format_message(item: FeedItem) -> str:
    title = html.escape(item.title)
    source = html.escape(item.source)
    category = html.escape(item.category)
    summary = html.escape(shorten(item.summary or "原始消息未提供摘要，请查看原文。"))
    url = html.escape(item.url, quote=True)
    return (
        f"<b>【链路验证｜{category}】</b>\n\n"
        f"<b>{title}</b>\n\n"
        f"{summary}\n\n"
        f"来源：{source}\n"
        f"时间：{format_time(item.published_at)}\n"
        f'<a href="{url}">查看原文</a>'
    )


def telegram_base_url(token: str) -> str:
    return f"https://api.telegram.org/bot{token}"


def send_telegram(token: str, chat_id: str, text: str) -> None:
    result = http_json(
        f"{telegram_base_url(token)}/sendMessage",
        method="POST",
        payload={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
    )
    if not result.get("ok"):
        raise RuntimeError(f"Telegram 返回失败：{result}")


def discover_chats(token: str) -> list[dict[str, Any]]:
    result = http_json(f"{telegram_base_url(token)}/getUpdates")
    chats: dict[str, dict[str, Any]] = {}
    for update in result.get("result", []):
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is not None:
            chats[str(chat_id)] = {
                "chat_id": chat_id,
                "type": chat.get("type"),
                "name": chat.get("title") or chat.get("username") or chat.get("first_name"),
            }
    return list(chats.values())


def load_state(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return set(data.get("sent", []))


def save_state(path: Path, sent: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"sent": sorted(sent)[-5000:]}, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as temp_file:
        temp_file.write(payload)
        temp_path = Path(temp_file.name)
    temp_path.replace(path)


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"缺少环境变量 {name}，请参考 .env.example 配置。")
    return value


def print_errors(errors: list[str]) -> None:
    for error in errors:
        print(f"[WARN] {error}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="验证 RSS 消息源到 Telegram 的最小闭环。")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument(
        "command",
        choices=["preview", "discover-chat", "send-test", "send-latest", "bootstrap", "run"],
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")
    args = build_parser().parse_args()

    if args.command == "discover-chat":
        chats = discover_chats(require_env("TELEGRAM_BOT_TOKEN"))
        if not chats:
            print("尚未发现聊天。请先打开机器人并发送 /start，然后重试。")
            return 1
        print(json.dumps(chats, ensure_ascii=False, indent=2))
        return 0

    if args.command == "send-test":
        send_telegram(
            require_env("TELEGRAM_BOT_TOKEN"),
            require_env("TELEGRAM_CHAT_ID"),
            "<b>AI 情报链路测试成功</b>\n\n服务器已经可以向 Telegram 发送消息。",
        )
        print("测试消息发送成功。")
        return 0

    sources = load_sources(args.sources)
    items, errors = collect_items(sources)
    print_errors(errors)
    if not items:
        raise RuntimeError("没有从任何消息源获取到可用条目。")

    if args.command == "preview":
        for item in items[: args.limit]:
            print(format_message(item))
            print("\n" + "-" * 72 + "\n")
        return 0

    state = load_state(args.state)

    if args.command == "bootstrap":
        state.update(item.item_id for item in items)
        save_state(args.state, state)
        print(f"已建立基线，共记录 {len(items)} 条现有消息，不发送 Telegram。")
        return 0

    token = require_env("TELEGRAM_BOT_TOKEN")
    chat_id = require_env("TELEGRAM_CHAT_ID")

    if args.command == "send-latest":
        candidates = items[: args.limit]
    else:
        if not args.state.exists():
            state.update(item.item_id for item in items)
            save_state(args.state, state)
            print("首次运行已自动建立基线，没有发送历史消息。再次运行将只发送新消息。")
            return 0
        candidates = [item for item in reversed(items) if item.item_id not in state][: args.limit]

    if not candidates:
        print("没有需要发送的新消息。")
        return 0

    sent_count = 0
    for item in candidates:
        send_telegram(token, chat_id, format_message(item))
        state.add(item.item_id)
        save_state(args.state, state)
        sent_count += 1
    print(f"已成功发送 {sent_count} 条消息。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, ET.ParseError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
