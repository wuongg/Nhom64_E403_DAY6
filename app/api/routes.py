from __future__ import annotations

import json
from datetime import datetime

from pydantic import ValidationError

from ..db import FeedbackWrite, MessageWrite
from ..db.contracts import ChatMessageRecord
from .framework import APIRouter, HTTPException, Request
from .schemas import (
    CreateSessionResponse,
    FeedbackRequest,
    FeedbackResponse,
    KBHitResponse,
    MessageItemResponse,
    MessageRequest,
    MessageResponse,
    MetricsResponse,
    RoleDecisionResponse,
    SessionDetailResponse,
)


router = APIRouter(prefix="/api/v1")


def _container(request: Request):
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise HTTPException(503, "Application container is not ready")
    return container


def _iso(value: datetime) -> str:
    return value.isoformat()


def _kb_hits_from_json(raw: str | None) -> list[dict]:
    if not raw:
        return []
    return json.loads(raw)


def _role_decision_payload(decision) -> RoleDecisionResponse:
    return RoleDecisionResponse(
        role=decision.role,
        safety=decision.safety,
        driver_type=decision.driver_type,
        reason=decision.reason,
    )


def _kb_hits_payload(hits) -> list[KBHitResponse]:
    return [
        KBHitResponse(
            id=hit.id,
            topic=hit.topic,
            question=hit.question,
            category=hit.category,
        )
        for hit in hits
    ]


def _metrics_payload(result) -> MetricsResponse:
    return MetricsResponse(**result.to_dict(), usage=result.to_dict()["usage"])


def _message_item_payload(message: ChatMessageRecord) -> MessageItemResponse:
    return MessageItemResponse(
        id=message.id,
        actor=message.actor,
        content=message.content,
        role=message.role,
        safety=message.safety,
        handoff_recommended=message.handoff_recommended,
        handoff_reason=message.handoff_reason,
        model=message.model,
        latency_ms=message.latency_ms,
        input_tokens=message.input_tokens,
        output_tokens=message.output_tokens,
        total_tokens=message.total_tokens,
        cost_usd_estimate=message.cost_usd_estimate,
        kb_hits=[KBHitResponse(**hit) for hit in _kb_hits_from_json(message.kb_hits_json)],
        created_at=_iso(message.created_at),
    )


@router.post("/sessions")
def create_session(request: Request) -> CreateSessionResponse:
    container = _container(request)
    record = container.store.create_session()
    return CreateSessionResponse(
        session_id=record.id,
        created_at=_iso(record.created_at),
    )


@router.get("/sessions/{session_id}")
def get_session(request: Request, session_id: str) -> SessionDetailResponse:
    container = _container(request)
    detail = container.store.get_session_details(session_id)
    if detail is None:
        raise HTTPException(404, "Session not found")

    return SessionDetailResponse(
        session_id=detail.session.id,
        status=detail.session.status,
        created_at=_iso(detail.session.created_at),
        updated_at=_iso(detail.session.updated_at),
        messages=[_message_item_payload(message) for message in detail.messages],
    )


@router.post("/sessions/{session_id}/messages")
async def post_message(request: Request, session_id: str) -> MessageResponse:
    container = _container(request)
    if container.store.get_session(session_id) is None:
        raise HTTPException(404, "Session not found")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(400, f"Invalid JSON body: {exc}") from exc

    try:
        body = MessageRequest(**(payload or {}))
    except ValidationError as exc:
        raise HTTPException(422, exc.errors()) from exc

    turn = container.chat_service.process(
        body.message,
        role_mode=body.role_mode,
        role_override=body.role_override,
        k=body.k,
        model=body.model,
    )

    user_message = container.store.add_message(
        MessageWrite(
            session_id=session_id,
            actor="user",
            content=body.message,
            role=turn.role_decision.role,
            safety=turn.role_decision.safety,
            handoff_recommended=turn.handoff.recommended,
            handoff_reason=turn.handoff.reason,
            model=turn.model,
            kb_hits=[hit.to_public_dict() for hit in turn.kb_results],
        )
    )

    assistant_message = None
    if turn.answer is not None:
        assistant_message = container.store.add_message(
            MessageWrite(
                session_id=session_id,
                actor="assistant",
                content=turn.answer.text,
                role=turn.role_decision.role,
                safety=turn.role_decision.safety,
                handoff_recommended=turn.handoff.recommended,
                handoff_reason=turn.handoff.reason,
                model=turn.answer.model,
                latency_ms=turn.answer.latency_ms,
                input_tokens=turn.answer.usage.input_tokens,
                output_tokens=turn.answer.usage.output_tokens,
                total_tokens=turn.answer.usage.total_tokens,
                cost_usd_estimate=turn.answer.cost_usd_estimate,
                kb_hits=[hit.to_public_dict() for hit in turn.kb_results],
            )
        )

    return MessageResponse(
        session_id=session_id,
        user_message_id=user_message.id,
        assistant_message_id=None if assistant_message is None else assistant_message.id,
        mode=turn.mode,
        answer=None if turn.answer is None else turn.answer.text,
        role_decision=_role_decision_payload(turn.role_decision),
        kb_hits=_kb_hits_payload(turn.kb_hits),
        handoff_recommended=turn.handoff.recommended,
        handoff_reason=turn.handoff.reason,
        metrics=None if turn.answer is None else _metrics_payload(turn.answer),
    )


@router.post("/sessions/{session_id}/feedback")
async def post_feedback(request: Request, session_id: str) -> FeedbackResponse:
    container = _container(request)
    if container.store.get_session(session_id) is None:
        raise HTTPException(404, "Session not found")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(400, f"Invalid JSON body: {exc}") from exc

    try:
        body = FeedbackRequest(**(payload or {}))
    except ValidationError as exc:
        raise HTTPException(422, exc.errors()) from exc

    message = container.store.get_message(body.message_id)
    if message is None or message.session_id != session_id:
        raise HTTPException(404, "Message not found for session")

    record = container.store.add_feedback(
        FeedbackWrite(
            session_id=session_id,
            message_id=body.message_id,
            verdict=body.verdict,
            reason=body.reason,
            note=body.note,
        )
    )
    return FeedbackResponse(
        feedback_id=record.id,
        session_id=session_id,
        stored=True,
    )
