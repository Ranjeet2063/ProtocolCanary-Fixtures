#!/usr/bin/env python3
r"""Build the deterministic release archive for one protocol pack (CF-06).

Packs the fixtures of a pack directory (for example ``protocol-28/``) and its
generated ``registry.json`` into a ``.tar.gz`` that is byte-for-byte
reproducible: building the same pack twice gives the same SHA-256.

The rules implemented here are the ones in
``Protocol-Canary/docs/contracts/cf-06-fixture-releases.md`` section 2, which
is authoritative:

* content is exactly the CF-02 pack membership (every ``*.toml`` file and every
  file a fixture names in ``input_file`` or ``expected_file``) plus
  ``registry.json`` at the archive root. No README, no ``.git``, no links;
* entries are sorted by path in UTF-8 byte order, directories before the files
  inside them;
* owner uid and gid are 0, owner and group names are empty, mtime is 0, files
  are mode 0644 and directories 0755, with no extended attributes;
* the gzip stream carries no file name and a zero timestamp (``gzip -n``);
* the D-06 limits hold for the archive as a whole: at most 2,000 entries,
  16 MiB uncompressed, 1 MiB per file and depth 8.

An invalid pack is never repaired or skipped: the tool prints what is wrong and
exits non-zero without writing an archive.

Usage:
    python3 tools/pack/pack.py PACK --version 1.0.0 [--output-dir DIR]

Requires Python 3.11+ and nothing outside the standard library.
"""
from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import importlib.util
import io
import json
import re
import sys
import tarfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative: str):
    path = REPO_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


# Atomic writes (F-081): a release artifact is published under its final name
# only once it is complete.
atomic_write = _load("canary_atomic_write", "tools/common/atomic_write.py")
write_bytes_atomic = atomic_write.write_bytes_atomic
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.common import pack_limits

ARCHIVE_PREFIX = "protocolcanary-fixtures"
REGISTRY_NAME = "registry.json"
FILE_MODE = 0o644
DIRECTORY_MODE = 0o755

MAX_ENTRIES = pack_limits.MAX_FILES
MAX_FILES = pack_limits.MAX_FILES
MAX_TOTAL_BYTES = pack_limits.MAX_TOTAL_BYTES
MAX_FILE_BYTES = pack_limits.MAX_FILE_BYTES
MAX_DEPTH = pack_limits.MAX_DEPTH

