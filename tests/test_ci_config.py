"""CI workflow guards for the Windows offline-helper job."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_job_runs_offline_helper_tests():
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "windows-latest" in ci
    for name in ("test_regrid_map.py", "test_skill_helper_sync.py", "test_offline_fields.py"):
        assert name in ci
