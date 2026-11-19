"""The skill's bundled helpers are generated copies of src/regrid/offline sources."""

import importlib.util
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = Path("plugins/regrid-research/skills/property-research/scripts")
OFFLINE = Path("src/regrid/offline")

_spec = importlib.util.spec_from_file_location(
    "sync_skill_helpers", ROOT / "scripts/sync_skill_helpers.py"
)
assert _spec and _spec.loader
sync_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync_module)


def make_tree(tmp_path: Path) -> Path:
    """Copy the offline sources and skill scripts into a tmp tree mirroring repo paths."""
    shutil.copytree(
        ROOT / OFFLINE, tmp_path / OFFLINE, ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copytree(
        ROOT / SKILL_SCRIPTS, tmp_path / SKILL_SCRIPTS, ignore=shutil.ignore_patterns("__pycache__")
    )
    return tmp_path


def test_skill_copies_match_sources():
    assert sync_module.sync(ROOT, check=True) == []


def test_check_reports_drift_without_writing(tmp_path):
    fake = make_tree(tmp_path)
    (fake / SKILL_SCRIPTS / "map.py").write_text("# edited\n")
    assert sync_module.sync(fake, check=True) == ["map.py"]
    assert (fake / SKILL_SCRIPTS / "map.py").read_text() == "# edited\n"


def test_sync_writes_identical_copy(tmp_path):
    fake = make_tree(tmp_path)
    (fake / SKILL_SCRIPTS / "map.py").write_text("# edited\n")
    assert sync_module.sync(fake, check=False) == ["map.py"]
    assert sync_module.sync(fake, check=True) == []


def test_missing_skill_copy_counts_as_drift(tmp_path):
    fake = make_tree(tmp_path)
    (fake / SKILL_SCRIPTS / "map.py").unlink()
    assert sync_module.sync(fake, check=True) == ["map.py"]
    assert sync_module.sync(fake, check=False) == ["map.py"]
    assert (fake / SKILL_SCRIPTS / "map.py").exists()


def test_cli_check_exit_codes(tmp_path, capsys):
    assert sync_module.main(["--check"], root=ROOT) == 0
    fake = make_tree(tmp_path)
    (fake / SKILL_SCRIPTS / "map.py").write_text("# edited\n")
    assert sync_module.main(["--check"], root=fake) == 1
    assert (
        "out of sync: map.py; run python scripts/sync_skill_helpers.py" in capsys.readouterr().out
    )
    assert sync_module.main([], root=fake) == 0
    assert sync_module.main(["--check"], root=fake) == 0


def test_offline_helpers_import_nothing_from_regrid():
    paths = sorted((ROOT / "src/regrid/offline").glob("*.py"))
    assert {"map.py", "fields.py", "freshness.py"} <= {p.name for p in paths}
    for path in paths:
        assert not re.search(r"^\s*(from|import)\s+regrid\b|^\s*from\s+\.", path.read_text(), re.M)