_VERSION_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def _load_generator():
    path = REPO_ROOT / "tools" / "registry" / "generate.py"
    spec = importlib.util.spec_from_file_location("registry_generate", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules.setdefault("registry_generate", module)
    spec.loader.exec_module(module)
    return module


def _load_validator():
    path = REPO_ROOT / "tools" / "validate" / "validate.py"
    spec = importlib.util.spec_from_file_location("pack_validate", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules.setdefault("pack_validate", module)
    spec.loader.exec_module(module)
    return module


generate = _load_generator()
validate = _load_validator()


class PackError(Exception):
    """The pack cannot be archived. The message says what to fix."""


@dataclass(frozen=True)
class ArchiveInfo:
    """Facts about a written archive, as recorded in the release manifest."""

    path: Path
    sha256: str
    size: int
    entries: int
    uncompressed_bytes: int
    pack_digest: str
    protocol: int


def archive_name(version: str) -> str:
    return f"{ARCHIVE_PREFIX}-{version}.tar.gz"


def check_version(version: str) -> None:
    if not _VERSION_RE.fullmatch(version):
        raise PackError(
            f"version {version!r} is not MAJOR.MINOR.PATCH (for example 1.0.0)"
        )


def collect_members(pack: Path) -> tuple[dict[str, bytes], str, int]:
    """The files of the archive, ``{path: bytes}``, plus digest and protocol.

    Membership is the CF-02 set; ``registry.json`` is generated from it. Any
    problem the registry generator finds (a link, an unsafe path, a missing
    payload, two protocols) stops the build.
    """
    try:
        scanned = generate.scan_pack(pack)
        registry = generate.build_registry(scanned)
        generate.check_against_schema(registry)
    except generate.PackError as error:
        raise PackError(str(error)) from None
    except OSError as error:
        raise PackError(f"could not read the pack: {error}") from None

    members: dict[str, bytes] = {}
    for fixture in registry["fixtures"]:
        members[fixture["path"]] = scanned[fixture["path"]]
        for payload in fixture["payloads"]:
            members[payload["path"]] = scanned[payload["path"]]
    members[REGISTRY_NAME] = generate.render_registry(registry).encode("utf-8")
    return members, registry["packDigest"], registry["protocol"]


def directories_of(paths) -> list[str]:
    """Every parent directory of ``paths``, sorted in UTF-8 byte order."""
    found: set[str] = set()
    for path in paths:
        parts = path.split("/")[:-1]
        for end in range(1, len(parts) + 1):
            found.add("/".join(parts[:end]))
    return sorted(found, key=lambda p: p.encode("utf-8"))


def check_limits(members: dict[str, bytes], directories: list[str]) -> None:
    """The D-06 limits, applied to the archive as it will be written."""
    entries = len(members) + len(directories)
    if entries > MAX_ENTRIES:
        raise PackError(
            f"the archive would have {entries} entries, over the limit of {MAX_ENTRIES}"
        )
    total = 0
    for path, data in members.items():
        if len(data) > MAX_FILE_BYTES:
            raise PackError(
                f"{path} is {len(data)} bytes, over the {MAX_FILE_BYTES}-byte limit for one file"
            )
        if len(path.split("/")) > MAX_DEPTH:
            raise PackError(f"{path} is deeper than {MAX_DEPTH} path segments")
        total += len(data)
    if total > MAX_TOTAL_BYTES:
        raise PackError(
            f"the archive would hold {total} bytes uncompressed, over the limit of {MAX_TOTAL_BYTES}"
        )


def check_verified_evidence(pack: Path) -> None:
    """Require current CF-04 evidence for every fixture in ``pack``.

    Protocol 29 releases require fresh evidence on both Testnet and Futurenet.
    Protocol 30 releases require fresh Testnet-only RPC identity evidence.
    Stored records under ``history/`` cannot satisfy either release gate.
    """
    try:
        scanned = generate.scan_pack(pack)
        if not any(path.endswith(".toml") for path in scanned):
            raise PackError("--verified refuses a pack with zero fixtures")
        registry = generate.build_registry(scanned)
        generate.check_against_schema(registry)
    except generate.PackError as error:
        raise PackError(str(error)) from None
    except OSError as error:
        raise PackError(f"could not read the pack: {error}") from None

    fixture_hashes = {
        fixture["id"]: hashlib.sha256(scanned[fixture["path"]]).hexdigest()
        for fixture in registry["fixtures"]
    }
    if not fixture_hashes:
        raise PackError("--verified refuses a pack with zero fixtures")

    evidence_dir = pack / "evidence"
    if not evidence_dir.is_dir():
        raise PackError("--verified requires an evidence/ directory")

    evidence_files = [
        path
        for path in validate.find_evidence_files(evidence_dir)
        if "history" not in path.relative_to(evidence_dir).parts
        and "records" in path.relative_to(evidence_dir).parts
    ]
    verified: set[str] = set()
    records: list[tuple[Path, dict]] = []
    now = datetime.datetime.now(datetime.UTC)
    for path in evidence_files:
        report = validate.Report()
        record = validate.validate_evidence_file(path, report, now=now)
        if record is None:
            raise PackError(f"invalid verification evidence {path}: {'; '.join(report.errors)}")
        validate.check_evidence_against_fixtures(path, record, fixture_hashes, report)
        if report.errors:
            raise PackError(f"invalid verification evidence {path}: {'; '.join(report.errors)}")
        if record["outcome"] != "matched":
            raise PackError(f"verification evidence {path} does not have a passing outcome")
        verified.add(record["fixtureId"])
        records.append((path, record))

    missing = sorted(set(fixture_hashes) - verified)
    if missing:
        raise PackError(
            "--verified requires passing evidence records for every fixture; missing "
            + ", ".join(missing)
        )

    if registry["protocol"] == 29:
        _check_protocol29_live_evidence(pack, registry, fixture_hashes, records, now)
    elif registry["protocol"] == 30:
        _check_protocol30_live_evidence(pack, registry, fixture_hashes, records, now)


_PROTOCOL29_NETWORKS = {
    "testnet": {
        "host": "soroban-testnet.stellar.org",
        "passphrase": "Test SDF Network ; September 2015",
    },
    "futurenet": {
        "host": "rpc-futurenet.stellar.org",
        "passphrase": "Test SDF Future Network ; October 2022",
    },
}
_FIXTURE_RPC_METHODS = {
    "get-version-info": "getVersionInfo",
    "get-network": "getNetwork",
    "get-latest-ledger": "getLatestLedger",
}
_PROTOCOL29_LIVE_FRESHNESS = datetime.timedelta(days=30)


def _read_json(path: Path, description: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackError(f"{description} {path} is not readable JSON: {error}") from None
    if not isinstance(value, dict):
        raise PackError(f"{description} {path} must contain a JSON object")
    return value


def _check_protocol29_live_evidence(
    pack: Path,
    registry: dict,
    fixture_hashes: dict[str, str],
    records: list[tuple[Path, dict]],
    now: datetime.datetime,
) -> None:
    """Require one authentic, fresh Testnet and Futurenet record per fixture."""
    expected: dict[tuple[str, str], tuple[Path, dict]] = {}
    fixture_methods: dict[str, str] = {}
    for fixture in registry["fixtures"]:
        fixture_path = pack / fixture["path"]
        try:
            parsed = tomllib.loads(fixture_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            raise PackError(f"could not read Protocol 29 fixture {fixture_path}: {error}") from None
        method = parsed.get("method")
        rpc_method = _FIXTURE_RPC_METHODS.get(method)
        if rpc_method is None:
            raise PackError(
                f"--verified has no live RPC method mapping for Protocol 29 fixture "
                f"{fixture['id']!r} method {method!r}"
            )
        fixture_methods[fixture["id"]] = rpc_method

    for path, record in records:
        fixture_id = record["fixtureId"]
        network = record.get("network", {}).get("name") if isinstance(record.get("network"), dict) else None
        if record.get("method") != "live-read-only":
            raise PackError(
                f"Protocol 29 verified evidence must be live-read-only: {path}"
            )
        if network not in _PROTOCOL29_NETWORKS:
            raise PackError(
                f"Protocol 29 verified evidence must identify testnet or futurenet: {path}"
            )
        key = (fixture_id, network)
        if key in expected:
            raise PackError(
                f"duplicate Protocol 29 live record for fixture {fixture_id!r} on {network}"
            )
        expected[key] = (path, record)

    missing = [
        f"{fixture_id} on {network}"
        for fixture_id in fixture_hashes
        for network in _PROTOCOL29_NETWORKS
        if (fixture_id, network) not in expected
    ]
    if missing:
        raise PackError(
            "Protocol 29 --verified requires live-read-only records for every fixture "
            "on Testnet and Futurenet; missing " + ", ".join(missing)
        )

    pack_parent = pack.resolve().parent
    for (fixture_id, network), (record_path, record) in expected.items():
        required_network = _PROTOCOL29_NETWORKS[network]
        if record["outcome"] != "matched":
            raise PackError(f"Protocol 29 live evidence is not matched: {record_path}")
        if record.get("fixtureSha256") != fixture_hashes[fixture_id]:
            raise PackError(f"Protocol 29 live evidence has the wrong fixture digest: {record_path}")
        if record.get("endpointHost") != required_network["host"]:
            raise PackError(f"Protocol 29 live evidence has the wrong endpoint host: {record_path}")
        network_record = record.get("network", {})
        if (
            network_record.get("passphrase") != required_network["passphrase"]
            or network_record.get("observedProtocol") != 29
        ):
            raise PackError(f"Protocol 29 live evidence has the wrong network identity: {record_path}")
        if "live" not in record_path.relative_to(pack / "evidence").parts:
            raise PackError(f"Protocol 29 live record is outside evidence/live/: {record_path}")
        relative_record_path = record_path.relative_to(pack / "evidence").parts
        if relative_record_path[:3] != ("live", network, "records"):
            raise PackError(
                f"Protocol 29 live record is not stored under evidence/live/{network}/records/: "
                f"{record_path}"
            )
        age = now - validate._parse_instant(record["checkedAt"])
        if age < -validate.CLOCK_SKEW_TOLERANCE or age > _PROTOCOL29_LIVE_FRESHNESS:
            raise PackError(
                f"Protocol 29 live evidence is outside the 30-day freshness window: {record_path}"
            )

        reference = record.get("evidenceRef")
        expected_prefix = f"{pack.name}/evidence/live/{network}/captures/"
        if not isinstance(reference, str) or not reference.startswith(expected_prefix):
            raise PackError(f"Protocol 29 live evidenceRef is not a network capture path: {record_path}")
        capture_path = pack_parent / reference
        if not capture_path.is_file() or capture_path.resolve().parent != (
            pack / "evidence" / "live" / network / "captures"
        ).resolve():
            raise PackError(f"Protocol 29 evidenceRef does not resolve to a capture: {record_path}")
        capture = _read_json(capture_path, "Protocol 29 capture")
        if capture.get("capturedAt") != record["checkedAt"]:
            raise PackError(f"Protocol 29 capture timestamp does not match its record: {record_path}")
        if capture.get("endpointHost") != required_network["host"]:
            raise PackError(f"Protocol 29 capture host does not match its record: {capture_path}")
        request = capture.get("request")
        response = capture.get("response")
        result = response.get("result") if isinstance(response, dict) else None
        if not isinstance(request, dict) or not isinstance(response, dict) or not isinstance(result, dict):
            raise PackError(f"Protocol 29 capture lacks a JSON-RPC request or result: {capture_path}")
        if (
            request.get("jsonrpc") != "2.0"
            or response.get("jsonrpc") != "2.0"
            or request.get("id") != response.get("id")
            or request.get("method") != fixture_methods[fixture_id]
            or result.get("protocolVersion") != 29
        ):
            raise PackError(f"Protocol 29 capture does not match its fixture assertion: {capture_path}")

        network_capture_path = capture_path.with_name("get-network.json")
        network_capture = _read_json(network_capture_path, "Protocol 29 network identity capture")
        net_request = network_capture.get("request")
        net_response = network_capture.get("response")
        net_result = net_response.get("result") if isinstance(net_response, dict) else None
        if (
            network_capture.get("endpointHost") != required_network["host"]
            or not isinstance(net_request, dict)
            or net_request.get("jsonrpc") != "2.0"
            or net_request.get("method") != "getNetwork"
            or not isinstance(net_response, dict)
            or net_response.get("jsonrpc") != "2.0"
            or net_request.get("id") != net_response.get("id")
            or not isinstance(net_result, dict)
            or net_result.get("passphrase") != required_network["passphrase"]
            or net_result.get("protocolVersion") != 29
        ):
            raise PackError(
                f"Protocol 29 network identity capture does not match {network}: {network_capture_path}"
            )


_PROTOCOL30_TESTNET = {
    "host": "soroban-testnet.stellar.org",
    "passphrase": "Test SDF Network ; September 2015",
}
_PROTOCOL30_LIVE_FRESHNESS = datetime.timedelta(days=30)
_PROTOCOL30_CAPTURE_WINDOW = datetime.timedelta(minutes=5)


def _check_protocol30_live_evidence(
    pack: Path,
    registry: dict,
    fixture_hashes: dict[str, str],
    records: list[tuple[Path, dict]],
    now: datetime.datetime,
) -> None:
    """Require fresh, coherent, Testnet-only RPC evidence for every P30 fixture.

    This validates stored live-capture records; it is not cryptographic proof
    of an RPC response or of compatibility beyond declared assertions.
    """
    if len(records) != len(fixture_hashes):
        raise PackError("Protocol 30 release requires exactly one Testnet live record per fixture")

    expected_ids = set(fixture_hashes)
    observed_ids: set[str] = set()
    for record_path, record in records:
        fixture_id = record["fixtureId"]
        if fixture_id not in expected_ids or fixture_id in observed_ids:
            raise PackError(f"Protocol 30 unexpected or duplicate live record: {record_path}")
        observed_ids.add(fixture_id)
        if record_path.is_symlink() or record_path.relative_to(pack / "evidence").parts[:3] != (
            "live", "testnet", "records"
        ):
            raise PackError(f"Protocol 30 record must be under Testnet live records: {record_path}")
        if record["method"] != "live-read-only":
            raise PackError(f"Protocol 30 release requires live-read-only evidence: {record_path}")
        if record["outcome"] != "matched" or record["fixtureSha256"] != fixture_hashes[fixture_id]:
            raise PackError(f"Protocol 30 record outcome or fixture digest mismatch: {record_path}")
        if record.get("verifier", {}).get("name") != "protocolcanary-fixtures-capture-live":
            raise PackError(f"Protocol 30 record has an unexpected verifier: {record_path}")
        network = record.get("network", {})
        if (
            network.get("name") != "testnet"
            or network.get("passphrase") != _PROTOCOL30_TESTNET["passphrase"]
            or network.get("observedProtocol") != 30
            or record.get("endpointHost") != _PROTOCOL30_TESTNET["host"]
        ):
            raise PackError(f"Protocol 30 record has the wrong Testnet identity: {record_path}")
        checked_at = validate._parse_instant(record["checkedAt"])
        if not (-validate.CLOCK_SKEW_TOLERANCE <= now - checked_at <= _PROTOCOL30_LIVE_FRESHNESS):
            raise PackError(f"Protocol 30 live evidence is outside the 30-day freshness window: {record_path}")

        fixture = next(f for f in registry["fixtures"] if f["id"] == fixture_id)
        fixture_path = pack / fixture["path"]
        try:
            body = tomllib.loads(fixture_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise PackError(f"Protocol 30 fixture cannot be parsed: {fixture_path}: {exc}") from None
        # First release deliberately supports just the independently tested
        # getVersionInfo identity assertion. Extend only with specific evidence.
        if (
            fixture["surface"] != "rpc"
            or body.get("method") != "get-version-info"
            or body.get("assert") != [
                {"kind": "field-equals", "field": "protocolVersion", "value": 30}
            ]
        ):
            raise PackError(f"Protocol 30 release gate does not support this fixture: {fixture_path}")

        expected_ref = "protocol-30/evidence/live/testnet/captures/get-version-info.json"
        if record.get("evidenceRef") != expected_ref:
            raise PackError(f"Protocol 30 record must link the exact raw capture: {record_path}")
        capture_dir = pack / "evidence" / "live" / "testnet" / "captures"
        version_path = capture_dir / "get-version-info.json"
        network_path = capture_dir / "get-network.json"
        for item in (version_path, network_path):
            if item.is_symlink() or not item.is_file():
                raise PackError(f"Protocol 30 required capture is missing or a symlink: {item}")
        version_capture = _read_json(version_path, "Protocol 30 version capture")
        network_capture = _read_json(network_path, "Protocol 30 network capture")

        def check_rpc_capture(capture: dict, method: str, filename: Path) -> dict:
            request = capture.get("request")
            response = capture.get("response")
            result = response.get("result") if isinstance(response, dict) else None
            if (
                capture.get("endpointHost") != _PROTOCOL30_TESTNET["host"]
                or not isinstance(request, dict)
                or not isinstance(response, dict)
                or not isinstance(result, dict)
                or request.get("jsonrpc") != "2.0"
                or response.get("jsonrpc") != "2.0"
                or request.get("id") != response.get("id")
                or request.get("method") != method
                or "error" in response
                or result.get("protocolVersion") != 30
            ):
                raise PackError(f"Protocol 30 capture has incorrect RPC identity: {filename}")
            return result

        check_rpc_capture(version_capture, "getVersionInfo", version_path)
        network_result = check_rpc_capture(network_capture, "getNetwork", network_path)
        if network_result.get("passphrase") != _PROTOCOL30_TESTNET["passphrase"]:
            raise PackError(f"Protocol 30 getNetwork passphrase mismatch: {network_path}")
        if version_capture.get("capturedAt") != record["checkedAt"]:
            raise PackError(f"Protocol 30 raw version capture timestamp mismatch: {version_path}")
        network_timestamp = network_capture.get("capturedAt")
        if not isinstance(network_timestamp, str):
            raise PackError(f"Protocol 30 network capture has no UTC timestamp: {network_path}")
        if not network_timestamp.endswith("Z"):
            raise PackError(f"Protocol 30 network timestamp must be UTC: {network_path}")
        try:
            network_time = validate._parse_instant(network_timestamp)
        except (TypeError, ValueError) as exc:
            raise PackError(f"Protocol 30 network timestamp is invalid: {network_path}: {exc}") from None
        if (
            abs(network_time - checked_at) > _PROTOCOL30_CAPTURE_WINDOW
            or now - network_time > _PROTOCOL30_LIVE_FRESHNESS
            or network_time - now > validate.CLOCK_SKEW_TOLERANCE
        ):
            raise PackError(f"Protocol 30 Testnet identity and version captures are not contemporaneous: {network_path}")

    missing = expected_ids - observed_ids
    if missing:
        raise PackError(f"Protocol 30 missing live evidence for {', '.join(sorted(missing))}")


def _tar_info(name: str, *, directory: bool, size: int = 0) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.mode = DIRECTORY_MODE if directory else FILE_MODE
    info.size = 0 if directory else size
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def render_archive(members: dict[str, bytes]) -> bytes:
    """The archive bytes for ``members``. Deterministic for equal input."""
    directories = directories_of(members)
    check_limits(members, directories)

    names = sorted(set(members) | set(directories), key=lambda p: p.encode("utf-8"))
    raw = io.BytesIO()
    # `filename=""` and `mtime=0`: the gzip header carries neither a name nor
    # a time, so the compressed bytes do not depend on where or when it ran.
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as stream:
        with tarfile.open(
            fileobj=stream, mode="w", format=tarfile.PAX_FORMAT, encoding="utf-8"
        ) as archive:
            for name in names:
                if name in members:
                    data = members[name]
                    archive.addfile(
                        _tar_info(name, directory=False, size=len(data)), io.BytesIO(data)
                    )
                else:
                    archive.addfile(_tar_info(name, directory=True))
    return raw.getvalue()


def build_archive(pack: Path, output_dir: Path, version: str) -> ArchiveInfo:
    """Write ``protocolcanary-fixtures-<version>.tar.gz`` into ``output_dir``."""
    check_version(version)
    members, digest, protocol = collect_members(pack)
    data = render_archive(members)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / archive_name(version)
    write_bytes_atomic(path, data)
    return ArchiveInfo(
        path=path,
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
        entries=len(members) + len(directories_of(members)),
        uncompressed_bytes=sum(len(b) for b in members.values()),
        pack_digest=digest,
        protocol=protocol,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pack.py",
        description=(
            "Build the deterministic fixture-pack archive (CF-06). Reads the pack, "
            "never executes anything, and writes nothing unless the whole pack is valid."
        ),
    )
    parser.add_argument("pack", type=Path, help="pack directory, for example protocol-28")
    parser.add_argument(
        "--version",
        required=True,
        help="release version, MAJOR.MINOR.PATCH; names the archive",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dist"),
        metavar="DIR",
        help="directory for the archive (default: dist)",
    )
    parser.add_argument(
        "--verified",
        action="store_true",
        help="require valid, passing CF-04 evidence for every fixture",
    )
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.verified:
            check_verified_evidence(args.pack)
        info = build_archive(args.pack, args.output_dir, args.version)
    except PackError as error:
        print(f"error: {error}", file=sys.stderr)
        print("FAILED: no archive written", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"error: could not write the archive: {error}", file=sys.stderr)
        return 1
    print(f"OK: wrote {info.path}")
    print(f"sha256   {info.sha256}")
    print(f"bytes    {info.size}")
    print(f"entries  {info.entries}")
    print(f"digest   {info.pack_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
