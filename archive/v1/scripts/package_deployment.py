"""Build a runtime-only ZIP from an explicit allowlist; never include actual secrets."""

import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "streamlit_app.py",
    "requirements.txt",
    "requirements-lock.txt",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    ".streamlit/config.toml",
    ".streamlit/secrets.toml.example",
]
DIRECTORIES = ["firstlook", "app_pages", "static", "examples", "resources"]


def main():
    files = [ROOT / name for name in FILES]
    files += [
        p
        for name in DIRECTORIES
        for p in (ROOT / name).rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    ]
    output = ROOT / "dist" / "first-look-deployment.zip"
    output.parent.mkdir(exist_ok=True)
    checksums = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)
    }
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(files):
            archive.write(p, p.relative_to(ROOT))
        archive.writestr("deployment-manifest.json", json.dumps(checksums, indent=2) + "\n")
    print(f"Built {output.name}: {len(files)} runtime files, {output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
