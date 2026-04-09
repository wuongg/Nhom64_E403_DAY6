# API Backend

Tai lieu nay mo ta API hien tai cua backend FastAPI trong repo `F:\vin\Nhom64_403`.

## Base URL

Mac dinh khi chay local:

```text
http://127.0.0.1:8000
```

## Entry Point

Backend duoc expose tai module:

```text
app.api.main:app
```

Co the chay bang app instance:

```powershell
.venv\Scripts\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

Hoac chay bang factory:

```powershell
.venv\Scripts\python.exe -m uvicorn app.api.main:create_app --factory --host 127.0.0.1 --port 8000
```

## Health Check

### `GET /health`

Tra trang thai backend, tinh trang KB va xem backend co doc duoc `OPENAI_API_KEY` hay khong.

Response mau:

```json
{
  "status": "ok",
  "kb_loaded": true,
  "openai_configured": true
}
```

Luu y:

- `openai_configured=true` chi co nghia la backend doc thay API key.
- Neu mang ra ngoai bi chan hoac OpenAI loi, endpoint chat van co the roi ve `mode="preview"`.

## Session API

### `POST /api/v1/sessions`

Tao session moi.

Request body:

```json
{}
```

Response mau:

```json
{
  "session_id": "a27c56de-0b8f-45d2-afba-01c4f652a0ad",
  "created_at": "2026-04-09T14:20:01.123456"
}
```

### `GET /api/v1/sessions/{session_id}`

Lay metadata session va lich su message.

Response mau:

```json
{
  "session_id": "a27c56de-0b8f-45d2-afba-01c4f652a0ad",
  "status": "open",
  "created_at": "2026-04-09T14:20:01.123456",
  "updated_at": "2026-04-09T14:20:08.654321",
  "messages": [
    {
      "id": "e9df498e-9f1b-4422-9e1e-854fa2269492",
      "actor": "user",
      "content": "Tôi muốn xuất hóa đơn VAT cho chuyến hôm qua",
      "role": "user",
      "safety": false,
      "handoff_recommended": false,
      "handoff_reason": "handoff not needed because KB has at least one scored hit",
      "model": "gpt-4o-mini",
      "latency_ms": null,
      "input_tokens": null,
      "output_tokens": null,
      "total_tokens": null,
      "cost_usd_estimate": null,
      "kb_hits": [
        {
          "id": "643a454e6136b782620683982fd2111a",
          "topic": "3. Cước phí và Phương thức thanh toán",
          "question": "3.4. Hướng dẫn yêu cầu xuất hóa đơn VAT và cách kiểm tra hóa đơn với các chuyến xe Xanh SM",
          "category": "Dành cho người dùng"
        }
      ],
      "created_at": "2026-04-09T14:20:08.654321"
    }
  ]
}
```

## Message API

### `POST /api/v1/sessions/{session_id}/messages`

Gui 1 user message vao session.

Request body:

```json
{
  "message": "Tôi muốn xuất hóa đơn VAT cho chuyến hôm qua",
  "role_mode": "rule",
  "k": 3
}
```

Truong ho tro:

- `message`: bat buoc, noi dung cau hoi.
- `role_override`: tuy chon, `user|driver|merchant`.
- `role_mode`: `auto|llm|rule`.
- `k`: so KB hit toi da.
- `model`: override model cho request hien tai.

Response khi goi LLM thanh cong:

```json
{
  "session_id": "a27c56de-0b8f-45d2-afba-01c4f652a0ad",
  "user_message_id": "e9df498e-9f1b-4422-9e1e-854fa2269492",
  "assistant_message_id": "cf44ab64-5c80-4091-9a1e-140768ae996c",
  "mode": "answer",
  "answer": "Để xuất hóa đơn VAT cho chuyến xe hôm qua, bạn cần yêu cầu xuất hóa đơn trước khi chuyến đi kết thúc...",
  "role_decision": {
    "role": "user",
    "safety": false,
    "driver_type": null,
    "reason": "default"
  },
  "kb_hits": [
    {
      "id": "643a454e6136b782620683982fd2111a",
      "topic": "3. Cước phí và Phương thức thanh toán",
      "question": "3.4. Hướng dẫn yêu cầu xuất hóa đơn VAT và cách kiểm tra hóa đơn với các chuyến xe Xanh SM",
      "category": "Dành cho người dùng"
    }
  ],
  "handoff_recommended": false,
  "handoff_reason": "handoff not needed because KB has at least one scored hit",
  "metrics": {
    "model": "gpt-4o-mini",
    "latency_ms": 2753.37,
    "usage": {
      "input_tokens": 1839,
      "output_tokens": 123,
      "total_tokens": 1962
    },
    "cost_usd_estimate": 0.00034965
  }
}
```

Response khi backend khong goi duoc LLM:

```json
{
  "session_id": "4db75809-d07f-49ef-9f26-cdc34ae6fdab",
  "user_message_id": "e9df498e-9f1b-4422-9e1e-854fa2269492",
  "assistant_message_id": null,
  "mode": "preview",
  "answer": null,
  "role_decision": {
    "role": "user",
    "safety": false,
    "driver_type": null,
    "reason": "default"
  },
  "kb_hits": [
    {
      "id": "643a454e6136b782620683982fd2111a",
      "topic": "3. Cước phí và Phương thức thanh toán",
      "question": "3.4. Hướng dẫn yêu cầu xuất hóa đơn VAT và cách kiểm tra hóa đơn với các chuyến xe Xanh SM",
      "category": "Dành cho người dùng"
    }
  ],
  "handoff_recommended": false,
  "handoff_reason": "handoff not needed because KB has at least one scored hit",
  "metrics": null
}
```

Luu y:

- User message luon duoc luu vao DB.
- Assistant message chi duoc luu khi `turn.answer` ton tai.
- `kb_hits` chi tra metadata can cho UI.

## Feedback API

### `POST /api/v1/sessions/{session_id}/feedback`

Luu feedback cho 1 message trong session.

Request body:

```json
{
  "message_id": "cf44ab64-5c80-4091-9a1e-140768ae996c",
  "verdict": "not_helpful",
  "reason": "wrong_answer",
  "note": "Thiếu hướng dẫn xử lý hoàn tiền"
}
```

Gia tri hop le:

- `verdict`: `helpful|not_helpful`
- `reason`: `wrong_intent|wrong_answer|missing_info|handoff_needed|other`

Response mau:

```json
{
  "feedback_id": "f0f5d73e-8eb8-475f-9f0b-0d4f6fd4b2a1",
  "session_id": "a27c56de-0b8f-45d2-afba-01c4f652a0ad",
  "stored": true
}
```

## Error Cases

Mot so loi API dang co:

- `404 Session not found`
- `404 Message not found for session`
- `400 Invalid JSON body: ...`
- `422` khi body sai schema
- `503 Application container is not ready`

## PowerShell Examples

Tao session:

```powershell
$session = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/sessions' -Method Post
$session
```

Gui message:

```powershell
$body = @{
  message = 'Tôi muốn xuất hóa đơn VAT cho chuyến hôm qua'
  role_mode = 'rule'
  k = 3
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/v1/sessions/$($session.session_id)/messages" `
  -Method Post `
  -ContentType 'application/json; charset=utf-8' `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

Lay history:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/sessions/$($session.session_id)" -Method Get
```
