# Plan chuyen `app` thanh backend FastAPI

## Summary
- Giu nguyen loi Python hien co cua `app` va boc thanh backend `FastAPI`, thay vi viet lai pipeline RAG.
- Backend v1 phuc vu 3 nhu cau: chat hoi dap, luu session hoi thoai, luu feedback/handoff de frontend dung sau.
- Khong lam auth o v1. Dung SQLite de co persistence that, de demo va khong can them ha tang.
- Giu CLI hien tai hoat dong; backend va CLI dung chung service layer de tranh logic bi tach doi.

## Key Changes
- Them lop `settings` doc `.env` cho `OPENAI_API_KEY`, `MODEL`, `RAW_DIR`, `DB_URL`, `CORS_ORIGINS`, `TOP_K`, `ENABLE_DEBUG_FIELDS`.
- Them service layer ro rang:
  - `RoleService`: boc `decide_role` va `decide_role_with_llm`.
  - `KnowledgeBaseService`: load `raw/*.md` mot lan khi app start, retrieve theo role.
  - `ChatService`: dieu phoi role detect -> retrieve -> build prompt -> goi LLM hoac tra `preview` mode.
  - `HandoffService`: ap heuristic v1 de gan co `handoff_recommended`.
- Heuristic handoff v1 duoc co dinh nhu sau:
  - `true` neu `decision.safety = true`
  - `true` neu user co intent ro kieu "gap nhan vien", "hotline", "nguoi that", "khieu nai", "khan cap"
  - `true` neu retrieve khong co hit co diem > 0
  - nguoc lai `false`
- Them persistence SQLite qua SQLAlchemy 2.x, tao schema luc startup bang `create_all()`; chua dung migration tool o v1.
- Them 3 bang chinh:
  - `chat_sessions`: `id`, `status`, `created_at`, `updated_at`
  - `chat_messages`: `id`, `session_id`, `actor`, `content`, `role`, `safety`, `handoff_recommended`, `handoff_reason`, `model`, `latency_ms`, `input_tokens`, `output_tokens`, `total_tokens`, `cost_usd_estimate`, `kb_hits_json`, `created_at`
  - `message_feedback`: `id`, `session_id`, `message_id`, `verdict`, `reason`, `note`, `created_at`
- Public API v1:
  - `GET /health`: tra `status`, `kb_loaded`, `openai_configured`
  - `POST /api/v1/sessions`: tao session moi, tra `session_id`, `created_at`
  - `GET /api/v1/sessions/{session_id}`: tra metadata session va toan bo message theo thoi gian
  - `POST /api/v1/sessions/{session_id}/messages`
    - Request: `message`, `role_override?`, `role_mode=auto|llm|rule`, `k?`, `model?`
    - Response: `session_id`, `user_message_id`, `assistant_message_id?`, `mode=answer|preview`, `answer?`, `role_decision`, `kb_hits`, `handoff_recommended`, `handoff_reason`, `metrics?`
  - `POST /api/v1/sessions/{session_id}/feedback`
    - Request: `message_id`, `verdict=helpful|not_helpful`, `reason=wrong_intent|wrong_answer|missing_info|handoff_needed|other`, `note?`
    - Response: `feedback_id`, `stored=true`
- Quy uoc response:
  - `kb_hits` chi tra metadata can cho UI: `id`, `topic`, `question`, `category`
  - `metrics` chi co khi thuc su goi LLM
  - neu thieu `OPENAI_API_KEY`, endpoint `/messages` van chay pipeline va luu log nhung tra `mode="preview"` cung `answer=null`
- To chuc code:
  - them module API rieng trong `app`
  - giu `app/__main__.py` cho CLI nhung refactor de goi chung service layer
  - khong dung toi cau truc `raw/` ngoai viec tai su dung loader hien co

## Implementation Notes
- FastAPI app dung lifespan de:
  - load settings
  - preload KB vao memory
  - khoi tao DB schema
  - cau hinh CORS cho frontend dev
- Pydantic models phai tach rieng cho request/response de frontend co contract ro rang.
- Message flow chuan:
  - nhan user message
  - luu user message
  - detect role
  - retrieve KB
  - build prompt
  - neu co key thi goi LLM va luu assistant message
  - neu khong co key thi khong sinh assistant answer that, van luu ban ghi preview
  - tra response cho frontend
- Session API chua can multi-tenant hay ownership vi khong co auth v1.
- Khong lam streaming/SSE o v1; response dong bo JSON mot luot.
- Khong tich hop CRM/ticket that o v1; handoff chi la co va ly do de frontend hien thi nut/chuyen luong sau nay.

## Test Plan
- Unit test cho `RoleService`, `KnowledgeBaseService`, `HandoffService`.
- API test cho:
  - `GET /health` tra dung trang thai khi co va khong co `OPENAI_API_KEY`
  - tao session thanh cong
  - gui message o `role_mode=rule`
  - gui message o `preview` mode khi khong co key
  - luu feedback thanh cong
  - truy van session tra dung lich su message
  - query safety sinh `handoff_recommended=true`
  - query khong match KB sinh `handoff_recommended=true`
- Mock loi goi OpenAI de test deterministic, khong phu thuoc network.
- Acceptance scenario:
  - nguoi dung hoi VAT -> backend tra answer + KB hits + metrics
  - nguoi dung bao su co an toan -> backend gan `handoff_recommended` ngay
  - nguoi dung cham `not_helpful` -> feedback duoc luu va truy van lai thay trong DB

## Assumptions
- Backend dat trong package `app`, khong tao service repo moi.
- `raw/*.md` tiep tuc la source of truth cua KB va duoc reload khi restart app.
- SQLite du cho demo/prototype; chua toi uu concurrent write cao.
- Khong auth, khong rate limit, khong streaming o v1.
- Neu sau nay can production hoa, buoc ke tiep se la them migration, structured logging, va auth/API key protection.
