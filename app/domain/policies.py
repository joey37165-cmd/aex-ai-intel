from __future__ import annotations

from dataclasses import dataclass, replace

from app.domain.models import AnalysisResult


@dataclass(frozen=True)
class NotificationPolicy:
    allowed_priorities: frozenset[str] = frozenset({"S", "A"})
    min_confidence: float = 0.75

    def apply(self, result: AnalysisResult) -> AnalysisResult:
        if result.decision != "notify":
            return result

        reason = None
        if result.priority not in self.allowed_priorities:
            reason = f"priority_{result.priority}_not_allowed"
        elif result.confidence < self.min_confidence:
            reason = f"confidence_below_{self.min_confidence:g}"

        if reason is None:
            return result

        raw = dict(result.raw)
        raw["_notification_policy"] = {
            "original_decision": result.decision,
            "final_decision": "review",
            "reason": reason,
        }
        return replace(result, decision="review", raw=raw)
