# Nhom064-403 — XanhSM Help Center AI

Prototype chatbot hỗ trợ khách hàng Xanh SM, gồm FastAPI backend, web frontend tĩnh và pipeline RAG trên kho tri thức nội bộ trong thư mục `raw/`.

## Chức năng chính

- Phân loại ngữ cảnh câu hỏi theo vai trò `user | driver | merchant`.
- Truy xuất Knowledge Base từ các file markdown trong `raw/` và trả về top-k nội dung liên quan.
- Sinh câu trả lời bằng OpenAI khi có `OPENAI_API_KEY`.
- Tự động rơi về `preview mode` khi chưa cấu hình API key hoặc gọi LLM thất bại.
- Quản lý hội thoại theo session, lưu lịch sử tin nhắn và metadata vào SQLite.
- Tóm tắt memory cho hội thoại dài để giữ ngữ cảnh cho các lượt chat tiếp theo.
- Đánh dấu handoff khi có tín hiệu an toàn, cần escalte sang người thật, hoặc KB không đủ dữ liệu.
- Hỗ trợ web search tùy chọn bằng Serper/SerpAPI cho các câu hỏi cần dữ liệu cập nhật theo thời gian.
- Frontend web có health check, chat streaming qua SSE, lịch sử session cục bộ và gửi feedback cho câu trả lời.

## Kiến trúc

- `app/api`: FastAPI app, schema và route.
- `app/services`: role routing, KB retrieval, memory, handoff, web search.
- `app/db`: lớp lưu trữ SQLite cho session, message, feedback.
- `frontend/index.html`: giao diện chat một trang, gọi API backend.
- `raw/`: nguồn dữ liệu markdown cho KB.
- `docs/api.md`: mô tả chi tiết contract API.

## API chính

Backend mặc định chạy ở `http://127.0.0.1:8000`.

- `GET /health`: kiểm tra trạng thái backend, KB và cấu hình OpenAI.
- `POST /api/v1/sessions`: tạo session mới.
- `GET /api/v1/sessions/{session_id}`: lấy metadata và lịch sử hội thoại.
- `POST /api/v1/sessions/{session_id}/messages`: gửi câu hỏi và nhận câu trả lời dạng JSON.
- `POST /api/v1/sessions/{session_id}/messages/stream`: stream câu trả lời qua SSE.
- `POST /api/v1/sessions/{session_id}/feedback`: lưu feedback cho câu trả lời.

Xem chi tiết request/response trong [docs/api.md](/F:/vin/Nhom64_403/docs/api.md).

## Cấu hình môi trường

Sao chép `.env.example` thành `.env` và điền các giá trị cần thiết:

```powershell
Copy-Item .env.example .env
```

Biến môi trường quan trọng:

- `OPENAI_API_KEY`: bật chế độ trả lời bằng LLM. Nếu bỏ trống, hệ thống chạy preview mode.
- `MODEL`: model mặc định, hiện tại là `gpt-4o-mini`.
- `RAW_DIR`: thư mục chứa KB markdown, mặc định là `./raw`.
- `DB_URL`: đường dẫn SQLite.
- `ENABLE_WEB_SEARCH`: bật/tắt web search.
- `SERPER_API_KEY` hoặc `SERPAPI_API_KEY`: khóa cho web search.

## Chạy bằng Docker

Yêu cầu: Docker Desktop hoặc Docker Engine có `docker compose`.

1. Tạo file `.env` nếu chưa có.
2. Build và khởi động stack:

```powershell
docker compose up -d --build
```

3. Truy cập dịch vụ:

- Frontend: `http://localhost:8080`
- Backend API: `http://localhost:8000`
- Health check: `http://localhost:8000/health`

4. Xem log khi cần:

```powershell
docker compose logs -f backend
docker compose logs -f frontend
```

5. Dừng stack:

```powershell
docker compose down
```

Ghi chú Docker:

- `raw/` được mount read-only vào container backend tại `/data/raw`.
- SQLite được persist qua volume `db_data`.
- Frontend tự động gọi backend ở cùng hostname, cổng `8000`, nên chạy được với `localhost` và `127.0.0.1`.

## Chạy local không dùng Docker

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Chạy backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

Chạy frontend:

```powershell
.\.venv\Scripts\python.exe -m http.server 3000 --directory frontend
```

Khi chạy local, frontend mặc định gọi API ở `http://127.0.0.1:8000`.

## CLI prototype

Xem prompt và KB mà chưa gọi OpenAI:

```powershell
python -m app "Mình bị trừ tiền 2 lần" --show-prompt
```

Gọi OpenAI qua CLI:

```powershell
$env:OPENAI_API_KEY="YOUR_KEY"
python -m app "Mình muốn xuất hóa đơn VAT cho chuyến hôm qua"
```

## Kiểm thử

Chạy test:

```powershell
pytest -q
```

Đánh giá RAG bằng script có sẵn:

```powershell
python eval_ragas.py --n 10 --k 5 --role-mode rule --answer-model gpt-4o-mini --evaluator-model gpt-4o-mini --out ragas_results.json
```
