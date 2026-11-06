#!/usr/bin/env python3
"""Generate each populated pack registry twice outside the checkout and validate it."""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "tools" / "registry" / "generate.py"
VALIDATOR = ROOT / "tools" / "validate" / "validate_registry.py"


def run(command: list[str]) -> None:
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed with exit code {result.returncode}: {command}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate each populated protocol registry twice in a temporary "
            "directory, compare canonical bytes, then validate full pack contents."
        )
    )
    parser.add_argument(
        "packs",
        nargs="*",
        type=Path,
        help="protocol pack directories (default: all protocol-* directories)",
    )
    args = parser.parse_args(argv)
    packs = args.packs or sorted(path for path in ROOT.glob("protocol-*") if path.is_dir())

    try:
        with tempfile.TemporaryDirectory(prefix="canary-registry-check-") as temp_name:
            temp = Path(temp_name)
            for pack_arg in packs:
                pack = pack_arg if pack_arg.is_absolute() else ROOT / pack_arg
                if not pack.is_dir():
                    raise RuntimeError(f"{pack_arg}: not a protocol pack directory")
                if not any(path.is_file() for path in pack.rglob("*.toml")):
                    print(f"SKIP: {pack.name}: no fixtures and no release registry is required")
                    continue
                first = temp / f"{pack.name}-first-registry-v1.json"
                second = temp / f"{pack.name}-second-registry-v1.json"
                run([sys.executable, str(GENERATOR), str(pack), "--output", str(first)])
                run([sys.executable, str(GENERATOR), str(pack), "--output", str(second)])
                if first.read_bytes() != second.read_bytes():
                    raise RuntimeError(f"{pack.name}: registry generation is not deterministic")
                print(f"OK: {pack.name}: two isolated registry outputs are byte-identical")
                run(
                    [
                        sys.executable,
                        str(VALIDATOR),
                        str(pack),
                        "--registry",
                        str(first),
                    ]
                )
    except (OSError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
