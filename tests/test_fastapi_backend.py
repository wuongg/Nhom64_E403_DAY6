from __future__ import annotations

import importlib
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_MODULE_CANDIDATES = (
    "app.api",
    "app.api.main",
    "app.main",
    "app.api.app",
    "app.fastapi_app",
    "app.server",
)


def _clear_app_modules() -> None:
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules.pop(name, None)


def _load_test_client():
    try:
        framework_path = ROOT / "app" / "api" / "framework.py"
        spec = importlib.util.spec_from_file_location("backend_test_framework", framework_path)
        if spec is None or spec.loader is None:
            raise FileNotFoundError(framework_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        TestClient = getattr(module, "TestClient")
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Backend test client is unavailable: {exc}")

    importlib.invalidate_caches()
    last_error: Exception | None = None

    for module_name in APP_MODULE_CANDIDATES:
        _clear_app_modules()
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name.startswith("app.") or exc.name in {module_name, module_name.split(".")[0]}:
                last_error = exc
                continue
            if exc.name in {"anyio", "httpx", "pydantic", "sqlalchemy"}:
                pytest.skip(f"Backend dependencies are unavailable while importing {module_name}: {exc}")
            raise

        for attr in ("create_app", "build_app", "get_app"):
            factory = getattr(module, attr, None)
            if factory is None:
                continue
            app = factory() if callable(factory) else factory
            if app is not None:
                return TestClient(app)

        app = getattr(module, "app", None)
        if app is not None:
            return TestClient(app)

        last_error = RuntimeError(f"{module_name} has no app factory or app object")

    pytest.skip(f"FastAPI backend entrypoint not found yet: {last_error!r}")


def _configure_env(monkeypatch: pytest.MonkeyPatch, db_path: Path, openai_key: str | None = None) -> None:
    # Tests assume the backend reads these settings from process env at startup.
    monkeypatch.setenv("RAW_DIR", str(ROOT / "raw"))
    monkeypatch.setenv("DB_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("ENABLE_DEBUG_FIELDS", "1")
    if openai_key is None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OPENAI_API_KEY", openai_key)


def _rows(db_path: Path, table: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(f"SELECT * FROM {table} ORDER BY created_at").fetchall()
    finally:
        conn.close()


def _message_payload(message: str, role_mode: str = "rule", k: int = 3) -> dict[str, object]:
    # The plan describes JSON bodies for messages; this keeps the tests aligned to that contract.
    return {"message": message, "role_mode": role_mode, "k": k}


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "backend.sqlite3"


def test_health_reports_kb_and_openai_state_without_key(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    _configure_env(monkeypatch, db_path, openai_key=None)
    with _load_test_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"ok", "healthy"}
    assert data["kb_loaded"] is True
    assert data["openai_configured"] is False


def test_health_reports_openai_configured_when_key_exists(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    _configure_env(monkeypatch, db_path, openai_key="test-key")
    with _load_test_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["kb_loaded"] is True
    assert data["openai_configured"] is True


def test_session_creation_message_flow_and_history_persist(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    _configure_env(monkeypatch, db_path, openai_key=None)
    with _load_test_client() as client:
        created = client.post("/api/v1/sessions")
        assert created.status_code in {200, 201}
        session_id = created.json()["session_id"]

        first_message = client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json=_message_payload("Tôi bị trừ tiền 2 lần khi đặt chuyến", role_mode="rule"),
        )
        assert first_message.status_code == 200
        first_data = first_message.json()
        assert first_data["session_id"] == session_id
        assert first_data["role_decision"]["role"] == "user"
        assert isinstance(first_data["kb_hits"], list)
        if first_data["kb_hits"]:
            kb_hit = first_data["kb_hits"][0]
            assert {"id", "topic", "question", "category"} <= set(kb_hit)

        second_message = client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json=_message_payload("Tôi muốn xuất hóa đơn VAT cho chuyến đi", role_mode="rule"),
        )
        assert second_message.status_code == 200
        second_data = second_message.json()
        assert second_data["session_id"] == session_id

        history = client.get(f"/api/v1/sessions/{session_id}")
        assert history.status_code == 200
        history_data = history.json()
        assert history_data["session_id"] == session_id

    message_rows = _rows(db_path, "chat_messages")
    assert len(message_rows) >= 2
    user_rows = [row for row in message_rows if row["actor"] == "user"]
    assert user_rows[0]["content"] == "Tôi bị trừ tiền 2 lần khi đặt chuyến"
    assert user_rows[1]["content"] == "Tôi muốn xuất hóa đơn VAT cho chuyến đi"

    session_rows = _rows(db_path, "chat_sessions")
    assert len(session_rows) == 1
    assert session_rows[0]["id"] == session_id


def test_preview_mode_without_openai_key(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    _configure_env(monkeypatch, db_path, openai_key=None)
    with _load_test_client() as client:
        created = client.post("/api/v1/sessions")
        session_id = created.json()["session_id"]

        response = client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json=_message_payload("Tôi cần hỗ trợ hóa đơn VAT", role_mode="rule"),
        )

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "preview"
    assert data["answer"] is None
    assert data.get("metrics") is None
    assert data["session_id"] == session_id


def test_feedback_is_persisted(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    _configure_env(monkeypatch, db_path, openai_key=None)
    with _load_test_client() as client:
        created = client.post("/api/v1/sessions")
        session_id = created.json()["session_id"]

        message = client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json=_message_payload("Tôi bị trừ tiền 2 lần", role_mode="rule"),
        ).json()

        message_id = message.get("assistant_message_id") or message["user_message_id"]
        feedback = client.post(
            f"/api/v1/sessions/{session_id}/feedback",
            json={
                "message_id": message_id,
                "verdict": "not_helpful",
                "reason": "wrong_answer",
                "note": "Thiếu hướng dẫn xử lý hoàn tiền",
            },
        )

    assert feedback.status_code == 200
    data = feedback.json()
    assert data["stored"] is True
    assert data["session_id"] == session_id

    rows = _rows(db_path, "message_feedback")
    assert len(rows) == 1
    row = rows[0]
    assert row["session_id"] == session_id
    assert row["message_id"] == message_id
    assert row["verdict"] == "not_helpful"
    assert row["reason"] == "wrong_answer"
    assert row["note"] == "Thiếu hướng dẫn xử lý hoàn tiền"


def test_safety_and_no_kb_match_trigger_handoff(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    _configure_env(monkeypatch, db_path, openai_key=None)
    with _load_test_client() as client:
        created = client.post("/api/v1/sessions")
        session_id = created.json()["session_id"]

        safety = client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json=_message_payload("Tôi vừa gặp tai nạn, không an toàn, cần hỗ trợ khẩn cấp", role_mode="rule"),
        )
        assert safety.status_code == 200
        safety_data = safety.json()
        assert safety_data["role_decision"]["safety"] is True
        assert safety_data["handoff_recommended"] is True

        no_match = client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json=_message_payload("qz-8137 lexical platypus reverse turbine", role_mode="rule"),
        )
        assert no_match.status_code == 200
        no_match_data = no_match.json()
        assert no_match_data["handoff_recommended"] is True
