#!/usr/bin/env python3
r"""Cross-validate a protocol pack's fixtures against its generated registry (CF-02 section 6).

The registry is not committed in a source checkout. With no ``--registry``
argument this tool generates the canonical registry into a temporary directory
and validates it there. CI supplies the twice-generated temporary output so it
can check deterministic bytes and full pack consistency without writing to a
contributor branch. A consumer may also pass an archive-extracted or otherwise
generated registry explicitly:

* every regular ``*.toml`` file in the pack must be listed in the registry's
  ``fixtures[]`` array (an *orphaned* fixture is rejected, naming its path);
* every ``fixtures[]`` entry, and every payload under it, must exist in the
  pack as a regular file (a phantom entry is rejected, naming its path);
* the SHA-256 of each file must equal the ``sha256`` recorded for it (a
  mismatch is rejected, printing both hashes).

Everything else in the pack (README files, evidence captures, schemas) is
outside the pack per CF-02 section 2 and is neither scanned nor required to
be listed; only ``fixtures[]`` entries are read. A directory named ``.git``
is skipped, and a symbolic link is never followed: a pack that contains one
is invalid under the pack rules, and this tool reads files only, never
outside the pack and never executes anything.

The registry document itself is checked against
``schemas/registry-v1.schema.json`` before it is used, and each path it
names must be a plain pack-relative path, so a registry cannot make the
checker read outside the pack. This command validates the supplied registry
schema and every fixture and payload entry against the pack. Canonical
generation and the pack digest are handled by ``tools/registry/generate.py``;
``tools/registry/check_all.py`` generates twice into isolated temporary
locations and calls this validator.

Usage:
    python3 tools/validate/validate_registry.py [PACK ...] [--registry PATH]

Without PACK arguments every ``protocol-*`` directory in the repository is
checked. Exit codes:

    0   every checked pack matches its generated or supplied registry
    1   cross-validation problems: a fixture on disk is not listed, a listed
        fixture or payload is missing on disk, or a sha256 differs
    2   unusable input: a pack path that is not a directory, a registry that
        cannot be read or is not a usable registry document, or a
        command-line error

Requires Python 3.11+ and nothing outside the standard library.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.common.json_strict import JSONInputError, load_json
from tools.registry import generate as registry_generator

SCHEMA_PATH = REPO_ROOT / "schemas" / "registry-v1.schema.json"
REGISTRY_NAME = "registry-v1.json"


class RegistryInputError(Exception):
    """The registry, or another input, cannot be checked. Never repaired."""


def _load_schema_validator():
    """Import tools/validate/jsonschema_lite.py without needing a package."""
    name = "canary_jsonschema_lite_validate_registry"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = REPO_ROOT / "tools" / "validate" / "jsonschema_lite.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _utf8_key(text: str) -> bytes:
    return text.encode("utf-8")


# ---------------------------------------------------------------- inputs


def load_registry(path: Path) -> dict:
    """Read and check one registry file, or raise RegistryInputError."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise RegistryInputError(f"{path}: no such file") from None
    except IsADirectoryError:
        raise RegistryInputError(f"{path}: is a directory, not a registry file") from None
    except OSError as error:
        raise RegistryInputError(f"{path}: could not be read: {error}") from None

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RegistryInputError(f"{path}: is not valid UTF-8: {error}") from None

    try:
        registry = load_json(text, str(path))
    except JSONInputError as error:
        raise RegistryInputError(str(error)) from None

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    problems = _load_schema_validator().validate(registry, schema)
    # The schema's fixtures minItems floor rejects an empty array, but an
    # empty baseline packs can have a schema-valid generated registry;
    # tools/registry/generate.py filters the same message for --allow-empty.
    problems = [p for p in problems if "fewer than 1" not in p]
    if problems:
        raise RegistryInputError(
            f"{path}: is not a usable registry (checked against {SCHEMA_PATH.name}):\n"
            "  - " + "\n  - ".join(problems)
        )
    return registry


