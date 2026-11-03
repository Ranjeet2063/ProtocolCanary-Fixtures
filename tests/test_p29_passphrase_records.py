"""Preserve the historical Protocol 29 structural records by network."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = REPO_ROOT / "protocol-29" / "evidence" / "history" / "verification"
CURRENT_FIXTURE = (
    REPO_ROOT / "protocol-29" / "rpc" / "p29-rpc-version-info-protocol-29.toml"
)


class Protocol29HistoricalRecordTests(unittest.TestCase):
    def test_structural_records_remain_historical_and_network_specific(self) -> None:
        testnet = HISTORICAL / "testnet" / "p29-rpc-network-mismatch.json"
        futurenet = HISTORICAL / "futurenet" / "p29-rpc-network-mismatch.json"
        testnet_record = json.loads(testnet.read_text(encoding="utf-8"))
        futurenet_record = json.loads(futurenet.read_text(encoding="utf-8"))

        self.assertEqual(
            testnet_record["network"]["passphrase"],
            "Test SDF Network ; September 2015",
        )
        self.assertEqual(
            futurenet_record["network"]["passphrase"],
            "Test SDF Future Network ; October 2022",
        )
        self.assertEqual(testnet_record["method"], "structural")
        self.assertEqual(futurenet_record["method"], "structural")
        self.assertNotIn("evidenceRef", testnet_record)
        self.assertNotIn("evidenceRef", futurenet_record)
        self.assertEqual(testnet_record["fixtureId"], "p29-rpc-network-mismatch")
        self.assertEqual(futurenet_record["fixtureId"], "p29-rpc-network-mismatch")
        self.assertNotEqual(
            testnet_record["fixtureSha256"],
            __import__("hashlib").sha256(CURRENT_FIXTURE.read_bytes()).hexdigest(),
        )
        self.assertNotEqual(
            futurenet_record["fixtureSha256"],
            __import__("hashlib").sha256(CURRENT_FIXTURE.read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
