"""Matched text/visual ablation harness. Offline validates packets; --live uses owner credentials."""

import argparse
import copy
import json
from pathlib import Path

from firstlook.challenges import automatic_challenges
from firstlook.config import settings_from
from firstlook.contracts import NarrativeSynthesis, ProposalBatch
from firstlook.discovery import discover
from firstlook.examples import synthetic
from firstlook.ingest import load_table
from firstlook.investigation import run_terra
from firstlook.providers.language import TerraProvider


class Capture:
    """An offline packet recorder, never presented as a model response."""

    records = []

    def propose(self, packet, images):
        self.packet, self.images = packet.model_dump(mode="json"), images
        return ProposalBatch(abstain_reason="Offline packet validation; no model ran")

    def synthesize(self, packet):
        return NarrativeSynthesis(interpretation="Offline packet validation only.", evidence_ids=[])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--seeds", type=int, nargs="+", default=[17, 82])
    args = parser.parse_args()
    if not 1 <= len(args.seeds) <= 5:
        raise SystemExit("Use one to five independent seeds.")
    import tomllib

    path = Path(".streamlit/secrets.toml")
    cfg = settings_from(tomllib.loads(path.read_text()) if path.exists() else {})
    if args.live and not cfg.available("terra"):
        raise SystemExit("Terra credentials are required for --live. No requests sent.")
    report = []
    for kind in ["reversal", "nonlinear", "null"]:
        for seed in args.seeds:
            frame = synthetic(kind, seed=seed)
            dataset = load_table(frame.to_csv(index=False).encode(), f"{kind}-{seed}.csv")
            inv = discover(dataset)
            automatic_challenges(dataset, inv)
            text, visual = Capture(), Capture()
            run_terra(dataset, copy.deepcopy(inv), text, visual=False)
            run_terra(dataset, copy.deepcopy(inv), visual, visual=True)
            assert text.packet == visual.packet
            row = {
                "case": kind,
                "seed": seed,
                "matched": True,
                "packet": text.packet,
                "image_count": len(visual.images),
                "live_model_ran": args.live,
            }
            if args.live:
                conditions = {}
                for label, with_image in [("text", False), ("visual", True)]:
                    trial = copy.deepcopy(inv)
                    run_terra(dataset, trial, TerraProvider(cfg), visual=with_image)
                    conditions[label] = trial.terra
                row["conditions"] = conditions
                row["evaluation_required"] = (
                    "Inspect accepted checks, supported evidence, contradictions, abstention, token/image cost and novel checked findings; do not equate verbosity with insight."
                )
            report.append(row)
    out = Path("reports/terra-ablation-live.json" if args.live else "reports/terra-packets-offline.json")
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{len(report)} matched cases written to {out}. Live provider execution: {args.live}.")
    print("This harness validates bindings; it does not establish that image input improves the app.")


if __name__ == "__main__":
    main()
