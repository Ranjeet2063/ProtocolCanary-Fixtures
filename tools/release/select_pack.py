#!/usr/bin/env python3
"""Select a fixture pack from an explicit versioned tag or dispatch choice.

Versioned tags encode both pack and version, for example
``fixtures-p29-v1.2.3``. Legacy or unscoped tags are rejected rather than
silently selecting a pack.
"""
from __future__ import annotations

import argparse
import re
import sys

_VERSION = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
_TAG = re.compile(rf"fixtures-p(28|29)-v({_VERSION})")


class SelectionError(ValueError):
    """An event does not unambiguously select a supported pack and version."""


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
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    try:
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
