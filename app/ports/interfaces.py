from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from app.domain.models import AnalysisResult, ContentItem, DigestCandidate, DigestReport, ReportWindow


class SourceAdapter(Protocol):
    def fetch(self, source: dict) -> Iterable[ContentItem]: ...


@runtime_checkable
class ContentEnricher(Protocol):
    def enrich(self, item: ContentItem, source: dict) -> ContentItem: ...


class Analyzer(Protocol):
    def analyze(self, item: ContentItem) -> AnalysisResult: ...


class DigestGenerator(Protocol):
    prompt_version: str

    def generate(self, window: ReportWindow, items: list[DigestCandidate]) -> DigestReport: ...


class Notifier(Protocol):
    def send(self, text: str) -> str: ...
