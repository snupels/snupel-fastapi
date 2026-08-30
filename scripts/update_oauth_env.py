"""Merge OAuth deployment values from stdin into the production .env file."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def update_env(path: Path, values: dict[str, str]) -> None:
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    updates = {key: value for key, value in values.items() if value}
    output: list[str] = []
    handled: set[str] = set()

    for line in existing:
        key = line.split("=", 1)[0] if "=" in line and not line.lstrip().startswith("#") else None
        if key in updates:
            output.append(f"{key}={updates[key]}")
            handled.add(key)
        else:
            output.append(line)

    output.extend(f"{key}={value}" for key, value in updates.items() if key not in handled)
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


if __name__ == "__main__":
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in payload.items()):
        raise SystemExit("OAuth environment payload must be a string mapping.")
    update_env(Path(".env"), payload)
