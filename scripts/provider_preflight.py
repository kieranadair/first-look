"""Offline adapter checks by default. --live performs explicitly requested billable smoke calls."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from firstlook.config import settings_from
from firstlook.contracts import EvidencePacket
from firstlook.examples import load_example
from firstlook.modeling import run_model
from firstlook.providers.language import TerraProvider
from firstlook.providers.tabpfn import TabPFNProvider
from firstlook.providers.typesafe import JevProvider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true")
    mode.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.live:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_providers_and_terra.py",
                "tests/test_models_and_jobs.py",
            ],
            check=True,
        )
        print("Offline controlled SDK checks passed. No live provider calls were made.")
        return
    import tomllib

    path = Path(".streamlit/secrets.toml")
    cfg = settings_from(tomllib.loads(path.read_text()) if path.exists() else {})
    results = {}
    if cfg.available("jev"):
        record = JevProvider(cfg).choose(
            {"task": "preflight", "support": 100},
            {"supported": "Show the supported distribution", "none": "Abstain"},
            "Choose a supported next view",
        )
        results["jev"] = {"choice": record.choice, "resolved_model": record.resolved_model}
    if cfg.available("terra"):
        p = TerraProvider(cfg)
        packet = EvidencePacket(
            context="preflight", focus=None, fields=[], findings=[], assets=[], allowed_operations=["none"]
        )
        result = p.propose(packet, [])
        results["terra"] = {
            "parsed": True,
            "abstention": result.abstain_reason,
            "resolved_model": p.records[-1]["resolved_model"],
        }
    if cfg.available("tabpfn"):
        ds = load_example("nonlinear")
        run = run_model(ds, ds.context(), "f003", provider=TabPFNProvider(cfg))
        results["tabpfn"] = {
            "actual_provider": run.provider,
            "warnings": run.warnings,
            "record": run.model_record,
        }
    if not results:
        raise SystemExit("No usable provider keys. Add owner secrets; placeholders launch no requests.")
    Path("reports/provider-live.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
