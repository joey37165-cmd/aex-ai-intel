from __future__ import annotations

import re
import unicodedata


_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}")
_GENERIC_TERMS = {
    "发布", "推出", "上线", "更新", "新增", "模型", "平台", "支持", "能力", "信息",
    "人工智能", "ai", "new", "release", "update", "model", "api", "available",
}
_IDENTITY_TERMS = {"deepseek", "v4", "flash", "vision", "exp"}


def _tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    tokens: set[str] = set()
    for match in _TOKEN_RE.finditer(normalized):
        token = match.group(0)
        tokens.add(token)
        if all("\u4e00" <= char <= "\u9fff" for char in token):
            tokens.update(token[index:index + 2] for index in range(len(token) - 1))
    return {token for token in tokens if token not in _GENERIC_TERMS}


def _dice(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return 2 * len(left & right) / (len(left) + len(right))


def are_semantic_duplicates(
    left_title: str,
    left_summary: str,
    right_title: str,
    right_summary: str,
) -> bool:
    """Conservative cross-source duplicate detection for the same news event."""
    left_title_tokens = _tokens(left_title)
    right_title_tokens = _tokens(right_title)
    left_all = _tokens(f"{left_title}\n{left_summary}")
    right_all = _tokens(f"{right_title}\n{right_summary}")
    shared_title = left_title_tokens & right_title_tokens
    shared_all = left_all & right_all
    if not shared_title or not shared_all:
        return False
    meaningful_shared = {term for term in shared_all if len(term) >= 2}
    shared_event = meaningful_shared - _IDENTITY_TERMS - _GENERIC_TERMS
    title_score = _dice(left_title_tokens, right_title_tokens)
    all_score = _dice(left_all, right_all)
    if shared_event & shared_title and title_score >= 0.42:
        return True
    if len(shared_event) >= 2 and all_score >= 0.28:
        return True
    # A very close title match can still be the same event when the only
    # stable terms are a model or product identifier.
    return bool(meaningful_shared & _IDENTITY_TERMS) and title_score >= 0.65 and all_score >= 0.4
