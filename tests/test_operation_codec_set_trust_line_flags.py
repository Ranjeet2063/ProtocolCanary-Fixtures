"""SET_TRUST_LINE_FLAGS against typed Protocol 28 XDR oracle vectors."""

from __future__ import annotations

import base64
import unittest
from dataclasses import replace

from tests import operation_xdr, xdr_codec

# Generated with official stellar-xdr = 28.0.1, rustc/cargo 1.97.1, and
# WriteXdr::to_xdr_base64(Limits::none()). The schema is pinned to
# stellar/stellar-xdr commit 9c9c145953e80990d6ff1ae3a6a973a0ce6d0694.
#
# Typed construction: account(b) = AccountId(
#   PublicKey::PublicKeyTypeEd25519(Uint256([b; 32]))).
# operation(t, a, c, s) = Operation { source_account: None,
#   body: OperationBody::SetTrustLineFlags(SetTrustLineFlagsOp {
#     trustor: t, asset: a, clear_flags: c, set_flags: s }) }.
# - native = operation(account(0x11), Asset::Native, u32::MAX, 0)
# - credit4 = operation(account(0x22), Asset::CreditAlphanum4(AlphaNum4 {
#     asset_code: AssetCode4(*b"FLAG"), issuer: account(0x33) }), 0, u32::MAX)
# - credit12 = operation(account(0x44), Asset::CreditAlphanum12(AlphaNum12 {
#     asset_code: AssetCode12(*b"TWELVE_BYTES"), issuer: account(0x55) }),
#     0x12345678, 0xa5a5a5a5)
# Each envelope is TransactionEnvelope::Tx(TransactionV1Envelope {
#   tx: Transaction { source_account: MuxedAccount::Ed25519(Uint256([0xaa; 32])),
#     fee: 100, seq_num: SequenceNumber(1), cond: Preconditions::None,
#     memo: Memo::None, operations: vec![named_operation],
#     ext: TransactionExt::V0 }, signatures: Default::default() }).
OPERATION_ORACLES = {
    "native": "AAAAAAAAABUAAAAAEREREREREREREREREREREREREREREREREREREREREREAAAAA/////wAAAAA=",
    "credit4": "AAAAAAAAABUAAAAAIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIAAAABRkxBRwAAAAAzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMwAAAAD/////",
    "credit12": "AAAAAAAAABUAAAAAREREREREREREREREREREREREREREREREREREREREREQAAAACVFdFTFZFX0JZVEVTAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVEjRWeKWlpaU=",
}

ENVELOPE_ORACLES = {
    "native": "AAAAAgAAAACqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqgAAAGQAAAAAAAAAAQAAAAAAAAAAAAAAAQAAAAAAAAAVAAAAABERERERERERERERERERERERERERERERERERERERERERAAAAAP////8AAAAAAAAAAAAAAAA=",
    "credit12": "AAAAAgAAAACqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqgAAAGQAAAAAAAAAAQAAAAAAAAAAAAAAAQAAAAAAAAAVAAAAAEREREREREREREREREREREREREREREREREREREREREREAAAAAlRXRUxWRV9CWVRFUwAAAABVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVRI0VnilpaWlAAAAAAAAAAA=",
}


def decode_operation(raw: bytes) -> xdr_codec.Operation:
    reader = xdr_codec.XdrReader(raw)
    operation = xdr_codec._decode_operation(reader)
    reader.assert_eof()
    return operation


def encode_operation(operation: xdr_codec.Operation) -> bytes:
    writer = xdr_codec.XdrWriter()
    xdr_codec._encode_operation(writer, operation)
    return writer.to_bytes()