def require_pack_relative(value: str, where: str) -> str:
    """The pack path rules that matter for reading (CF-02 section 2)."""
    if value == "" or value.startswith("/") or "\\" in value or "\x00" in value:
        raise RegistryInputError(f"{where}: {value!r} is not a plain relative path")
    if re.match(r"^[A-Za-z]:", value):
        raise RegistryInputError(f"{where}: {value!r} has a drive prefix")
    for segment in value.split("/"):
        if segment in ("", ".", ".."):
            raise RegistryInputError(
                f"{where}: {value!r} contains an empty, '.' or '..' segment"
            )
    return value


def scan_fixture_paths(pack: Path) -> list[str]:
    """Pack-relative paths of every regular ``*.toml`` file, sorted.

    Sorted by UTF-8 bytes, as CF-02 section 4 orders paths. A directory named
    ``.git`` is skipped (CF-02 section 2) and a symbolic link is never
    followed: a pack that contains one is invalid under the pack rules, and
    this tool never reads outside the pack.
    """
    found: list[str] = []
    stack: list[tuple[Path, str]] = [(pack, "")]
    while stack:
        directory, prefix = stack.pop()
        with os.scandir(directory) as iterator:
            entries = list(iterator)
        for entry in entries:
            if entry.name == ".git" or entry.is_symlink():
                continue
            rel = f"{prefix}{entry.name}"
            if entry.is_dir(follow_symlinks=False):
                stack.append((Path(entry.path), rel + "/"))
            elif entry.is_file(follow_symlinks=False) and rel.endswith(".toml"):
                found.append(rel)
    return sorted(found, key=_utf8_key)


def sha256_or_reason(path: Path) -> tuple[str | None, str]:
    """``(sha256, "")`` for a regular file, else ``(None, why)``."""
    if path.is_symlink():
        return None, "is a symbolic link, not a regular file"
    if not path.exists():
        return None, "is missing from the pack"
    if not path.is_file():
        return None, "is not a regular file"
    try:
        data = path.read_bytes()
    except OSError as error:
        raise RegistryInputError(f"{path}: could not be read: {error}") from None
    return hashlib.sha256(data).hexdigest(), ""


