"""Small, source-linked conditional design rules; no claim of universal optimality."""

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def registry() -> dict:
    return json.loads((Path(__file__).resolve().parent.parent / "resources" / "rules.json").read_text())


def rule_details(rule_ids: list[str]) -> list[dict]:
    rules = registry()["rules"]
    return [{"id": rid, **rules[rid]} for rid in rule_ids if rid in rules]
