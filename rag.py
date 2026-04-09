"""
XanhSM Help Center — RAG Chatbot
Dùng Google Gemini API (embedding + generation).
"""

import json
import os
import sys
import io
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from google import genai

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")

load_dotenv(Path(__file__).parent / ".env")

# ── Config ──────────────────────────────────────────────────────────
DATA_PATH = Path(__file__).parent / "data.jsonl"
EMBED_CACHE = Path(__file__).parent / "embeddings.npz"

EMBED_MODEL = "gemini-embedding-001"
GEN_MODEL = "gemini-3.1-flash-lite-preview"

TOP_K = 5  # số FAQ trả về cho mỗi câu hỏi

SYSTEM_PROMPT = """\
Bạn là "Trợ lý điều phối thông minh" của Trung tâm hỗ trợ XanhSM. Nhiệm vụ:
- Tự động rào trước bảo mật: "Do quy định bảo mật, em không thể truy cập dữ liệu chuyến đi cá nhân mà chỉ có thể tra cứu thông tin chung..." (nếu phù hợp).
- Trả lời khách hàng dựa HOÀN TOÀN vào FAQ được cung cấp bên dưới.
- Luôn trình bày quy trình hướng dẫn ở dạng danh sách (checklist 1-2-3) rõ ràng để khách dễ làm theo.
- Thể hiện sự đồng cảm với vấn đề của khách.
- Nếu FAQ không chứa đủ thông tin, nói rõ và hướng dẫn gọi tổng đài.
- KHÔNG bịa thông tin ngoài FAQ.
- Trả lời bằng tiếng Việt.
"""

EMERGENCY_KEYWORDS = ["tai nạn", "công an", "cấp cứu", "bệnh viện", "chảy máu", "va chạm", "tự tử", "đụng xe"]
HANDOFF_KEYWORDS = ["nhân viên", "cskh", "tổng đài", "bực", "tức", "điên", "đền tiền", "kiện", "người thật", "chửi"]
MAX_TURNS_BEFORE_HANDOFF = 3

# ── Helpers ──────────────────────────────────────────────────────────

