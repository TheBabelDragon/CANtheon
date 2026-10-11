#!/usr/bin/env python3
"""Validate config/chimera-compatibility.json for Chimera Readiness Gate.

Fails closed when required repository revisions, schema versions, or
contract versions are missing or malformed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "config" / "chimera-compatibility.json"

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")


def fail(msg: str) -> None:
    print(f"FAIL  {msg}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    if not MANIFEST_PATH.is_file():
        fail(f"manifest missing: {MANIFEST_PATH}")

    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"manifest is not valid JSON: {exc}")

    if data.get("manifest_version") != "1.1":
        fail(f"unsupported manifest_version: {data.get('manifest_version')!r}")

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
                fail(
                    f"repository {name}: commit must be exact 40-char SHA, "
                    f"got {commit!r}"
                )
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

    cmds = data.get("verification_commands")
    if not isinstance(cmds, dict) or "smoke" not in cmds or "unit" not in cmds:
        fail("verification_commands must include at least unit and smoke")

    print("PASS  chimera-compatibility.json is well-formed")
    print(f"      repositories: {len(repos)}")
    print(f"      contracts:    {len(contracts)}")
    for name, entry in repos.items():
        if entry.get("required"):
            print(f"      pin {name}: {entry['commit'][:12]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
