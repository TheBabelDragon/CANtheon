#!/usr/bin/env python3
"""Validate config/chimera-compatibility.json for Chimera Readiness Gate.

Structural validation only (deterministic, no network).
Fails closed on missing/malformed required fields.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "config" / "chimera-compatibility.json"

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")
SUPPORTED_MANIFEST_VERSIONS = frozenset({"1.1", "1.2", "1.3"})


def fail(msg: str) -> None:
    print(f"FAIL  {msg}", file=sys.stderr)
    raise SystemExit(1)


def validate(data: dict[str, Any]) -> None:
    mv = data.get("manifest_version")
    if mv not in SUPPORTED_MANIFEST_VERSIONS:
        fail(f"unsupported manifest_version: {mv!r} (supported: {sorted(SUPPORTED_MANIFEST_VERSIONS)})")

    repos = data.get("repositories")
    if not isinstance(repos, dict) or not repos:
        fail("repositories missing or empty")

    required_keys = ("owner", "repo", "commit", "role", "required")
    for name, entry in repos.items():
        if not isinstance(entry, dict):
            fail(f"repository {name}: entry must be object")
        for k in required_keys:
            if k not in entry:
                fail(f"repository {name}: missing field {k!r}")
        if entry.get("required") is True:
            commit = entry.get("commit") or ""
            if not SHA_RE.match(str(commit)):
                fail(f"repository {name}: commit must be exact 40-char lowercase hex SHA, got {commit!r}")
            if not entry.get("owner") or not entry.get("repo"):
                fail(f"repository {name}: owner/repo required")

    contracts = data.get("contracts")
    if not isinstance(contracts, dict) or not contracts:
        fail("contracts missing or empty")
    for cid, c in contracts.items():
        if not isinstance(c, dict):
            fail(f"contract {cid}: must be object")
        ver = c.get("version")
        if not ver or not VERSION_RE.match(str(ver)):
            fail(f"contract {cid}: version missing or malformed: {ver!r}")
        if not c.get("owner_repo"):
            fail(f"contract {cid}: owner_repo required")
        if c["owner_repo"] not in repos:
            fail(f"contract {cid}: owner_repo {c['owner_repo']!r} not in repositories")

    rels = data.get("compatibility_relationships") or []
    if not isinstance(rels, list):
        fail("compatibility_relationships must be a list")
    for i, rel in enumerate(rels):
        if not isinstance(rel, dict):
            fail(f"relationship[{i}]: must be object")
        for k in ("from", "to", "interface"):
            if k not in rel:
                fail(f"relationship[{i}]: missing {k!r}")
        if rel["from"] not in repos:
            fail(f"relationship[{i}]: from {rel['from']!r} not a declared repository")
        if rel["to"] not in repos:
            fail(f"relationship[{i}]: to {rel['to']!r} not a declared repository")

    cmds = data.get("verification_commands")
    if not isinstance(cmds, dict):
        fail("verification_commands missing")
    for required in ("unit", "smoke", "validate_manifest"):
        if required not in cmds:
            fail(f"verification_commands missing required key: {required}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Chimera compatibility manifest")
    parser.add_argument("manifest", nargs="?", default=str(DEFAULT_MANIFEST),
                        help="path to chimera-compatibility.json")
    args = parser.parse_args(argv)
    path = Path(args.manifest)
    if not path.is_file():
        fail(f"manifest missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"manifest is not valid JSON: {exc}")
    if not isinstance(data, dict):
        fail("manifest root must be an object")
    validate(data)
    repos = data["repositories"]
    print("PASS  chimera-compatibility.json is well-formed")
    print(f"      manifest_version: {data.get('manifest_version')}")
    print(f"      repositories: {len(repos)}")
    print(f"      contracts:    {len(data.get('contracts') or {})}")
    for name, entry in repos.items():
        if entry.get("required"):
            note = " (informational baseline)" if name == "CANtheon" else ""
            print(f"      pin {name}: {entry['commit'][:12]}…{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
