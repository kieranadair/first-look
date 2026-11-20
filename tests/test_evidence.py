import io
import zipfile

import pytest

from firstlook.evidence import brief, export_bundle, import_bundle, read_bundle, recompute
from firstlook.state import Workspace, pin


def make_workspace(dataset, investigation):
    ws = Workspace()
    ws.load(dataset)
    ws.investigation = investigation
    pin(ws, investigation.findings[0].id)
    ws.pins[0]["note"] = "Check this with the domain owner."
    return ws


def test_export_import_and_recompute(dataset, investigation):
    ws = make_workspace(dataset, investigation)
    data = export_bundle(ws, True)
    copy = import_bundle(data)
    assert copy.replay and copy.pins == ws.pins
    assert copy.investigation.context.id == investigation.context.id
    assert all(x["status"] == "match" for x in recompute(copy))
    assert "changed" in brief(copy)


def test_data_free_inspection_and_required_original(dataset, investigation):
    data = export_bundle(make_workspace(dataset, investigation), False)
    copy = import_bundle(data)
    assert copy.dataset.frame.empty
    with pytest.raises(ValueError, match="original"):
        recompute(copy)
    with pytest.raises(ValueError, match="fingerprint"):
        import_bundle(data, b"x\n1\n2\n")


@pytest.mark.parametrize("path", ["../escape.json", "/absolute.json", "a\\escape.json", "run.py"])
def test_unsafe_archive_rejected(path):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr(path, "{}")
    with pytest.raises(ValueError):
        read_bundle(data.getvalue())


def test_checksum_modification_rejected(dataset, investigation):
    data = export_bundle(make_workspace(dataset, investigation))
    source = zipfile.ZipFile(io.BytesIO(data))
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as z:
        for name in source.namelist():
            z.writestr(name, source.read(name) if name != "brief.md" else b"modified")
    with pytest.raises(ValueError, match="checksum"):
        read_bundle(target.getvalue())


def test_fresh_process_cli_recompute(dataset, investigation, tmp_path):
    import subprocess
    import sys

    path = tmp_path / "evidence.zip"
    path.write_bytes(export_bundle(make_workspace(dataset, investigation), True))
    result = subprocess.run(
        [sys.executable, "-m", "firstlook.replay", "recompute", str(path)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "different" not in result.stdout
