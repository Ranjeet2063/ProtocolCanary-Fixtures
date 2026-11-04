"""Offline local-mock checks for the distinct Protocol 30 identity fixture."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import mock_rpc  # noqa: E402

from tools.evidence import capture_live  # noqa: E402

PACK30 = ROOT / "protocol-30"
PACK29 = ROOT / "protocol-29"
FIXTURE = PACK30 / "rpc" / "p30-rpc-version-info-protocol-30.toml"


class Protocol30TestnetFixtureTests(unittest.TestCase):
    def test_strict_protocol_30_identity_assertion(self) -> None:
        data = tomllib.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(data["id"], "p30-rpc-version-info-protocol-30")
        self.assertEqual(data["protocol"], 30)
        self.assertEqual(data["surface"], "rpc")
        self.assertEqual(data["method"], "get-version-info")
        self.assertEqual(data["assert"], [
            {"kind": "field-equals", "field": "protocolVersion", "value": 30}
        ])

    def test_registry_pins_fixture_bytes(self) -> None:
        registry = json.loads((PACK30 / "registry-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["protocol"], 30)
        self.assertEqual(len(registry["fixtures"]), 1)
        entry = registry["fixtures"][0]
        self.assertEqual(entry["path"], "rpc/p30-rpc-version-info-protocol-30.toml")
        self.assertEqual(entry["sha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())

    def test_p30_matches_p30_mock(self) -> None:
        # A test mock is NEVER live evidence.
        with tempfile.TemporaryDirectory() as tmp, mock_rpc.MockRpcServer(protocol=30) as server:
            result = capture_live.run(PACK30, output_dir=Path(tmp), local_endpoint=server.url)
        self.assertEqual(result.failures, [])
        self.assertEqual([outcome for _, outcome, _ in result.outcomes], ["matched"])

    def test_p29_fails_p30_mock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock_rpc.MockRpcServer(protocol=30) as server:
            result = capture_live.run(PACK29, output_dir=Path(tmp), local_endpoint=server.url)
        self.assertEqual([outcome for _, outcome, _ in result.outcomes], ["mismatched"])

    def test_p30_fails_p29_mock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock_rpc.MockRpcServer(protocol=29) as server:
            result = capture_live.run(PACK30, output_dir=Path(tmp), local_endpoint=server.url)
        self.assertEqual([outcome for _, outcome, _ in result.outcomes], ["mismatched"])


if __name__ == "__main__":
    unittest.main()
