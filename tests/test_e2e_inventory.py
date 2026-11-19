"""Every CLI subcommand must have an end-to-end test (runs in `make check`, not `make e2e`)."""

import argparse
import re
from pathlib import Path

from regrid.cli import _parser

E2E_FILES = sorted(Path(__file__).parent.glob("test_e2e*.py"))


def _subcommands() -> list[str]:
    # argparse keeps subparsers in a private attribute; this test only reads it.
    actions = [a for a in _parser()._actions if isinstance(a, argparse._SubParsersAction)]
    assert len(actions) == 1
    return sorted(actions[0].choices)


def test_every_subcommand_has_an_e2e_test() -> None:
    files = [f for f in E2E_FILES if f.name != Path(__file__).name]
    assert files, "no tests/test_e2e*.py files found"
    text = "\n".join(f.read_text(encoding="utf-8") for f in files)
    missing = [name for name in _subcommands() if not re.search(rf'"{re.escape(name)}"', text)]
    assert not missing, f"CLI subcommands without an e2e test: {missing}"
