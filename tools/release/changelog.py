#!/usr/bin/env python3
"""Render deterministic protocol release notes from immutable changelog fragments."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAG_RE = re.compile(r"^fixtures-p(?P<protocol>[0-9]+)-v(?P<version>.+)$")
VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
FRAGMENT_RE = re.compile(
    r"^changelog\.d/(?:common|protocol-[0-9]+)/[a-z0-9][a-z0-9._-]*\.md$"
)


class ChangelogError(Exception):
    """The release changelog cannot be generated safely."""


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode:
        raise ChangelogError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def version_tuple(version: str) -> tuple[int, int, int]:
    if not VERSION_RE.fullmatch(version):
        raise ChangelogError(f"invalid release version {version!r}; expected MAJOR.MINOR.PATCH")
    return tuple(int(part) for part in version.split("."))


def previous_tag(root: Path, protocol: int, version: str) -> str | None:
    """Latest reachable protocol tag older than the selected release version."""
    selected = version_tuple(version)
    tags = run_git(
        root,
        "tag",
        "--list",
        f"fixtures-p{protocol}-v*",
        "--merged",
        "HEAD",
    )
    candidates: list[tuple[tuple[int, int, int], str]] = []
    for tag in tags.splitlines():
        match = TAG_RE.fullmatch(tag)
        if match is None or int(match.group("protocol")) != protocol:
            continue
        try:
            tag_version = version_tuple(match.group("version"))
        except ChangelogError:
            continue
        if tag_version < selected:
            candidates.append((tag_version, tag))
    return max(candidates)[1] if candidates else None


def fragment_paths(root: Path, protocol: int, version: str) -> list[str]:
    """Paths added since the prior protocol release, in UTF-8 path order."""
    prior = previous_tag(root, protocol, version)
    if prior is None:
        candidates = []
        for directory in (root / "changelog.d" / "common", root / "changelog.d" / f"protocol-{protocol}"):
            if directory.is_dir():
                candidates.extend(
                    path.relative_to(root).as_posix()
                    for path in directory.rglob("*.md")
                )
    else:
        diff = run_git(
            root,
            "diff",
            "--diff-filter=A",
            "--name-only",
            f"{prior}...HEAD",
            "--",
            "changelog.d/common",
            f"changelog.d/protocol-{protocol}",
        )
        candidates = [line for line in diff.splitlines() if line]

    prefix = f"changelog.d/protocol-{protocol}/"
    allowed = ["changelog.d/common/", prefix]
    result = []
    for candidate in candidates:
        if not any(candidate.startswith(item) for item in allowed):
            continue
        if not FRAGMENT_RE.fullmatch(candidate):
            raise ChangelogError(f"invalid changelog fragment path {candidate!r}")
        result.append(candidate)
    return sorted(set(result), key=lambda path: path.encode("utf-8"))


def render_changelog(root: Path, protocol: int, version: str) -> str:
    """Render canonical UTF-8 Markdown from the selected immutable fragments."""
    version_tuple(version)
    fragments = fragment_paths(root, protocol, version)
    lines = [f"# Protocol {protocol} fixture pack {version}", "", "## Changes", ""]
    if not fragments:
        prior = previous_tag(root, protocol, version)
        if prior:
            lines.append(f"No changelog fragments were added since `{prior}`.")
        else:
            lines.append("No changelog fragments are recorded for this pack yet.")
        return "\n".join(lines) + "\n"

    for relative in fragments:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ChangelogError(f"{relative}: fragment must be a regular file, not a symlink")
        try:
            path.resolve().relative_to(root.resolve())
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise ChangelogError(f"{relative}: cannot read fragment safely: {error}") from None
        content = content.strip()
        if not content:
            raise ChangelogError(f"{relative}: fragment is empty")
        lines.extend([f"### {Path(relative).stem}", "", content, ""])
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate deterministic release notes from added changelog fragments."
    )
    parser.add_argument("--protocol", type=int, required=True, help="protocol pack number")
    parser.add_argument("--version", required=True, help="release version MAJOR.MINOR.PATCH")
    parser.add_argument("--output", type=Path, required=True, help="output Markdown path")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=ROOT,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.protocol <= 0:
            raise ChangelogError("protocol must be a positive integer")
        markdown = render_changelog(args.repo_root, args.protocol, args.version)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=args.output.parent, prefix=f".{args.output.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(markdown.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, args.output)
    except (ChangelogError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"OK: wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
