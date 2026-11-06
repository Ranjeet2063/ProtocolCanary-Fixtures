"""Offline local-mock checks for the distinct Protocol 30 identity fixture."""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
import tomllib
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import mock_rpc  # noqa: E402
import scval_xdr  # noqa: E402

from tests import xdr_codec  # noqa: E402
from tools.evidence import capture_live  # noqa: E402
from tools.registry import generate as registry_generate  # noqa: E402

PACK30 = ROOT / "protocol-30"
PACK29 = ROOT / "protocol-29"
FIXTURE = PACK30 / "rpc" / "p30-rpc-version-info-protocol-30.toml"
CAP84_FIXTURE = PACK30 / "xdr" / "cap-0084" / "p30-xdr-cap0084-muxed-contract-address-roundtrip.toml"
CAP88_SIGNED_FIXTURE = PACK30 / "xdr" / "cap-0088" / "p30-xdr-cap0088-stellar-value-signed-ms-roundtrip.toml"
CAP88_EMPTY_FIXTURE = PACK30 / "xdr" / "cap-0088" / "p30-xdr-cap0088-stellar-value-empty-tx-set-ms-roundtrip.toml"


def load_xdr_fixture(path: Path) -> tuple[dict, bytes]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data, base64.b64decode(data["value_base64"], validate=True)


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
        registry = json.loads(registry_generate.generate(PACK30))
        self.assertEqual(registry["protocol"], 30)
        entries = {entry["id"]: entry for entry in registry["fixtures"]}
        self.assertTrue(
            {
                "p30-rpc-version-info-protocol-30",
                "p30-xdr-cap0084-muxed-contract-address-roundtrip",
                "p30-xdr-cap0088-stellar-value-signed-ms-roundtrip",
                "p30-xdr-cap0088-stellar-value-empty-tx-set-ms-roundtrip",
            } <= set(entries),
            "required Protocol 30 baseline fixtures must stay in the generated registry",
        )
        paths = {
            "p30-rpc-version-info-protocol-30": FIXTURE,
            "p30-xdr-cap0084-muxed-contract-address-roundtrip": CAP84_FIXTURE,
            "p30-xdr-cap0088-stellar-value-signed-ms-roundtrip": CAP88_SIGNED_FIXTURE,
            "p30-xdr-cap0088-stellar-value-empty-tx-set-ms-roundtrip": CAP88_EMPTY_FIXTURE,
        }
        for fixture_id, path in paths.items():
            with self.subTest(fixture_id=fixture_id):
                entry = entries[fixture_id]
                self.assertEqual(entry["path"], path.relative_to(PACK30).as_posix())
                self.assertEqual(
                    entry["sha256"], hashlib.sha256(path.read_bytes()).hexdigest()
                )

    def test_cap84_muxed_contract_address_fields(self) -> None:
        data, raw = load_xdr_fixture(CAP84_FIXTURE)
        self.assertEqual(data["type"], "ScVal")
        self.assertEqual(data["kind"], "roundtrip")

        decoded = scval_xdr.decode(raw)
        self.assertEqual(decoded[0], "address")
        self.assertEqual(
            decoded[1],
            {
                "type": "muxed-contract",
                "id": 0x0102030405060708,
                "contract_id": bytes([0x22]) * 32,
            },
        )
        self.assertEqual(raw, scval_xdr.encode(decoded))
        json_value = scval_xdr.to_json(decoded)
        self.assertEqual(
            json_value,
            {
                "type": "address",
                "value": {
                    "type": "muxed-contract",
                    "id": 0x0102030405060708,
                    "contract_id": (bytes([0x22]) * 32).hex(),
                },
            },
        )
        self.assertEqual(scval_xdr.from_json(json_value), decoded)

    def test_cap88_millisecond_stellar_value_fields_and_time_relation(self) -> None:
        signed_data, signed_raw = load_xdr_fixture(CAP88_SIGNED_FIXTURE)
        empty_data, empty_raw = load_xdr_fixture(CAP88_EMPTY_FIXTURE)
        self.assertEqual(signed_data["type"], "StellarValue")
        self.assertEqual(empty_data["type"], "StellarValue")

        signed = xdr_codec.decode_stellar_value(signed_raw)
        self.assertEqual(signed.tx_set_hash, bytes([0x11]) * 32)
        self.assertEqual(signed.close_time, 1_700_000_123)
        self.assertEqual(signed.upgrades, [])
        self.assertEqual(signed.ext.ext_type, xdr_codec.STELLAR_VALUE_SIGNED_MS)
        self.assertIsNotNone(signed.ext.signed_ms_value)
        signed_ms = signed.ext.signed_ms_value
        self.assertEqual(signed_ms.close_time_ms, 1_700_000_123_456)
        self.assertEqual(signed.close_time, signed_ms.close_time_ms // 1000)
        self.assertEqual(signed_ms.lc_value_signature.node_id.ed25519, bytes([0x66]) * 32)
        self.assertEqual(signed_ms.lc_value_signature.signature, bytes([0x55]) * 64)

        empty = xdr_codec.decode_stellar_value(empty_raw)
        self.assertEqual(empty.tx_set_hash, bytes(32))
        self.assertEqual(empty.close_time, 1_700_000_123)
        self.assertEqual(empty.upgrades, [])
        self.assertEqual(empty.ext.ext_type, xdr_codec.STELLAR_VALUE_EMPTY_TX_SET_MS)
        self.assertIsNotNone(empty.ext.proposed_ms_value)
        proposed_ms = empty.ext.proposed_ms_value
        self.assertEqual(proposed_ms.close_time_ms, 1_700_000_123_456)
        self.assertEqual(empty.close_time, proposed_ms.close_time_ms // 1000)
        self.assertEqual(proposed_ms.tx_set_hash, bytes([0x33]) * 32)
        self.assertEqual(proposed_ms.previous_ledger_hash, bytes([0x44]) * 32)
        self.assertEqual(proposed_ms.previous_ledger_version, 30)
        self.assertEqual(proposed_ms.lc_value_signature.node_id.ed25519, bytes([0x66]) * 32)
        self.assertEqual(proposed_ms.lc_value_signature.signature, bytes([0x55]) * 64)

    def test_cap84_and_cap88_truncated_xdr_is_rejected(self) -> None:
        for path, decoder in (
            (CAP84_FIXTURE, scval_xdr.decode),
            (CAP88_SIGNED_FIXTURE, xdr_codec.decode_stellar_value),
            (CAP88_EMPTY_FIXTURE, xdr_codec.decode_stellar_value),
        ):
            _, raw = load_xdr_fixture(path)
            error_type = (
                scval_xdr.XdrDecodeError
                if decoder is scval_xdr.decode
                else xdr_codec.XdrCodecError
            )
            with self.subTest(fixture=path.name), self.assertRaises(error_type):
                decoder(raw[:-1])

    def test_new_xdr_encoders_reject_out_of_range_values(self) -> None:
        with self.assertRaises(scval_xdr.XdrEncodeError):
            scval_xdr.encode(
                (
                    "address",
                    {
                        "type": "muxed-contract",
                        "id": 1 << 64,
                        "contract_id": bytes(32),
                    },
                )
            )
        with self.assertRaises(scval_xdr.XdrEncodeError):
            scval_xdr.encode(
                (
                    "address",
                    {
                        "type": "muxed-contract",
                        "id": 1,
                        "contract_id": bytes(31),
                    },
                )
            )

        _, raw = load_xdr_fixture(CAP88_SIGNED_FIXTURE)
        signed = xdr_codec.decode_stellar_value(raw)
        signed_ms = replace(signed.ext.signed_ms_value, close_time_ms=1 << 64)
        invalid = replace(
            signed,
            ext=replace(signed.ext, signed_ms_value=signed_ms),
        )
        with self.assertRaises(xdr_codec.XdrCodecError):
            xdr_codec.encode_stellar_value(invalid)

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
