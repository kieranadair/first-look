"""Evaluate seven labelled routing cases; offline by default, paid only with flags."""

import argparse
import json
from pathlib import Path

from firstlook.judgment_lab import evaluate_cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--allow-paid-requests",
        action="store_true",
        help="Authorise up to seven TypeSafe requests containing only bundled Penguins metadata and synthetic questions; uses TYPESAFE_API_KEY.",
    )
    args = parser.parse_args()
    provider = None
    if args.live:
        if not args.allow_paid_requests:
            parser.error(
                "Live evaluation requires explicit --allow-paid-requests and an owner-approved experimentation budget."
            )
        from firstlook.config import settings_from
        from firstlook.providers.typesafe import JevProvider
        import tomllib

        path = Path(".streamlit/secrets.toml")
        cfg = settings_from(tomllib.loads(path.read_text()) if path.exists() else {})
        provider = JevProvider(cfg, max_calls=7, max_questions=100)
    report = evaluate_cases(provider)
    output = Path("reports/judgment-evaluation.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "judgments"}, indent=2))


if __name__ == "__main__":
    main()
