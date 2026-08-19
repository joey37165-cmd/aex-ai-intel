from __future__ import annotations

import email
import email.header
import email.message
import imaplib
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime, parseaddr
from html.parser import HTMLParser

from app.domain.models import ContentItem


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def _plain(value: str) -> str:
    parser = _TextParser()
    try:
        parser.feed(value)
        value = " ".join(parser.parts)
    except Exception:
        pass
    return re.sub(r"\s+", " ", value).strip()


def _decode_header(value: str) -> str:
    parts: list[str] = []
    for text, charset in email.header.decode_header(value or ""):
        if isinstance(text, bytes):
            parts.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(text)
    return _plain("".join(parts))


def _body(message: email.message.Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() == "text/plain":
                return _plain(part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace"))
        for part in message.walk():
            if part.get_content_type() == "text/html":
                return _plain(part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace"))
        return ""
    payload = message.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return _plain(str(payload or ""))
    return _plain(payload.decode(message.get_content_charset() or "utf-8", errors="replace"))


def _matches_sender(message: email.message.Message, source: dict) -> bool:
    expected_address = str(source.get("from_address", "")).strip().casefold()
    expected_name = str(source.get("from_name", "")).strip().casefold()
    sender_name, sender_address = parseaddr(message.get("From", ""))
    if expected_address and sender_address.strip().casefold() != expected_address:
        return False
    if expected_name and _decode_header(sender_name).casefold() != expected_name:
        return False
    return True


class EmailSourceAdapter:
    def fetch(self, source: dict) -> list[ContentItem]:
        host = str(source.get("imap_host", "")).strip()
        username = os.environ.get(str(source.get("username_env", "")), "").strip()
        password = os.environ.get(str(source.get("password_env", "")), "")
        if not host or not username or not password:
            raise RuntimeError(f"{source.get('name', source.get('id'))} 缺少 IMAP 配置或凭据环境变量")
        folder = str(source.get("folder", "INBOX"))
        days = max(1, int(source.get("lookback_days", 2)))
        timeout_seconds = max(1, min(int(source.get("timeout_seconds", 20)), 60))
        client = imaplib.IMAP4_SSL(host, int(source.get("imap_port", 993)), timeout=timeout_seconds)
        try:
            client.login(username, password)
            status, _ = client.select(folder, readonly=True)
            if status != "OK":
                raise RuntimeError(f"无法打开邮箱文件夹：{folder}")
            since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
            search_criteria = ["SINCE", since]
            from_address = str(source.get("from_address", "")).strip()
            if from_address:
                search_criteria.extend(["FROM", f'"{from_address}"'])
            status, data = client.search(None, *search_criteria)
            if status != "OK":
                raise RuntimeError("IMAP 搜索失败")
            result: list[ContentItem] = []
            max_items = max(1, min(int(source.get("max_items", 50)), 200))
            for message_id in data[0].split()[-max_items:]:
                status, fetched = client.fetch(message_id, "(RFC822)")
                if status != "OK":
                    continue
                raw = next((part[1] for part in fetched if isinstance(part, tuple)), None)
                if not isinstance(raw, bytes):
                    continue
                message = email.message_from_bytes(raw)
                if not _matches_sender(message, source):
                    continue
                subject = _decode_header(message.get("Subject", ""))
                if not subject:
                    continue
                url = message.get("X-Source-URL", "") or f"email://{host}/{message_id.decode(errors='ignore')}"
                date = message.get("Date", "")
                try:
                    published = parsedate_to_datetime(date).astimezone(timezone.utc)
                except (TypeError, ValueError, OverflowError):
                    published = None
                body = _body(message)
                external_id = message.get("Message-ID", "") or message_id.decode(errors="ignore")
                result.append(ContentItem(
                    item_id=f"email:{source['id']}:{external_id}", source_id=source["id"],
                    source_name=source.get("name", source["id"]), category=source.get("category", "Email 情报"),
                    title=subject, url=url, summary=body[:4000], published_at=published,
                ))
            return result
        finally:
            try:
                client.logout()
            except Exception:
                pass
