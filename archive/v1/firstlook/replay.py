"""CLI for inspection and deterministic recomputation. No provider calls."""

import argparse
import json
from pathlib import Path

from firstlook.evidence import import_bundle, recompute


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inspect", "recompute"])
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--data", type=Path)
    args = parser.parse_args()
    raw = args.data.read_bytes() if args.data else None
    ws = import_bundle(args.bundle.read_bytes(), raw, args.data.name if args.data else "original.csv")
    assert ws.dataset is not None and ws.investigation is not None
    if args.action == "inspect":
        print(
            json.dumps(
                {
                    "dataset": ws.dataset.record.name,
                    "findings": len(ws.investigation.findings),
                    "challenges": len(ws.investigation.challenges),
                    "pins": len(ws.pins),
                },
                indent=2,
            )
        )
    else:
        results = recompute(ws)
        print(json.dumps(results, indent=2))
        if any(r["status"] == "different" for r in results):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
