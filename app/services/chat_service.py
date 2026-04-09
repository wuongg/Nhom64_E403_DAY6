from __future__ import annotations

from dataclasses import dataclass

from ..llm import ChatResult, chat_openai_with_metrics, has_openai_key
from ..prompting import build_prompt
from ..settings import Settings
from .handoff_service import HandoffService
from .kb_service import KnowledgeBaseService
from .role_service import RoleService
from .types import ChatPrepared, ChatTurnResult


@dataclass(frozen=True, slots=True)
class ChatService:
    settings: Settings
    role_service: RoleService
    kb_service: KnowledgeBaseService
    handoff_service: HandoffService

    def prepare(
        self,
        query: str,
        *,
        role_mode: str = "auto",
        role_override: str | None = None,
        k: int | None = None,
        model: str | None = None,
        preview_only: bool = False,
    ) -> ChatPrepared:
        """Run role classification, KB search, handoff eval, and prompt build.
        Does NOT call the LLM. Used by both process() and the streaming route."""
        active_model = model or self.settings.model
        top_k = k or self.settings.top_k

        decision = self.role_service.decide(
            query,
            role_mode=role_mode,
            role_override=role_override,
            model=active_model,
        )
        kb_results = self.kb_service.search(query, role=decision.role, k=top_k)
        handoff = self.handoff_service.evaluate(query, decision, kb_results)
        prompt = build_prompt(decision, query, [result.entry for result in kb_results])
        debug = prompt.debug if self.settings.enable_debug_fields else {}

        no_llm = preview_only or not has_openai_key()
        return ChatPrepared(
            query=query,
            role_decision=decision,
            kb_results=kb_results,
            kb_hits=tuple(result.to_hit() for result in kb_results),
            handoff=handoff,
            prompt=prompt,
            active_model=active_model,
            mode="preview" if no_llm else "answer",
            preview_only=no_llm,
            note=(
                "preview mode: explicit request"
                if preview_only
                else "preview mode: OPENAI_API_KEY is not configured"
                if no_llm
                else None
            ),
            debug=debug,
        )

    def process(
        self,
        query: str,
        *,
        role_mode: str = "auto",
        role_override: str | None = None,
        k: int | None = None,
        model: str | None = None,
        preview_only: bool = False,
    ) -> ChatTurnResult:
        prepared = self.prepare(
            query,
            role_mode=role_mode,
            role_override=role_override,
            k=k,
            model=model,
            preview_only=preview_only,
        )

        if prepared.preview_only:
            return ChatTurnResult(
                query=query,
                role_decision=prepared.role_decision,
                kb_results=prepared.kb_results,
                kb_hits=prepared.kb_hits,
                handoff=prepared.handoff,
                mode="preview",
                preview_only=True,
                prompt=prepared.prompt,
                answer=None,
                model=prepared.active_model,
                note=prepared.note,
                debug=prepared.debug,
            )

        try:
            answer: ChatResult = chat_openai_with_metrics(
                prepared.prompt.system,
                prepared.prompt.user,
                model=prepared.active_model,
            )
        except Exception as exc:
            failure_debug = dict(prepared.debug)
            failure_debug["llm_error"] = str(exc)
            return ChatTurnResult(
                query=query,
                role_decision=prepared.role_decision,
                kb_results=prepared.kb_results,
                kb_hits=prepared.kb_hits,
                handoff=prepared.handoff,
                mode="preview",
                preview_only=False,
                prompt=prepared.prompt,
                answer=None,
                model=prepared.active_model,
                note=f"OpenAI request failed: {exc}",
                debug=failure_debug,
            )

        return ChatTurnResult(
            query=query,
            role_decision=prepared.role_decision,
            kb_results=prepared.kb_results,
            kb_hits=prepared.kb_hits,
            handoff=prepared.handoff,
            mode="answer",
            preview_only=False,
            prompt=prepared.prompt,
            answer=answer,
            model=answer.model,
            note=None,
            debug=prepared.debug,
        )
