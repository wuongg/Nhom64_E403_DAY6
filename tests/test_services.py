from __future__ import annotations

from pathlib import Path

from app.services import HandoffService, KnowledgeBaseService, RoleService
from app.settings import Settings


ROOT = Path(__file__).resolve().parents[1]


def _settings() -> Settings:
    return Settings().with_overrides(raw_dir=ROOT / "raw")


def test_role_service_uses_rule_mode_without_openai() -> None:
    service = RoleService(_settings())
    decision = service.decide("Tôi là tài xế taxi cần hỗ trợ thu nhập", role_mode="rule")
    assert decision.role == "driver"
    assert decision.driver_type == "taxi"
    assert decision.safety is False


def test_role_service_marks_safety_queries() -> None:
    service = RoleService(_settings())
    decision = service.decide("Tôi vừa bị tai nạn và không an toàn", role_mode="rule")
    assert decision.role == "user"
    assert decision.safety is True


def test_knowledge_base_service_returns_positive_hit_for_vat_question() -> None:
    service = KnowledgeBaseService.load(ROOT / "raw")
    results = service.search("Tôi muốn xuất hóa đơn VAT cho chuyến hôm qua", role="user", k=3)
    assert results
    assert any(result.score > 0 for result in results)
    assert any("VAT" in result.question or "hóa đơn" in result.question.lower() for result in results)


def test_handoff_service_recommends_for_safety() -> None:
    role_service = RoleService(_settings())
    kb_service = KnowledgeBaseService.load(ROOT / "raw")
    handoff_service = HandoffService()

    decision = role_service.decide("Tôi gặp tai nạn khẩn cấp", role_mode="rule")
    results = kb_service.search("Tôi gặp tai nạn khẩn cấp", role=decision.role, k=3)
    handoff = handoff_service.evaluate("Tôi gặp tai nạn khẩn cấp", decision, results)

    assert handoff.recommended is True
    assert handoff.trigger == "safety"


def test_handoff_service_recommends_when_no_positive_kb_hit() -> None:
    role_service = RoleService(_settings())
    kb_service = KnowledgeBaseService.load(ROOT / "raw")
    handoff_service = HandoffService()

    query = "qz-8137 lexical platypus reverse turbine"
    decision = role_service.decide(query, role_mode="rule")
    results = kb_service.search(query, role=decision.role, k=3)
    handoff = handoff_service.evaluate(query, decision, results)

    assert all(result.score == 0 for result in results)
    assert handoff.recommended is True
    assert handoff.trigger == "no_kb_hit"
