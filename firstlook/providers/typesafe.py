"""Official TypeSafe SDK integration with strict option identity and abstention."""

from __future__ import annotations

from typing import Any
from dataclasses import asdict, is_dataclass

from firstlook.config import Settings
from firstlook.contracts import DecisionRecord, clean, digest
from firstlook.providers.base import ProviderError, safe_error
from firstlook.visualization.guidance import guidance_for, policy_packet
from firstlook.judgments import JudgmentBatch, JudgmentSpec, TRUST_BOUNDARY, decode_answer, request_input_size


class JevProvider:
    def __init__(
        self,
        settings: Settings,
        client: Any = None,
        *,
        max_calls: int = 8,
        max_questions: int = 256,
        max_input_bytes: int = 384_000,
    ):
        self.settings, self.client = settings, client
        self.calls = 0
        self.questions = 0
        self.input_bytes = 0
        self.max_calls, self.max_questions, self.max_input_bytes = max_calls, max_questions, max_input_bytes
        self.records: list[JudgmentBatch] = []

    def judge(
        self, state: dict, specifications: list[JudgmentSpec], *, context: str, purpose: str
    ) -> JudgmentBatch:
        """Ask independent typed questions; record the exact payload and code policy."""
        import time
        from typesafe_sdk import Choice, Noul, Score, TypeSafeClient, RetryPolicy

        if not self.settings.available("jev"):
            raise ProviderError("Jev is not configured; local analysis remains available.")
        if not 1 <= len(specifications) <= 40 or len({s.id for s in specifications}) != len(specifications):
            raise ProviderError("A batch needs one to forty uniquely named questions.")
        state = clean(state)
        questions = {}
        for spec in specifications:
            instructions = TRUST_BOUNDARY + "\n" + spec.question
            if spec.kind == "noul":
                questions[spec.id] = Noul(
                    instructions=instructions, criteria={"true": spec.yes, "false": spec.no}
                )
            elif spec.kind == "choice":
                questions[spec.id] = Choice(instructions=instructions, criteria=spec.options)
            else:
                questions[spec.id] = Score(instructions=instructions, criteria=spec.levels)
        size = request_input_size(state, specifications)
        if (
            size > 48_000
            or self.calls >= self.max_calls
            or self.questions + len(specifications) > self.max_questions
            or self.input_bytes + size > self.max_input_bytes
        ):
            raise ProviderError("The bounded Jev request, question or input budget was reached.")
        self.calls += 1
        self.questions += len(specifications)
        self.input_bytes += size
        try:
            client = self.client or TypeSafeClient(
                api_key=self.settings.typesafe_api_key,
                model=self.settings.typesafe_model,
                timeout=45,
                retry=RetryPolicy(max_retries=0),
            )
            started = time.perf_counter()
            response = client.system_one(state=state, questions=questions)
            elapsed = (time.perf_counter() - started) * 1000
            if set(response.answers) != set(questions):
                raise ValueError("The provider omitted a requested answer or returned an unknown question.")
            answers = {
                s.id: decode_answer(s, response.answers[s.id].model_dump(mode="json")) for s in specifications
            }
            usage = (
                response.usage.model_dump()
                if hasattr(response.usage, "model_dump")
                else asdict(response.usage)
                if is_dataclass(response.usage)
                else response.usage
            )
            record = JudgmentBatch(
                id=digest(
                    [
                        context,
                        purpose,
                        self.settings.typesafe_model,
                        response.model,
                        state,
                        [s.model_dump() for s in specifications],
                        {k: v.model_dump() for k, v in answers.items()},
                    ]
                ),
                purpose=purpose,
                context=context,
                requested_model=self.settings.typesafe_model,
                resolved_model=response.model,
                state=state,
                state_hash=digest(state),
                definitions=specifications,
                answers=answers,
                usage=clean(usage or {}),
                latency_ms=elapsed,
            )
            self.records.append(record)
            return record
        except Exception as exc:
            raise safe_error("Jev", exc) from exc

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
