# Database Schema

File database chính của ứng dụng hiện tại là `xanhsm_helpcenter.db` và app đang dùng SQLite qua SQLAlchemy.

## Mục đích lưu trữ

Database này dùng để lưu:

- Phiên chat của người dùng
- Các tin nhắn trong từng phiên chat
- Feedback cho một tin nhắn cụ thể
- Một số metadata phục vụ debug, đo hiệu năng và handoff

## Tổng quan các bảng

### `chat_sessions`

Lưu thông tin một phiên hội thoại.

| Cột | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | `VARCHAR(36)` | No | ID phiên chat, thường là UUID |
| `status` | `VARCHAR(32)` | No | Trạng thái phiên, ví dụ `active` |
| `created_at` | `DATETIME` | No | Thời điểm tạo phiên |
| `updated_at` | `DATETIME` | No | Thời điểm cập nhật gần nhất |
| `summary` | `TEXT` | Yes | Tóm tắt ngắn lịch sử hội thoại để giữ context |

Ý nghĩa:

- Một dòng tương ứng một session
- Một session có thể có nhiều message
- Một session có thể có nhiều feedback

### `chat_messages`

Lưu từng tin nhắn phát sinh trong một phiên chat.

| Cột | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | `VARCHAR(36)` | No | ID tin nhắn |
| `session_id` | `VARCHAR(36)` | No | Khóa ngoại tới `chat_sessions.id` |
| `actor` | `VARCHAR(16)` | No | Ai gửi tin nhắn, thường là `user` hoặc `assistant` |
| `content` | `TEXT` | No | Nội dung tin nhắn |
| `role` | `VARCHAR(16)` | Yes | Role phân loại, ví dụ `user`, `driver`, `merchant` |
| `safety` | `BOOLEAN` | No | Có cờ an toàn/sự cố nhạy cảm hay không |
| `handoff_recommended` | `BOOLEAN` | No | Có nên chuyển sang người thật/hotline không |
| `handoff_reason` | `TEXT` | Yes | Lý do đề xuất handoff |
| `model` | `VARCHAR(64)` | Yes | Model LLM đã dùng để tạo câu trả lời |
| `latency_ms` | `FLOAT` | Yes | Độ trễ phản hồi model |
| `input_tokens` | `INTEGER` | Yes | Số token input |
| `output_tokens` | `INTEGER` | Yes | Số token output |
| `total_tokens` | `INTEGER` | Yes | Tổng token |
| `cost_usd_estimate` | `FLOAT` | Yes | Chi phí ước tính |
| `kb_hits_json` | `TEXT` | Yes | Danh sách KB hits được lưu dạng JSON |
| `created_at` | `DATETIME` | No | Thời điểm tạo tin nhắn |

Ý nghĩa:

- Đây là bảng lưu lịch sử chat chính
- Có thể chứa cả message người dùng lẫn assistant
- Ngoài nội dung chat còn lưu metadata để trace pipeline RAG/LLM

### `message_feedback`

Lưu feedback cho một message.

| Cột | Kiểu | Null | Ý nghĩa |
|---|---|---|---|
| `id` | `VARCHAR(36)` | No | ID feedback |
| `session_id` | `VARCHAR(36)` | No | Session chứa message được feedback |
| `message_id` | `VARCHAR(36)` | No | Khóa ngoại tới `chat_messages.id` |
| `verdict` | `VARCHAR(32)` | No | Kết quả feedback, ví dụ `helpful`, `not_helpful` |
| `reason` | `VARCHAR(64)` | No | Lý do feedback |
| `note` | `TEXT` | Yes | Ghi chú thêm của người dùng |
| `created_at` | `DATETIME` | No | Thời điểm tạo feedback |

Ý nghĩa:

- Mỗi feedback gắn với đúng một message
- Dùng để đánh giá chất lượng câu trả lời

## Quan hệ giữa các bảng

- `chat_sessions (1) -> (n) chat_messages`
- `chat_sessions (1) -> (n) message_feedback`
- `chat_messages (1) -> (0..1) message_feedback`

## Index hiện có

- `ix_chat_messages_session_id` trên `chat_messages.session_id`
- `ix_message_feedback_message_id` trên `message_feedback.message_id` và là unique
- `ix_message_feedback_session_id` trên `message_feedback.session_id`

## Database hiện đang lưu gì

Về mặt nghiệp vụ, database đang lưu:

- Danh sách các phiên chat
- Nội dung toàn bộ hội thoại theo từng phiên
- Role được hệ thống suy ra cho từng message
- Cờ safety và handoff
- Metadata gọi model như token, latency, cost
- Danh sách KB hits dùng để trả lời
- Feedback người dùng cho từng message

## Lưu ý quan trọng

- App hiện tại kỳ vọng bảng `chat_sessions` có cột `summary`
- File `xanhsm_helpcenter.db` hiện có 3 bảng đúng như trên, nhưng schema thực tế cũ đang thiếu cột `summary`
- Trong code, cột `summary` đã được thêm ở lớp ORM và có logic `ALTER TABLE ... ADD COLUMN summary TEXT` để tự bù khi app chạy
