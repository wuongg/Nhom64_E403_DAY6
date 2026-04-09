# Hướng Dẫn Chạy Backend

Tai lieu nay mo ta cach chay backend FastAPI cua repo `F:\vin\Nhom64_403`.

## Yeu Cau

- Windows PowerShell
- Python da cai
- Virtual environment `.venv`
- Dependencies trong `requirements.txt`

## Cai Dependencies

Neu chua co `.venv`, tao moi:

```powershell
python -m venv .venv
```

Kich hoat environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Cai thu vien:

```powershell
pip install -r requirements.txt
```

## Bien Moi Truong

Backend doc setting tu `.env` va process env.

Các biến đang hỗ trợ:

- `OPENAI_API_KEY`: API key de goi OpenAI.
- `MODEL`: model mac dinh, hien tai default la `gpt-4o-mini`.
- `RAW_DIR`: duong dan toi folder KB markdown.
- `DB_URL`: SQLite URL.
- `CORS_ORIGINS`: danh sach origin ngan cach bang dau phay.
- `TOP_K`: so ket qua retrieve mac dinh.
- `ENABLE_DEBUG_FIELDS`: bat/tat debug fields.

Vi du set env trong PowerShell:

```powershell
$env:RAW_DIR = "$PWD\raw"
$env:DB_URL = "sqlite:///./xanhsm_helpcenter.db"
$env:MODEL = "gpt-4o-mini"
$env:OPENAI_API_KEY = "YOUR_KEY"
```

Neu muon chay khong goi LLM, co the bo trong `OPENAI_API_KEY` hoac khong set bien nay.

## Lenh Chay Backend

Cach don gian nhat:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

Neu muon reload khi dev:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Sau khi start thanh cong, backend se co dia chi:

```text
http://127.0.0.1:8000
```

## Kiem Tra Nhanh

Health check:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -Method Get
```

Ket qua mong doi:

```json
{
  "status": "ok",
  "kb_loaded": true,
  "openai_configured": true
}
```

## Test 1 Query Thu Cong

### Buoc 1: Tao session

```powershell
$session = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/sessions' -Method Post
$session
```

### Buoc 2: Gui query

```powershell
$body = @{
  message = 'Tôi muốn xuất hóa đơn VAT cho chuyến hôm qua'
  role_mode = 'rule'
  k = 3
} | ConvertTo-Json

$response = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/v1/sessions/$($session.session_id)/messages" `
  -Method Post `
  -ContentType 'application/json; charset=utf-8' `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))

$response
```

### Buoc 3: Doc ket qua

Co 2 truong hop chinh:

- `mode = "answer"`: backend goi duoc OpenAI va tra answer that.
- `mode = "preview"`: backend van detect role, retrieve KB, luu session, nhung khong goi duoc LLM.

Neu `mode = "answer"`, response thuong co:

- `answer`
- `assistant_message_id`
- `metrics`

Neu `mode = "preview"`, response thuong co:

- `answer = null`
- `assistant_message_id = null`
- `metrics = null`

## Lay Lich Su Session

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/sessions/$($session.session_id)" -Method Get
```

## Test Feedback

```powershell
$feedback = @{
  message_id = $response.assistant_message_id
  verdict = 'not_helpful'
  reason = 'wrong_answer'
  note = 'Thiếu hướng dẫn xử lý hoàn tiền'
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/v1/sessions/$($session.session_id)/feedback" `
  -Method Post `
  -ContentType 'application/json; charset=utf-8' `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($feedback))
```

Neu request message dang o `preview` va khong co `assistant_message_id`, co the tam dung `user_message_id` de test feedback.

## Luu Y Van Hanh

- `openai_configured=true` khong dam bao request OpenAI se thanh cong.
- Neu mang ra ngoai bi chan, backend co the tra `preview`.
- KB duoc nap tu `raw/*.md` khi startup.
- SQLite duoc tao schema luc start app.
- File DB mac dinh la `xanhsm_helpcenter.db` o root repo neu khong override `DB_URL`.

## File Lien Quan

- [app/api/main.py](/abs/path/F:/vin/Nhom64_403/app/api/main.py)
- [app/api/routes.py](/abs/path/F:/vin/Nhom64_403/app/api/routes.py)
- [app/settings.py](/abs/path/F:/vin/Nhom64_403/app/settings.py)
- [docs/api.md](/abs/path/F:/vin/Nhom64_403/docs/api.md)
