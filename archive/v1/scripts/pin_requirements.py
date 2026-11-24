"""Record the resolved Linux/Python 3.12 dependency graph used for this build."""

from importlib.metadata import distribution, version
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOTS = [
    "streamlit",
    "pandas",
    "numpy",
    "scipy",
    "scikit-learn",
    "pyarrow",
    "pydantic",
    "openai",
    "typesafe-sdk",
    "tabpfn-client",
    "matplotlib",
    "httpx",
    "threadpoolctl",
    "pint",
]
DEV = ["pytest", "hypothesis", "ruff", "ty", "playwright", "psutil"]


def main():
    found = {}
    pending = ROOTS.copy()
    while pending:
        name = canonicalize_name(pending.pop())
        if name in found:
            continue
        dist = distribution(name)
        found[name] = dist.version
        for raw in dist.requires or []:
            req = Requirement(raw)
            if req.marker is None or req.marker.evaluate({"extra": ""}):
                pending.append(req.name)
    Path("requirements-lock.txt").write_text(
        "# Resolved runtime graph · Python 3.12/Linux · 2026-11-22\n"
        + "\n".join(f"{k}=={v}" for k, v in sorted(found.items()))
        + "\n"
    )
    Path("requirements.txt").write_text(
        "# Streamlit Community Cloud: choose Python 3.12.\n-c requirements-lock.txt\n"
        + "\n".join(f"{k}=={version(k)}" for k in ROOTS)
        + "\n"
    )
    Path("requirements-dev.txt").write_text(
        "-r requirements.txt\n" + "\n".join(f"{k}=={version(k)}" for k in DEV) + "\n"
    )
    print(f"Pinned {len(ROOTS)} runtime roots and {len(found)} resolved packages.")


if __name__ == "__main__":
    main()
