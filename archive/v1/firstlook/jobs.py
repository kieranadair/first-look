"""Bounded, session-owned work. Worker threads never touch Streamlit."""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Event, RLock
from typing import Any, Callable


@dataclass
class Job:
    id: str
    owner: str
    context: str
    key: str
    state: str = "queued"
    stage: str = "Preparing investigation"
    result: Any = None
    error: str = ""
    created: float = field(default_factory=time.monotonic)
    cancelled: Event = field(default_factory=Event)


class JobManager:
    def __init__(self, capacity: int = 2, ttl: int = 600, deadline: float = 360):
        self.pool = ThreadPoolExecutor(max_workers=capacity, thread_name_prefix="firstlook")
        self.lock = RLock()
        self.jobs: dict[str, Job] = {}
        self.capacity, self.ttl = capacity, ttl
        self.deadline = deadline

    def submit(self, owner: str, context: str, key: str, task: Callable) -> str:
        with self.lock:
            self.jobs = {
                i: j
                for i, j in self.jobs.items()
                if j.state in {"running", "queued"} or time.monotonic() - j.created < self.ttl
            }
            for j in self.jobs.values():
                if (j.owner, j.context, j.key) == (owner, context, key) and j.state in {"queued", "running"}:
                    return j.id
            if any(j.owner == owner and j.state in {"queued", "running"} for j in self.jobs.values()):
                raise ValueError(
                    "Your current task is still running. Cancel or wait before starting another."
                )
            if sum(j.state in {"queued", "running"} for j in self.jobs.values()) >= self.capacity:
                raise ValueError("The shared analysis workers are busy. Try again shortly.")
            job = Job(uuid.uuid4().hex, owner, context, key)
            self.jobs[job.id] = job

        def work():
            def should_cancel():
                if time.monotonic() - job.created > self.deadline:
                    job.cancelled.set()
                return job.cancelled.is_set()

            def progress(stage: str):
                with self.lock:
                    job.stage = stage

            with self.lock:
                job.state = "running"
            try:
                result = task(progress, should_cancel)
                with self.lock:
                    if should_cancel():
                        job.state = "cancelled"
                    else:
                        job.result, job.state, job.stage = result, "completed", "Ready"
            except Exception as exc:
                with self.lock:
                    job.error = str(exc)[:300]
                    job.state = "cancelled" if job.cancelled.is_set() else "failed"

        self.pool.submit(work)
        return job.id

    def get(self, owner: str, job_id: str) -> Job | None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None or job.owner != owner:
                return None
            if job and job.state in {"queued", "running"} and time.monotonic() - job.created > self.deadline:
                job.cancelled.set()
                job.stage = "Application deadline reached; detaching from in-flight provider work."
            return job

    def cancel(self, owner: str, job_id: str) -> None:
        with self.lock:
            job = self.get(owner, job_id)
            if job:
                job.cancelled.set()
                job.stage = "Cancellation requested; remote work may still be billable."

    def forget(self, owner: str, job_id: str) -> None:
        with self.lock:
            job = self.get(owner, job_id)
            if job and job.state not in {"running", "queued"}:
                self.jobs.pop(job_id)
