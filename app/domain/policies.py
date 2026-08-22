from __future__ import annotations

from dataclasses import dataclass, replace

from app.domain.models import AnalysisResult


@dataclass(frozen=True)
class NotificationPolicy:
    allowed_priorities: frozenset[str] = frozenset({"S", "A", "B"})
    min_confidence: float = 0.75

    def apply(self, result: AnalysisResult) -> AnalysisResult:
        if result.decision == "ignore":
            return result

        if result.decision != "notify":
            return self._ignore(result, "unsupported_decision")

        reason = None
        if result.priority not in self.allowed_priorities:
            reason = f"priority_{result.priority}_not_allowed"
        elif result.confidence < self.min_confidence:
            reason = f"confidence_below_{self.min_confidence:g}"

        if reason is None:
            return result

        return self._ignore(result, reason)

    @staticmethod
    def _ignore(result: AnalysisResult, reason: str) -> AnalysisResult:
        raw = dict(result.raw)
        raw["_notification_policy"] = {
            "original_decision": result.decision,
            "final_decision": "ignore",
            "reason": reason,
        }
        return replace(result, decision="ignore", raw=raw)
