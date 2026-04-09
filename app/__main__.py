from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .services import build_core_services
from .settings import Settings


def main() -> int:
    settings = Settings.load()

    # Windows terminals can default to legacy encodings; force UTF-8 for Vietnamese text output.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(prog="xanhsm-helpcenter-ai")
    parser.add_argument("query", type=str, help="Câu hỏi người dùng")
    parser.add_argument(
        "--raw-dir",
        type=str,
        default=str(settings.raw_dir),
        help="Đường dẫn folder raw/",
    )
    parser.add_argument("--role", type=str, choices=["user", "driver", "merchant"], default=None)
    parser.add_argument(
        "--role-mode",
        type=str,
        choices=["auto", "llm", "rule"],
        default="auto",
        help="Cách phân loại role: auto (ưu tiên LLM nếu có key) | llm | rule",
    )
    parser.add_argument("--k", type=int, default=settings.top_k)
    parser.add_argument("--model", type=str, default=settings.model)
    parser.add_argument("--show-prompt", action="store_true", help="In prompt + KB thay vì gọi LLM")
    args = parser.parse_args()

    effective_settings = settings.with_overrides(raw_dir=Path(args.raw_dir))
    services = build_core_services(effective_settings)

    turn = services.chat_service.process(
        args.query,
        role_mode=args.role_mode,
        role_override=args.role,
        k=args.k,
        model=args.model,
        preview_only=args.show_prompt,
    )

    print(json.dumps(turn.debug, ensure_ascii=False, indent=2))

    if turn.mode == "preview":
        print("\n=== SYSTEM ===\n")
        print(turn.prompt.system)
        print("\n=== USER ===\n")
        print(turn.prompt.user)
        if turn.note:
            print(f"\n[info] {turn.note}")
        elif args.show_prompt or not services.openai_configured:
            print("\n[info] OPENAI_API_KEY chưa được set -> đang chạy chế độ preview prompt.")
        return 0

    print("\n=== ANSWER ===\n")
    print(turn.answer.text.strip())
    print("\n=== METRICS ===\n")
    print(json.dumps(turn.answer.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
