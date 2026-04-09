from __future__ import annotations

from dataclasses import replace

from ..llm import has_openai_key
from ..role_llm import decide_role_with_llm
from ..role_tree import RoleDecision, decide_role
from ..settings import Settings


class RoleService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def settings(self) -> Settings:
        return self._settings

    def decide(
        self,
        query: str,
        *,
        role_mode: str = "auto",
        role_override: str | None = None,
        model: str | None = None,
    ) -> RoleDecision:
        active_model = model or self._settings.model

        if role_mode == "rule":
            decision = decide_role(query)
        elif role_mode == "llm":
            decision = decide_role_with_llm(query, model=active_model)
        elif role_mode == "auto":
            if has_openai_key():
                decision = decide_role_with_llm(query, model=active_model)
            else:
                decision = decide_role(query)
        else:
            raise ValueError("role_mode must be one of: auto, llm, rule")

        if role_override is None:
            return decision

        if role_override not in {"user", "driver", "merchant"}:
            raise ValueError("role_override must be one of: user, driver, merchant")

        return replace(
            decision,
            role=role_override,
            reason=f"override role={role_override}; original={decision.reason}",
        )
