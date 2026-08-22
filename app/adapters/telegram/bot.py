from __future__ import annotations

import json
import os
import urllib.request


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, timeout: float = 25.0) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id
        self.timeout = timeout

    def send(self, text: str) -> str:
        request = urllib.request.Request(
            f"{self.base_url}/sendMessage",
            data=json.dumps({"chat_id": self.chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Aex-AI-Intel/0.1"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError(f"Telegram 返回失败：{result}")
        return str(result.get("result", {}).get("message_id", ""))

    def send_photo(self, photo_url: str, caption: str) -> str:
        request = urllib.request.Request(
            f"{self.base_url}/sendPhoto",
            data=json.dumps({
                "chat_id": self.chat_id, "photo": photo_url, "caption": caption,
                "parse_mode": "HTML", "disable_notification": False,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Aex-AI-Intel/0.1"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError(f"Telegram 返回失败：{result}")
        return str(result.get("result", {}).get("message_id", ""))


def build_notifier() -> TelegramNotifier:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID")
    return TelegramNotifier(token, chat_id)
