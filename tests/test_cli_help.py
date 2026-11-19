"""Every top-level CLI command has a real help string."""

from __future__ import annotations

import argparse

from regrid.cli import _parser

BARE_NAME_COMMANDS = {
    "address",
    "apn",
    "owner",
    "parcel",
    "parcel-path",
    "typeahead",
    "verse",
    "usage",
    "client-token-typeahead",
    "tilejson",
}


def _top_level_help() -> dict[str, str]:
    parser = _parser()
    subparsers = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return {
        action.dest: action.help or ""
        for action in subparsers._choices_actions
        if action.dest in subparsers.choices
    }


def test_every_top_level_command_has_help_text() -> None:
    helps = _top_level_help()
    assert helps
    for name, text in helps.items():
        assert text.strip(), f"{name} has no help text"


def test_help_text_is_not_the_bare_command_name() -> None:
    helps = _top_level_help()
    for name in BARE_NAME_COMMANDS:
        assert helps[name].strip() != name, f"{name} help is its own name"
