"""Every top-level CLI command has a real help string."""

from __future__ import annotations

import argparse

from regrid.cli import _parser


def _top_level_help() -> dict[str, str]:
    parser = _parser()
    subparsers = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    helps = {action.dest: action.help or "" for action in subparsers._choices_actions}
    # Every real subcommand must be listed (a missing help entry would be skipped otherwise).
    assert set(helps) == set(subparsers.choices)
    return helps


def test_every_top_level_command_has_descriptive_help_text() -> None:
    helps = _top_level_help()
    assert {"point", "address", "freshness", "map", "tile"} <= set(helps)
    for name, text in helps.items():
        # Empty, the bare command name, or a single word is not a description.
        assert len(text.split()) >= 3, f"{name} help is not descriptive: {text!r}"
        assert text.strip().lower() != name, f"{name} help is its own name"
