from __future__ import annotations

from ..role_tree import RoleDecision
from ..textnorm import normalize_for_match
from .types import KnowledgeBaseSearchResult, HandoffDecision


_HANDOFF_INTENT_PHRASES = (
    "gap nhan vien",
    "hotline",
    "nguoi that",
    "khieu nai",
    "khan cap",
)


class HandoffService:
    def evaluate(
        self,
        query: str,
        decision: RoleDecision,
        kb_results: tuple[KnowledgeBaseSearchResult, ...],
    ) -> HandoffDecision:
        if decision.safety:
            return HandoffDecision(
                recommended=True,
                reason="handoff recommended because safety is true",
                trigger="safety",
            )

        normalized = normalize_for_match(query)
        if any(phrase in normalized for phrase in _HANDOFF_INTENT_PHRASES):
            return HandoffDecision(
                recommended=True,
                reason="handoff recommended because user asked for human support or escalation",
                trigger="intent",
            )

        if not any(result.score > 0 for result in kb_results):
            return HandoffDecision(
                recommended=True,
                reason="handoff recommended because no KB hit scored above zero",
                trigger="no_kb_hit",
            )

        return HandoffDecision(
            recommended=False,
            reason="handoff not needed because KB has at least one scored hit",
            trigger="kb_match",
        )
