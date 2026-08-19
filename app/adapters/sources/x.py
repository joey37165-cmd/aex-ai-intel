from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from app.domain.models import ContentItem


class XSourceAdapter:
    """Official X API v2 recent search adapter; requires a Bearer Token."""

    def fetch(self, source: dict) -> list[ContentItem]:
        token = os.environ.get(str(source.get("bearer_token_env", "")), "").strip()
        query = str(source.get("query", "")).strip()
        if not token or not query:
            raise RuntimeError(f"{source.get('name', source.get('id'))} 缺少 X API Bearer Token 或 query")
        max_results = max(10, min(int(source.get("max_results", 20)), 100))
        params = urllib.parse.urlencode({
            "query": query,
            "max_results": max_results,
            "tweet.fields": "created_at,author_id,lang",
            "expansions": "author_id",
            "user.fields": "username,name",
        })
        request = urllib.request.Request(
            f"https://api.x.com/2/tweets/search/recent?{params}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": "Aex-AI-Intel/0.1"},
        )
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
        users = {user["id"]: user for user in payload.get("includes", {}).get("users", [])}
        result: list[ContentItem] = []
        for tweet in payload.get("data", []):
            tweet_id = str(tweet.get("id", ""))
            text = str(tweet.get("text", "")).strip()
            if not tweet_id or not text:
                continue
            author = users.get(str(tweet.get("author_id", "")), {})
            username = author.get("username", "unknown")
            published = None
            if tweet.get("created_at"):
                published = datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00")).astimezone(timezone.utc)
            result.append(ContentItem(
                item_id=f"x:{tweet_id}", source_id=source["id"], source_name=source.get("name", f"X @{username}"),
                category=source.get("category", "X AI 情报"), title=f"@{username}：{text[:180]}",
                url=f"https://x.com/{username}/status/{tweet_id}", summary=text, published_at=published,
            ))
        return result
