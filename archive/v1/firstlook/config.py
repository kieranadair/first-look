"""Owner configuration. Placeholder strings are never credentials."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Any


def configured(value: str) -> bool:
    return bool(value.strip()) and not any(
        token in value.lower() for token in ("replace_with", "your-key", "placeholder", "<your")
    )


@dataclass(frozen=True)
class Settings:
    typesafe_api_key: str = field(default="", repr=False)
    tabpfn_token: str = field(default="", repr=False)
    openai_api_key: str = field(default="", repr=False)
    typesafe_model: str = "jev-latest"
    tabpfn_model_path: str = "auto"
    openai_model: str = "gpt-6.1-terra"
    openai_reasoning_effort: str = "medium"
    provider_mode: str = "auto"
    allow_external_analysis: bool = True
    terra_visual_review: bool = True

    def available(self, provider: str) -> bool:
        if self.provider_mode == "offline" or not self.allow_external_analysis:
            return False
        return configured(
            getattr(
                self,
                {"jev": "typesafe_api_key", "tabpfn": "tabpfn_token", "terra": "openai_api_key"}[provider],
            )
        )


def settings_from(mapping: Mapping[str, Any] | None = None) -> Settings:
    mapping = mapping or {}
    providers, app = dict(mapping.get("providers", {})), dict(mapping.get("app", {}))
    keys = {
        "typesafe_api_key": "TYPESAFE_API_KEY",
        "tabpfn_token": "TABPFN_TOKEN",
        "openai_api_key": "OPENAI_API_KEY",
        "typesafe_model": "TYPESAFE_MODEL",
        "tabpfn_model_path": "TABPFN_MODEL_PATH",
        "openai_model": "OPENAI_MODEL",
        "openai_reasoning_effort": "OPENAI_REASONING_EFFORT",
    }
    values: dict[str, Any] = {
        k: os.environ.get(env, providers[k]) if k in providers else os.environ.get(env)
        for k, env in keys.items()
    }
    values = {k: v for k, v in values.items() if v is not None}
    mode = os.environ.get("FIRSTLOOK_PROVIDER_MODE", app.get("provider_mode", "auto"))
    if mode not in {"offline", "live", "auto"}:
        mode = "offline"
    values.update(
        provider_mode=mode,
        allow_external_analysis=bool(app.get("allow_external_analysis", True)),
        terra_visual_review=bool(app.get("terra_visual_review", True)),
    )
    return Settings(**values)
