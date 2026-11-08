"""Protocol 28 CLAWBACK codec checks against typed official XDR vectors."""

from __future__ import annotations

import base64
import unittest

from tests import operation_xdr, xdr_codec

# Generated with stellar-xdr 28.0.1 using typed Operation values and
# WriteXdr::to_xdr_base64(Limits::none()). The pinned schema is
# stellar/stellar-xdr commit 9c9c145953e80990d6ff1ae3a6a973a0ce6d0694.
#
# Typed constructions:
# - Native/classic/max:
#   Operation { source_account: None, body: OperationBody::Clawback(
#     ClawbackOp { asset: Asset::Native,
#       from: MuxedAccount::Ed25519(Uint256([0x11; 32])), amount: i64::MAX }) }
# - Native/muxed/min:
#   Operation { source_account: None, body: OperationBody::Clawback(
#     ClawbackOp { asset: Asset::Native,
#       from: MuxedAccount::MuxedEd25519(MuxedAccountMed25519 {
#         id: u64::MAX, ed25519: Uint256([0x22; 32]) }), amount: i64::MIN }) }
# - CreditAlphanum4/classic/17:
#   Operation { source_account: None, body: OperationBody::Clawback(
#     ClawbackOp { asset: Asset::CreditAlphanum4(AlphaNum4 {
#       asset_code: AssetCode4(*b"CLAW"), issuer: AccountId(
#         PublicKey::PublicKeyTypeEd25519(Uint256([0x33; 32]))) }),
#       from: MuxedAccount::Ed25519(Uint256([0x44; 32])), amount: 17 }) }
# - V1 envelope: TransactionEnvelope::Tx(TransactionV1Envelope { tx:
#   Transaction { source_account: MuxedAccount::Ed25519(Uint256([0xaa; 32])),
#     fee: 100, seq_num: SequenceNumber(1), cond: Preconditions::None,
#     memo: Memo::None, operations: vec![credit4_operation],
#     ext: TransactionExt::V0 }, signatures: Default::default() })
ORACLE_VECTORS = {
    "native_classic_int64_max": "AAAAAAAAABMAAAAAAAAAABERERERERERERERERERERERERERERERERERERERERERf/////////8=",
    "native_muxed_int64_min": "AAAAAAAAABMAAAAAAAABAP//////////IiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiKAAAAAAAAAAA==",
    "credit_alphanum4_classic": "AAAAAAAAABMAAAABQ0xBVwAAAAAzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMwAAAABERERERERERERERERERERERERERERERERERERERERERAAAAAAAAAAR",
}

ENVELOPE_ORACLE = "AAAAAgAAAACqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqgAAAGQAAAAAAAAAAQAAAAAAAAAAAAAAAQAAAAAAAAATAAAAAUNMQVcAAAAAMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMAAAAAREREREREREREREREREREREREREREREREREREREREREQAAAAAAAAAEQAAAAAAAAAA"


def decode_operation(data: bytes) -> xdr_codec.Operation:
    reader = xdr_codec.XdrReader(data)
    operation = xdr_codec._decode_operation(reader)
    reader.assert_eof()
    return operation


def encode_operation(operation: xdr_codec.Operation) -> bytes:
    writer = xdr_codec.XdrWriter()
    xdr_codec._encode_operation(writer, operation)
    return writer.to_bytes()


