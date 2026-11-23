"""Official TypeSafe SDK integration with strict option identity and abstention."""

from __future__ import annotations

from typing import Any
from dataclasses import asdict, is_dataclass

from firstlook.config import Settings
from firstlook.contracts import DecisionRecord, clean, digest
from firstlook.providers.base import ProviderError, safe_error
from firstlook.visualization.guidance import guidance_for, policy_packet


class JevProvider:
    def __init__(self, settings: Settings, client: Any = None):
        self.settings, self.client = settings, client
        self.calls = 0

    def choose(self, state: dict, options: dict[str, str], instructions: str) -> DecisionRecord:
        if not self.settings.available("jev"):
            raise ProviderError("Jev is not configured. Deterministic ranking remains available.")
        if self.calls >= 4 or not 1 <= len(options) <= 40:
            raise ProviderError("The decision budget or option limit was reached.")
        state = {**state, "chart_policy": policy_packet()}
        instructions = instructions + "\n\n" + guidance_for("jev")
        from typesafe_sdk import Choice, TypeSafeClient, RetryPolicy

        self.calls += 1
        try:
            client = self.client or TypeSafeClient(
                api_key=self.settings.typesafe_api_key,
                model=self.settings.typesafe_model,
                timeout=45,
                retry=RetryPolicy(max_retries=0),
            )
            response = client.system_one(
                state=clean(state),
                questions={"next": Choice(instructions=instructions, criteria=options)},
            )
            answer = response.choices["next"]
            p = dict(answer.probabilities)
            values = sorted(p.values(), reverse=True)
            accepted = (
                answer.choice != "none"
                and p[answer.choice] >= 0.75
                and (len(values) == 1 or values[0] - values[1] >= 0.15)
            )
            usage = getattr(response, "usage", None)
            if hasattr(usage, "model_dump"):
                usage = usage.model_dump()
            elif is_dataclass(usage) and not isinstance(usage, type):
                usage = asdict(usage)
            return DecisionRecord(
                provider="Jev",
                requested_model=self.settings.typesafe_model,
                resolved_model=getattr(response, "model", None),
                state_hash=digest(state),
                options=list(options),
                choice=answer.choice,
                probabilities=p,
                accepted=accepted,
                usage=clean(usage or {}),
                note="Application policy: p ≥ .75 and margin ≥ .15; these are engineering defaults.",
                state=clean(state),
                criteria=options,
                instructions=instructions,
            )
        except Exception as exc:
            raise safe_error("Jev", exc) from exc