def load_faq(path: Path) -> list[dict]:
    """Load FAQ entries từ JSONL."""
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cosine similarity giữa vector a và matrix b."""
    a_norm = a / np.linalg.norm(a)
    b_norm = b / np.linalg.norm(b, axis=1, keepdims=True)
    return b_norm @ a_norm


class RAGEngine:
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            print("❌ Cần đặt biến môi trường GEMINI_API_KEY (hoặc GOOGLE_API_KEY).")
            print("   Lấy key tại: https://aistudio.google.com/apikey")
            print()
            print('   set GEMINI_API_KEY=your_key_here   (Windows CMD)')
            print('   export GEMINI_API_KEY=your_key_here (bash/zsh)')
            sys.exit(1)

        self.client = genai.Client(api_key=api_key)
        self.faq = load_faq(DATA_PATH)
        self.texts = [entry["text"] for entry in self.faq]
        self.embeddings: np.ndarray | None = None
        self.history: list[dict] = []
        self.turn_count: int = 0

    # ── Embedding ────────────────────────────────────────────────────

    def build_embeddings(self):
        """Tạo embedding cho toàn bộ FAQ, cache ra file .npz."""
        if EMBED_CACHE.exists():
            print(f"📦 Load embeddings từ cache ({EMBED_CACHE.name})...")
            data = np.load(EMBED_CACHE)
            self.embeddings = data["emb"]
            if len(self.embeddings) == len(self.texts):
                print(f"   ✔ {len(self.embeddings)} vectors loaded.")
                return
            print("   ⚠ Cache không khớp số lượng FAQ, tạo lại...")

        print(f"🔄 Tạo embeddings cho {len(self.texts)} FAQ entries...")
        import time
        BATCH = 15  # free tier = 100 req/min, giữ an toàn
        all_embs = []
        total_batches = (len(self.texts) + BATCH - 1) // BATCH
        for i in range(0, len(self.texts), BATCH):
            batch = self.texts[i : i + BATCH]
            batch_num = i // BATCH + 1
            print(f"   Embedding batch {batch_num}/{total_batches} ({len(batch)} entries)...")
            # Retry on rate limit
            for attempt in range(5):
                try:
                    result = self.client.models.embed_content(
                        model=EMBED_MODEL,
                        contents=batch,
                    )
                    break
                except Exception as e:
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        wait = 15 * (attempt + 1)
                        print(f"   ⏳ Rate limit, chờ {wait}s...")
                        time.sleep(wait)
                    else:
                        raise
            for emb in result.embeddings:
                all_embs.append(emb.values)
            # Chờ giữa các batch để tránh rate limit
            if i + BATCH < len(self.texts):
                time.sleep(10)

        self.embeddings = np.array(all_embs, dtype=np.float32)
        np.savez_compressed(EMBED_CACHE, emb=self.embeddings)
        print(f"   ✔ Saved {len(self.embeddings)} vectors → {EMBED_CACHE.name}")

    # ── Retrieval ────────────────────────────────────────────────────

    def _call_with_retry(self, fn, max_retries=5, timeout=60):
        """Gọi API với retry khi bị rate limit / server overload + timeout chống treo."""
        import time
        import threading

        RETRYABLE = ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"]

        for attempt in range(max_retries):
            result_container = [None]
            error_container = [None]

            def _worker():
                try:
                    result_container[0] = fn()
                except Exception as e:
                    error_container[0] = e

            thread = threading.Thread(target=_worker, daemon=True)
            thread.start()
            thread.join(timeout=timeout)

            if thread.is_alive():
                # Thread vẫn chạy = API bị treo (socket stall)
                wait = 15 * (attempt + 1)
                if attempt < max_retries - 1:
                    print(f"   ⏳ API timeout ({timeout}s), thử lại sau {wait}s... (lần {attempt+1}/{max_retries})")
                    time.sleep(wait)
                    continue
                else:
                    raise TimeoutError(f"API không phản hồi sau {max_retries} lần thử (timeout {timeout}s/lần).")

            if error_container[0] is not None:
                e = error_container[0]
                err_str = str(e)
                if any(code in err_str for code in RETRYABLE) and attempt < max_retries - 1:
                    wait = 15 * (attempt + 1)
                    print(f"   ⏳ API lỗi tạm thời, chờ {wait}s... (lần {attempt+1}/{max_retries})")
                    time.sleep(wait)
                else:
                    raise e

            if result_container[0] is not None:
                return result_container[0]

    def retrieve(self, query: str, top_k: int = TOP_K) -> list[dict]:
        """Tìm top-k FAQ gần nhất với câu hỏi."""
        result = self._call_with_retry(
            lambda: self.client.models.embed_content(
                model=EMBED_MODEL,
                contents=[query],
            )
        )
        q_emb = np.array(result.embeddings[0].values, dtype=np.float32)

        scores = cosine_similarity(q_emb, self.embeddings)
        top_idx = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_idx:
            entry = self.faq[idx]
            results.append({
                "score": float(scores[idx]),
                "category": entry["metadata"]["category"],
                "topic": entry["metadata"]["topic"],
                "question": entry["metadata"]["question"],
                "text": entry["text"],
            })
        return results

    # ── Generation ───────────────────────────────────────────────────

    def trigger_handoff(self, final_query: str, reason: str) -> str:
        """Gom log để chuyển nhân viên CSKH và reset phiên."""
        self.history.append({"role": "user", "parts": [{"text": final_query}]})
        
        # Dùng LLM để tóm tắt vấn đề
        summary_prompt = "Hãy tóm tắt ngắn gọn (tối đa 3-4 dòng) vấn đề cốt lõi mà khách hàng đang gặp phải dựa trên đoạn chat sau để chuyển cho nhân viên CSKH xử lý:\n\n"
        for msg in self.history:
            role_str = "Khách: " if msg["role"] == "user" else "Bot: "
            summary_prompt += f"{role_str}{msg['parts'][0]['text']}\n"
            
        try:
            response = self._call_with_retry(
                lambda: self.client.models.generate_content(
                    model=GEN_MODEL,
                    contents=[summary_prompt],
                    config={"temperature": 0.1, "max_output_tokens": 300}
                )
            )
            summary = response.text.strip()
        except Exception:
            summary = "(Không thể tạo tóm tắt do lỗi API)"
        
        # Reset phiên trò chuyện
        self.history.clear()
        self.turn_count = 0
        
        return (
            f"🚨 [Rào trước] Do bảo mật truy cập dữ liệu và để hỗ trợ anh/chị tốt nhất, "
            f"em xin phép chuyển thông tin này tới nhân viên chăm sóc khách hàng.\n"
            f"* Lý do hệ thống tự động ngắt: {reason}\n"
            f"\n--- GHI CHÚ CHUYỂN GIAO CHO CSKH ---\n{summary}\n--------------------------------------\n\n"
            f"(💡 Bot đã tự động reset toàn bộ lịch sử trò chuyện. Bạn có thể hỏi vấn đề mới.)"
        )

    def answer(self, user_query: str) -> dict:
        """RAG pipeline: retrieve → build context → generate. Trả về dict chứa answer, latency, token."""
        import time
        t_start = time.perf_counter()

        # 0. Pre-generation check (Handoff Thresholds)
        query_lower = user_query.lower()
        if any(kw in query_lower for kw in EMERGENCY_KEYWORDS):
            text = self.trigger_handoff(user_query, "Khách hàng gặp trường hợp khẩn cấp")
            return {"text": text, "latency": time.perf_counter() - t_start, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        if any(kw in query_lower for kw in HANDOFF_KEYWORDS):
            text = self.trigger_handoff(user_query, "Khách hàng yêu cầu gặp nhân viên hoặc có biểu hiện giận dữ")
            return {"text": text, "latency": time.perf_counter() - t_start, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        if self.turn_count >= MAX_TURNS_BEFORE_HANDOFF:
            text = self.trigger_handoff(user_query, f"Vượt quá ngưỡng hỏi đáp tự động ({MAX_TURNS_BEFORE_HANDOFF} lần)")
            return {"text": text, "latency": time.perf_counter() - t_start, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        self.turn_count += 1

        # 1. Retrieve
        docs = self.retrieve(user_query)

        # 2. Build context
        context_parts = []
        for i, doc in enumerate(docs, 1):
            context_parts.append(
                f"[FAQ #{i} | {doc['category']} > {doc['topic']}]\n"
                f"Câu hỏi: {doc['question']}\n"
                f"Score: {doc['score']:.3f}\n"
                f"---\n{doc['text']}\n"
            )
        context = "\n".join(context_parts)

        # 3. Build message with history
        messages = []
        for msg in self.history:
            messages.append(msg)

        user_message = (
            f"Câu hỏi của khách hàng: {user_query}\n\n"
            f"--- FAQ liên quan ---\n{context}"
        )
        messages.append({"role": "user", "parts": [{"text": user_message}]})

        # 4. Generate (with retry + cooldown giữa embed & generate để tránh rate limit)
        time.sleep(2)
        response = self._call_with_retry(
            lambda: self.client.models.generate_content(
                model=GEN_MODEL,
                contents=messages,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "temperature": 0.3,
                    "max_output_tokens": 1024,
                },
            )
        )

        answer_text = response.text
        latency = time.perf_counter() - t_start

        # 5. Trích xuất token usage từ response metadata
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        try:
            usage = response.usage_metadata
            prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
            completion_tokens = getattr(usage, "candidates_token_count", 0) or 0
            total_tokens = getattr(usage, "total_token_count", 0) or (prompt_tokens + completion_tokens)
        except Exception:
            pass

        # 6. Update history (giữ context gọn — chỉ lưu câu hỏi gốc, không lưu FAQ context)
        self.history.append({"role": "user", "parts": [{"text": user_query}]})
        self.history.append({"role": "model", "parts": [{"text": answer_text}]})

        # Giới hạn history để tránh vượt token limit
        MAX_TURNS = 10
        if len(self.history) > MAX_TURNS * 2:
            self.history = self.history[-(MAX_TURNS * 2):]

        return {
            "text": answer_text,
            "latency": latency,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }


# ── CLI Chat Loop ────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  🚗 XanhSM Help Center — RAG Chatbot")
    print("  Powered by Gemini API")
    print("=" * 60)
    print()

    engine = RAGEngine()
    engine.build_embeddings()

    print()
    print("Sẵn sàng! Nhập câu hỏi (gõ 'exit' để thoát, 'debug' để xem FAQ retrieved)")
    print("-" * 60)

    debug_mode = False

    while True:
        try:
            query = input("\n🧑 Bạn: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nTạm biệt! 👋")
            break

        if not query:
            continue
        if query.lower() == "exit":
            print("Tạm biệt! 👋")
            break
        if query.lower() == "debug":
            debug_mode = not debug_mode
            print(f"   Debug mode: {'ON' if debug_mode else 'OFF'}")
            continue

        if debug_mode:
            docs = engine.retrieve(query)
            print("\n   📎 Top FAQ retrieved:")
            for i, doc in enumerate(docs, 1):
                print(f"   {i}. [{doc['score']:.3f}] [{doc['topic']}] {doc['question']}")
            print()

        result = engine.answer(query)
        print(f"\n🤖 Trợ lý: {result['text']}")
        print(f"   ⏱ Latency: {result['latency']:.2f}s | 🪙 Tokens: {result['prompt_tokens']} prompt + {result['completion_tokens']} completion = {result['total_tokens']} total")


if __name__ == "__main__":
    main()