class ClawbackOperationCodecTests(unittest.TestCase):
    def test_typed_oracle_vectors_preserve_discriminant_fields_and_bytes(self) -> None:
        vectors = {
            "native_classic_int64_max": (
                xdr_codec.ASSET_TYPE_NATIVE,
                xdr_codec.KEY_TYPE_ED25519,
                b"\x11" * 32,
                None,
                (1 << 63) - 1,
            ),
            "native_muxed_int64_min": (
                xdr_codec.ASSET_TYPE_NATIVE,
                xdr_codec.KEY_TYPE_MUXED_ED25519,
                b"\x22" * 32,
                (1 << 64) - 1,
                -(1 << 63),
            ),
            "credit_alphanum4_classic": (
                xdr_codec.ASSET_TYPE_CREDIT_ALPHANUM4,
                xdr_codec.KEY_TYPE_ED25519,
                b"\x44" * 32,
                None,
                17,
            ),
        }

        for name, expected in vectors.items():
            with self.subTest(operation=name):
                raw = base64.b64decode(ORACLE_VECTORS[name], validate=True)
                operation = decode_operation(raw)
                self.assertIsNone(operation.source_account)
                self.assertEqual(operation.body.op_type, operation_xdr.OPERATION_TYPE_CLAWBACK)
                payload = operation.body.operation
                self.assertIsInstance(payload, operation_xdr.ClawbackOp)
                self.assertEqual(payload.asset.asset_type, expected[0])
                self.assertEqual(payload.from_account.key_type, expected[1])
                self.assertEqual(payload.amount, expected[4])
                if payload.from_account.key_type == xdr_codec.KEY_TYPE_ED25519:
                    self.assertEqual(payload.from_account.ed25519, expected[2])
                else:
                    self.assertEqual(payload.from_account.muxed.ed25519, expected[2])
                    self.assertEqual(payload.from_account.muxed.id, expected[3])
                if name == "credit_alphanum4_classic":
                    asset = payload.asset.alpha_num4
                    self.assertEqual(asset.asset_code, b"CLAW")
                    self.assertEqual(asset.issuer.ed25519, b"\x33" * 32)
                self.assertEqual(encode_operation(operation), raw)

    def test_full_v1_transaction_envelope_roundtrips_exactly(self) -> None:
        raw = base64.b64decode(ENVELOPE_ORACLE, validate=True)
        envelope = xdr_codec.decode_transaction_envelope(raw)
        self.assertEqual(envelope.envelope_type, xdr_codec.ENVELOPE_TYPE_TX)
        self.assertEqual(len(envelope.v1.tx.operations), 1)
        operation = envelope.v1.tx.operations[0]
        self.assertEqual(operation.body.op_type, operation_xdr.OPERATION_TYPE_CLAWBACK)
        payload = operation.body.operation
        self.assertIsInstance(payload, operation_xdr.ClawbackOp)
        self.assertEqual(payload.asset.asset_type, xdr_codec.ASSET_TYPE_CREDIT_ALPHANUM4)
        self.assertEqual(payload.asset.alpha_num4.asset_code, b"CLAW")
        self.assertEqual(payload.asset.alpha_num4.issuer.ed25519, b"\x33" * 32)
        self.assertEqual(payload.from_account.ed25519, b"\x44" * 32)
        self.assertEqual(payload.amount, 17)
        encoded = xdr_codec.encode_transaction_envelope(envelope)
        self.assertEqual(encoded, raw)
        self.assertEqual(
            xdr_codec.encode_transaction_envelope(xdr_codec.decode_transaction_envelope(encoded)),
            raw,
        )

    def test_bad_union_tags_and_truncated_payloads_are_rejected(self) -> None:
        native = bytearray(base64.b64decode(ORACLE_VECTORS["native_classic_int64_max"]))
        bad_asset = native.copy()
        bad_asset[8:12] = (99).to_bytes(4, "big")
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "AssetType discriminant"):
            decode_operation(bytes(bad_asset))

        bad_account = native.copy()
        bad_account[12:16] = (99).to_bytes(4, "big")
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "CryptoKeyType discriminant"):
            decode_operation(bytes(bad_account))

        unsupported_operation = native.copy()
        unsupported_operation[4:8] = (18).to_bytes(4, "big")
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "unsupported OperationType arm"):
            decode_operation(bytes(unsupported_operation))

        for name, encoded in ORACLE_VECTORS.items():
            raw = base64.b64decode(encoded, validate=True)
            for end in range(len(raw)):
                with self.subTest(operation=name, truncated_at=end):
                    with self.assertRaises(xdr_codec.XdrCodecError):
                        decode_operation(raw[:end])

    def test_amount_outside_int64_and_wrong_payload_are_rejected(self) -> None:
        for amount in (-(1 << 63) - 1, 1 << 63):
            with self.subTest(amount=amount):
                operation = xdr_codec.Operation(
                    source_account=None,
                    body=xdr_codec.OperationBody(
                        op_type=operation_xdr.OPERATION_TYPE_CLAWBACK,
                        operation=operation_xdr.ClawbackOp(
                            asset=xdr_codec.Asset(asset_type=xdr_codec.ASSET_TYPE_NATIVE),
                            from_account=xdr_codec.MuxedAccount(
                                key_type=xdr_codec.KEY_TYPE_ED25519,
                                ed25519=b"\x11" * 32,
                            ),
                            amount=amount,
                        ),
                    ),
                )
                with self.assertRaisesRegex(xdr_codec.XdrCodecError, "int64 range"):
                    encode_operation(operation)

        wrong_payload = xdr_codec.Operation(
            source_account=None,
            body=xdr_codec.OperationBody(
                op_type=operation_xdr.OPERATION_TYPE_CLAWBACK,
                operation=operation_xdr.ClawbackClaimableBalanceOp(
                    balance_id=operation_xdr.ClaimableBalanceID(0, b"\x00" * 32)
                ),
            ),
        )
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "ClawbackOp required"):
            encode_operation(wrong_payload)


if __name__ == "__main__":
    unittest.main()
