"""Build credential-free Claude packages from one canonical set of skills."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

SOURCE = Path(__file__).resolve().parents[1] / "plugins" / "regrid-research"
MCP_URL = "https://support.regrid.com/mcp"
SKILLS = ("property-research", "setup")
BASE_FILES = (".claude-plugin/plugin.json", ".mcp.json", "README.md")
TOKEN_PATTERN = re.compile(rb"rg_[A-Za-z0-9_-]{8,}")


def read_public_file(root: Path, relative: str) -> bytes:
    """Read an allowlisted file only after rejecting symlinks in every component."""
    path = root
    for component in Path(relative).parts:
        path = path / component
        if path.is_symlink():
            raise ValueError(f"Symlink not allowed in package: {relative}")
    data = path.read_bytes()
    if TOKEN_PATTERN.search(data) or b"-----BEGIN PRIVATE KEY-----" in data:
        raise ValueError(f"Possible credential in package file: {relative}")
    return data


def skill_files(root: Path, name: str) -> dict[str, bytes]:
    prefix = f"skills/{name}"
    result = {f"{prefix}/SKILL.md": read_public_file(root, f"{prefix}/SKILL.md")}
    references = root / prefix / "references"
    if references.is_symlink():
        raise ValueError(f"Symlink not allowed in package: {prefix}/references")
    if references.exists():
        for path in sorted(references.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise ValueError(f"Symlink not allowed in package: {relative}")
            if path.is_file() and path.suffix in {".md", ".json"}:
                if any(part.startswith(".") for part in path.relative_to(references).parts):
                    continue
                if path.name.lower().startswith(("credentials", "secrets")):
                    continue
                result[relative] = read_public_file(root, relative)
    if name == "property-research":
        relative = f"{prefix}/scripts/workflow.py"
        result[relative] = read_public_file(root, relative)
    return result


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def write_archive(path: Path, files: dict[str, bytes]) -> None:
    """Use stable ordering, timestamps, and permissions for reproducible output."""
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    with ZipFile(path) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(files):
            raise ValueError("Archive integrity check failed")


def build(source: Path, output: Path) -> list[Path]:
    if source.is_symlink():
        raise ValueError("Plugin source cannot be a symlink")
    common = {name: read_public_file(source, name) for name in BASE_FILES}
    manifest = json.loads(common[".claude-plugin/plugin.json"])
    version = manifest["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Plugin version must be three numeric components")
    for name in SKILLS:
        common.update(skill_files(source, name))
    local_config = json.loads(common[".mcp.json"])
    expected = {
        "mcpServers": {
            "regrid": {
                "command": "npx",
                "args": [
                    "-y",
                    "mcp-remote",
                    MCP_URL,
                    "--header",
                    "x-regrid-token: ${REGRID_TOKEN}",
                ],
                "env": {"REGRID_TOKEN": "${REGRID_TOKEN}"},
            }
        }
    }
    if local_config != expected:
        raise ValueError("Local MCP config must use the approved token placeholder bridge")
    cowork = dict(common)
    cowork[".mcp.json"] = json_bytes({"mcpServers": {"regrid": {"type": "http", "url": MCP_URL}}})
    standalone = {
        name.removeprefix("skills/"): data
        for name, data in common.items()
        if name.startswith("skills/property-research/")
    }
    output.mkdir(parents=True, exist_ok=True)
    paths = []
    for label, files in (
        ("regrid-research-cowork", cowork),
        ("regrid-research-claude-code", common),
        ("regrid-property-research-skill", standalone),
    ):
        path = output / f"{label}-{version}.zip"
        write_archive(path, files)
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=SOURCE.parents[1] / "dist")
    args = parser.parse_args()
    for path in build(args.source, args.output):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
