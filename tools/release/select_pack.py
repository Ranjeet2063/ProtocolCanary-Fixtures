#!/usr/bin/env python3
"""Select a fixture pack from an explicit versioned tag or dispatch choice.

Versioned tags encode both pack and version, for example
``fixtures-p29-v1.2.3``. Legacy or unscoped tags are rejected rather than
silently selecting a pack.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_VERSION = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
_TAG = re.compile(rf"fixtures-p(28|29)-v({_VERSION})")


class SelectionError(ValueError):
    """An event does not unambiguously select a supported pack and version."""


def validate_release_ref(
    *,
    event: str,
    tag: str,
    ref: str,
    sha: str,
    main_ref: str = "refs/remotes/origin/main",
    repo: Path | str = ".",
) -> dict[str, str]:
    """Select a tag release and require its exact commit to be in main history."""
    selected = select(event=event, tag=tag)
    expected_ref = f"refs/tags/{tag}"
    if ref != expected_ref:
        raise SelectionError(
            f"event ref {ref!r} does not exactly match release tag {expected_ref!r}"
        )

    if not re.fullmatch(r"[0-9a-f]{40,64}", sha):
        raise SelectionError("event commit must be a full hexadecimal commit ID")

    try:
        tag_commit = subprocess.run(
            ["git", "rev-parse", "--verify", f"{expected_ref}^{{commit}}"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise SelectionError(f"cannot resolve release tag {expected_ref!r}") from error

    if tag_commit != sha:
        raise SelectionError(
            f"release tag resolves to {tag_commit}, not event commit {sha}"
        )

    try:
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", tag_commit, main_ref],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise SelectionError("could not verify release commit ancestry") from error
    if ancestry.returncode != 0:
        raise SelectionError(
            f"release commit {tag_commit} is not in protected main history ({main_ref})"
        )

    selected["tag"] = tag
    selected["commit"] = tag_commit
    return selected


def select(*, event: str, tag: str = "", protocol: str = "", version: str = "") -> dict[str, str]:
    if event in ("push", "release"):
        if protocol or version:
            raise SelectionError("tag events select both protocol and version from the tag")
        match = _TAG.fullmatch(tag)
        if match is None:
            raise SelectionError(
                f"unsupported or ambiguous release tag {tag!r}; expected "
                "fixtures-p28-vMAJOR.MINOR.PATCH or fixtures-p29-vMAJOR.MINOR.PATCH"
            )
        protocol, version = match.groups()
    elif event == "workflow_dispatch":
        if tag:
            raise SelectionError("manual dispatch selects a pack from protocol and version inputs")
        if protocol not in ("28", "29"):
            raise SelectionError("manual dispatch protocol must be 28 or 29")
        if not re.fullmatch(_VERSION, version):
            raise SelectionError("manual dispatch version must be MAJOR.MINOR.PATCH")
    else:
        raise SelectionError(f"unsupported workflow event {event!r}")

    return {
        "pack": f"protocol-{protocol}",
        "protocol": protocol,
        "version": version,
        "verified": "true" if protocol == "29" else "false",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True, choices=("push", "release", "workflow_dispatch"))
    parser.add_argument("--tag", default="")
    parser.add_argument("--protocol", default="")
    parser.add_argument("--version", default="")
    parser.add_argument("--ref", default="")
    parser.add_argument("--sha", default="")
    parser.add_argument("--main-ref", default="refs/remotes/origin/main")
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.event in ("push", "release"):
            if not args.ref or not args.sha:
                raise SelectionError("tag events require release-ref validation with --ref and --sha")
            if args.protocol or args.version:
                raise SelectionError("tag events select both protocol and version from the tag")
            selected = validate_release_ref(
                event=args.event,
                tag=args.tag,
                ref=args.ref,
                sha=args.sha,
                main_ref=args.main_ref,
            )
        else:
            if args.ref or args.sha:
                raise SelectionError("manual dispatch does not accept a release ref or commit")
            selected = select(
                event=args.event,
                tag=args.tag,
                protocol=args.protocol,
                version=args.version,
            )
    except SelectionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for key, value in selected.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