class SetTrustLineFlagsCodecTests(unittest.TestCase):
    def test_typed_operation_vectors_preserve_fields_and_bytes(self) -> None:
        expected = {
            "native": (b"\x11" * 32, xdr_codec.ASSET_TYPE_NATIVE, None, None, 0xFFFFFFFF, 0),
            "credit4": (
                b"\x22" * 32,
                xdr_codec.ASSET_TYPE_CREDIT_ALPHANUM4,
                b"FLAG",
                b"\x33" * 32,
                0,
                0xFFFFFFFF,
            ),
            "credit12": (
                b"\x44" * 32,
                xdr_codec.ASSET_TYPE_CREDIT_ALPHANUM12,
                b"TWELVE_BYTES",
                b"\x55" * 32,
                0x12345678,
                0xA5A5A5A5,
            ),
        }
        for name, encoded in OPERATION_ORACLES.items():
            with self.subTest(operation=name):
                raw = base64.b64decode(encoded, validate=True)
                operation = decode_operation(raw)
                self.assertIsNone(operation.source_account)
                self.assertEqual(raw[4:8], (21).to_bytes(4, "big"))
                self.assertEqual(
                    operation.body.op_type, operation_xdr.OPERATION_TYPE_SET_TRUST_LINE_FLAGS
                )
                payload = operation.body.operation
                self.assertIsInstance(payload, operation_xdr.SetTrustLineFlagsOp)
                trustor, asset_type, code, issuer, clear_flags, set_flags = expected[name]
                self.assertEqual(payload.trustor.key_type, xdr_codec.PUBLIC_KEY_TYPE_ED25519)
                self.assertEqual(payload.trustor.ed25519, trustor)
                self.assertEqual(payload.asset.asset_type, asset_type)
                self.assertEqual(
                    (payload.clear_flags, payload.set_flags), (clear_flags, set_flags)
                )
                if code is not None:
                    alpha = (
                        payload.asset.alpha_num4
                        if asset_type == xdr_codec.ASSET_TYPE_CREDIT_ALPHANUM4
                        else payload.asset.alpha_num12
                    )
                    self.assertEqual(alpha.asset_code, code)
                    self.assertEqual(alpha.issuer.ed25519, issuer)
                self.assertEqual(encode_operation(operation), raw)

    def test_official_v1_envelopes_roundtrip_byte_for_byte(self) -> None:
        for name, encoded in ENVELOPE_ORACLES.items():
            with self.subTest(envelope=name):
                raw = base64.b64decode(encoded, validate=True)
                envelope = xdr_codec.decode_transaction_envelope(raw)
                self.assertEqual(envelope.envelope_type, xdr_codec.ENVELOPE_TYPE_TX)
                self.assertEqual(envelope.v1.tx.source_account.ed25519, b"\xaa" * 32)
                self.assertEqual(len(envelope.v1.tx.operations), 1)
                operation = envelope.v1.tx.operations[0]
                self.assertEqual(
                    operation,
                    decode_operation(base64.b64decode(OPERATION_ORACLES[name], validate=True)),
                )
                self.assertEqual(xdr_codec.encode_transaction_envelope(envelope), raw)

    def test_malformed_nested_tags_truncation_and_trailing_bytes_are_rejected(self) -> None:
        raw = base64.b64decode(OPERATION_ORACLES["native"], validate=True)
        bad_trustor = bytearray(raw)
        bad_trustor[8:12] = (1).to_bytes(4, "big")
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "PublicKeyType discriminant"):
            decode_operation(bytes(bad_trustor))

        # TrustLineAsset accepts pool shares; the Asset field here does not.
        bad_asset = bytearray(raw)
        bad_asset[44:48] = (3).to_bytes(4, "big")
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "AssetType discriminant"):
            decode_operation(bytes(bad_asset))

        with self.assertRaises(xdr_codec.XdrCodecError):
            decode_operation(raw + b"\x00")
        for name, encoded in OPERATION_ORACLES.items():
            vector = base64.b64decode(encoded, validate=True)
            for end in range(len(vector)):
                with self.subTest(operation=name, truncated_at=end):
                    with self.assertRaises(xdr_codec.XdrCodecError):
                        decode_operation(vector[:end])

    def test_uint32_bounds_and_wrong_payload_are_rejected(self) -> None:
        operation = decode_operation(base64.b64decode(OPERATION_ORACLES["native"]))
        for field in ("clear_flags", "set_flags"):
            for value in (-1, 1 << 32):
                with self.subTest(field=field, value=value):
                    payload = replace(operation.body.operation, **{field: value})
                    invalid = replace(operation, body=replace(operation.body, operation=payload))
                    with self.assertRaisesRegex(xdr_codec.XdrCodecError, "uint32 range"):
                        encode_operation(invalid)

        invalid = replace(
            operation,
            body=replace(operation.body, operation=operation_xdr.InflationOp()),
        )
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "SetTrustLineFlagsOp required"):
            encode_operation(invalid)


if __name__ == "__main__":
    unittest.main()
