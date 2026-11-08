"""Typed Protocol 28 oracle vectors using existing identity/asset primitives."""

from __future__ import annotations

import base64
import unittest

from tests import operation_xdr, xdr_codec

# Produced by stellar-xdr 28.0.1 WriteXdr from typed Operation values. The
# values exercise XDR structure only.
ORACLE_VECTORS = {
    "create_account": "AAAAAAAAAAAAAAAAERERERERERERERERERERERERERERERERERERERERERF//////////w==",
    "account_merge": "AAAAAQAAAAAzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMwAAAAgAAAEA//////////8iIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIg==",
    "claim_claimable_balance": "AAAAAAAAAA8AAAAAREREREREREREREREREREREREREREREREREREREREREQ=",
    "begin_sponsoring_future_reserves": "AAAAAAAAABAAAAAAVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVU=",
    "clawback_claimable_balance": "AAAAAAAAABQAAAAAZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmY=",
}


def decode_operation(data: bytes) -> xdr_codec.Operation:
    reader = xdr_codec.XdrReader(data)
    operation = xdr_codec._decode_operation(reader)
    reader.assert_eof()
    return operation


def encode_operation(operation: xdr_codec.Operation) -> bytes:
    writer = xdr_codec.XdrWriter()
    xdr_codec._encode_operation(writer, operation)
    return writer.to_bytes()


def through_transaction_envelope(operation: xdr_codec.Operation) -> xdr_codec.Operation:
    tx = xdr_codec.Transaction(
        source_account=xdr_codec.MuxedAccount(
            key_type=xdr_codec.KEY_TYPE_ED25519, ed25519=b"\xaa" * 32
        ),
        fee=1,
        seq_num=1,
        cond=xdr_codec.Preconditions(precond_type=xdr_codec.PRECOND_NONE),
        memo=xdr_codec.Memo(memo_type=xdr_codec.MEMO_NONE),
        operations=[operation],
        ext=xdr_codec.TransactionExt(ext_type=0),
    )
    envelope = xdr_codec.TransactionEnvelope(
        envelope_type=xdr_codec.ENVELOPE_TYPE_TX,
        v1=xdr_codec.TransactionV1Envelope(tx=tx, signatures=[]),
    )
    raw = xdr_codec.encode_transaction_envelope(envelope)
    decoded = xdr_codec.decode_transaction_envelope(raw)
    if xdr_codec.encode_transaction_envelope(decoded) != raw:
        raise AssertionError("transaction envelope did not re-encode exactly")
    return decoded.v1.tx.operations[0]


class IdentityOperationCodecTests(unittest.TestCase):
    def test_official_operation_vectors_decode_and_reencode_exactly(self) -> None:
        for name, encoded in ORACLE_VECTORS.items():
            with self.subTest(operation=name):
                raw = base64.b64decode(encoded, validate=True)
                operation = decode_operation(raw)
                self.assertEqual(encode_operation(operation), raw)
                self.assertEqual(through_transaction_envelope(operation), operation)

    def test_create_account_preserves_account_id_and_signed_int64(self) -> None:
        operation = decode_operation(
            base64.b64decode(ORACLE_VECTORS["create_account"], validate=True)
        )
        self.assertEqual(operation.body.op_type, operation_xdr.OPERATION_TYPE_CREATE_ACCOUNT)
        payload = operation.body.operation
        self.assertIsInstance(payload, operation_xdr.CreateAccountOp)
        self.assertEqual(payload.destination.key_type, xdr_codec.PUBLIC_KEY_TYPE_ED25519)
        self.assertEqual(payload.destination.ed25519, b"\x11" * 32)
        self.assertEqual(payload.starting_balance, (1 << 63) - 1)

    def test_account_merge_preserves_optional_source_and_muxed_destination(self) -> None:
        operation = decode_operation(
            base64.b64decode(ORACLE_VECTORS["account_merge"], validate=True)
        )
        self.assertIsNotNone(operation.source_account)
        self.assertEqual(operation.source_account.key_type, xdr_codec.KEY_TYPE_ED25519)
        self.assertEqual(operation.source_account.ed25519, b"\x33" * 32)
        payload = operation.body.operation
        self.assertIsInstance(payload, operation_xdr.AccountMergeOp)
        self.assertEqual(payload.destination.key_type, xdr_codec.KEY_TYPE_MUXED_ED25519)
        self.assertEqual(payload.destination.muxed.id, (1 << 64) - 1)
        self.assertEqual(payload.destination.muxed.ed25519, b"\x22" * 32)

    def test_sponsorship_and_claimable_balance_fields(self) -> None:
        sponsoring = decode_operation(
            base64.b64decode(ORACLE_VECTORS["begin_sponsoring_future_reserves"], validate=True)
        )
        self.assertIsInstance(
            sponsoring.body.operation,
            operation_xdr.BeginSponsoringFutureReservesOp,
        )
        self.assertEqual(sponsoring.body.operation.sponsored_id.ed25519, b"\x55" * 32)

        for name, expected in (
            ("claim_claimable_balance", b"\x44" * 32),
            ("clawback_claimable_balance", b"\x66" * 32),
        ):
            with self.subTest(operation=name):
                operation = decode_operation(base64.b64decode(ORACLE_VECTORS[name], validate=True))
                self.assertEqual(operation.body.operation.balance_id.id_type, 0)
                self.assertEqual(operation.body.operation.balance_id.v0, expected)

    def test_claimable_balance_union_and_opaque_length_are_checked(self) -> None:
        invalid_id = (
            (0).to_bytes(4, "big")
            + operation_xdr.OPERATION_TYPE_CLAIM_CLAIMABLE_BALANCE.to_bytes(4, "big")
            + (1).to_bytes(4, "big")
            + (b"\x00" * 32)
        )
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "ClaimableBalanceIDType"):
            decode_operation(invalid_id)

        invalid_hash = xdr_codec.Operation(
            source_account=None,
            body=xdr_codec.OperationBody(
                op_type=operation_xdr.OPERATION_TYPE_CLAIM_CLAIMABLE_BALANCE,
                operation=operation_xdr.ClaimClaimableBalanceOp(
                    balance_id=operation_xdr.ClaimableBalanceID(id_type=0, v0=b"\x00" * 31)
                ),
            ),
        )
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "32 bytes"):
            encode_operation(invalid_hash)


if __name__ == "__main__":
    unittest.main()