def display_path(path: Path) -> str:
    """Repo-relative POSIX path when the path is inside the repository."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix() if hasattr(path, "as_posix") else str(path).replace("\\", "/")


# ---------------------------------------------------------------- checking


def check_pack(
    pack: Path,
    display: str,
    registry_path: Path | None = None,
) -> tuple[list[str], int, int]:
    """``(problems, fixtures on disk, payload hashes verified)`` for one pack.

    Problems are deterministic: a missing registry first, then unlisted
    fixtures sorted by path, then one line per registry entry in registry
    order. Raises RegistryInputError when the registry itself is unusable.
    """
    registry_display = f"{display}/{REGISTRY_NAME}"
    disk = scan_fixture_paths(pack)
    problems: list[str] = []
    payload_count = 0

    entries: list[dict] = []
    if registry_path is not None and registry_path.exists():
        entries = load_registry(registry_path)["fixtures"]
    elif disk:
        problems.append(
            f"{registry_display}: does not exist, so {len(disk)} fixture(s) on "
            "disk are not listed anywhere"
        )

    listed: set[str] = set()
    for entry in entries:
        rel = entry["path"]
        require_pack_relative(rel, registry_display)
        listed.add(rel)
        digest, reason = sha256_or_reason(pack / rel)
        if digest is None:
            problems.append(
                f"{display}/{rel}: listed in {registry_display} but {reason}"
            )
        elif digest != entry["sha256"]:
            problems.append(
                f"{display}/{rel}: sha256 mismatch: registry {entry['sha256']}, "
                f"file {digest}"
            )
        for payload in entry["payloads"]:
            payload_count += 1
            prel = payload["path"]
            require_pack_relative(prel, registry_display)
            pdigest, preason = sha256_or_reason(pack / prel)
            if pdigest is None:
                problems.append(
                    f"{display}/{prel}: payload listed under {entry['id']!r} in "
                    f"{registry_display} but {preason}"
                )
            elif pdigest != payload["sha256"]:
                problems.append(
                    f"{display}/{prel}: sha256 mismatch (payload of "
                    f"{entry['id']!r}): registry {payload['sha256']}, "
                    f"file {pdigest}"
                )

    for rel in disk:  # already sorted by UTF-8 bytes
        if rel not in listed:
            problems.append(
                f"{display}/{rel}: fixture on disk is not listed in "
                f"{registry_display}"
            )
    return problems, len(disk), payload_count


# ---------------------------------------------------------------- cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_registry.py",
        description=(
            "Cross-validate a protocol pack's fixtures against its canonical "
            "generated registry: every *.toml on disk must be listed, every "
            "listed fixture and payload must exist, and every sha256 must "
            "match. Reads files only; never executes anything."
        ),
        epilog=(
            "Without PACK arguments every protocol-* directory in the "
            "repository is checked. Without --registry, canonical output is "
            "generated in a temporary directory. --registry may be used with "
            "exactly one PACK. Exit codes: 0 every pack matches its "
            "generated or supplied registry, 1 cross-validation problems (an unlisted fixture, a "
            "listed file missing on disk, a sha256 mismatch), 2 unusable "
            "input (a pack path that is not a directory, a registry that "
            "cannot be read or is not a usable registry document, or a "
            "command-line error)."
        ),
    )
    parser.add_argument(
        "packs",
        nargs="*",
        type=Path,
        metavar="PACK",
        help="pack directory to check (default: every protocol-* directory)",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        metavar="PATH",
        help="validate this external registry (only with one PACK)",
    )
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    if args.packs:
        packs = list(args.packs)
    else:
        packs = sorted(
            path for path in REPO_ROOT.glob("protocol-*") if path.is_dir()
        )
    if not packs:
        if args.registry is not None:
            print("error: --registry requires one PACK", file=sys.stderr)
            return 2
        print("OK: no protocol-* pack directories found")
        return 0
    if args.registry is not None and len(packs) != 1:
        print("error: --registry can only be used with one PACK", file=sys.stderr)
        return 2

    total_problems = 0
    with tempfile.TemporaryDirectory(prefix="canary-registry-check-") as temp:
        for index, pack in enumerate(packs):
            if not pack.exists():
                print(f"error: {pack}: no such directory", file=sys.stderr)
                return 2
            if not pack.is_dir():
                print(f"error: {pack}: not a directory", file=sys.stderr)
                return 2
            display = display_path(pack)
            registry_path = args.registry
            disk = scan_fixture_paths(pack)
            if registry_path is None and disk:
                try:
                    generated = registry_generator.generate(pack)
                except registry_generator.PackError as error:
                    print(
                        f"error: {display}: could not generate registry: {error}",
                        file=sys.stderr,
                    )
                    return 1
                registry_path = Path(temp) / f"{index}-{pack.name}-{REGISTRY_NAME}"
                try:
                    registry_path.write_bytes(generated.encode("utf-8"))
                except OSError as error:
                    print(f"error: could not write temporary registry: {error}", file=sys.stderr)
                    return 2
            try:
                problems, fixtures, payloads = check_pack(pack, display, registry_path)
            except RegistryInputError as error:
                print(f"error: {error}", file=sys.stderr)
                return 2
            if problems:
                total_problems += len(problems)
                for line in problems:
                    print(f"error: {line}", file=sys.stderr)
            elif fixtures == 0 and registry_path is None:
                print(f"OK: {display}: no fixtures and no generated registry to check")
            else:
                print(
                    f"OK: {display}: {fixtures} fixture(s) and {payloads} "
                    "payload hash(es) match the generated registry"
                )

    if total_problems:
        print(f"FAILED: {total_problems} problem(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
