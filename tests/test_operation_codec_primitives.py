"""Oracle vectors and malformed-input checks for primitive operation arms.

The official bytes below were produced by ``stellar-xdr = 28.0.1`` using its
typed ``Operation`` values and ``WriteXdr::to_xdr_base64(Limits::none())``.
The type definitions are pinned to stellar/stellar-xdr commit
9c9c145953e80990d6ff1ae3a6a973a0ce6d0694. These are structural XDR checks,
not transaction-validity or host-execution tests.
"""

from __future__ import annotations

import base64
import unittest

from tests import operation_xdr, xdr_codec

ORACLE_VECTORS = {
    "inflation": "AAAAAAAAAAk=",
    "bump_sequence": "AAAAAAAAAAuAAAAAAAAAAA==",
    "end_sponsoring_future_reserves": "AAAAAAAAABE=",
    "extend_footprint_ttl": "AAAAAAAAABkAAAAA/////w==",
    "restore_footprint": "AAAAAAAAABoAAAAA",
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


class PrimitiveOperationCodecTests(unittest.TestCase):
    def test_official_operation_vectors_decode_and_reencode_exactly(self) -> None:
        expected = {
            "inflation": (
                operation_xdr.OPERATION_TYPE_INFLATION,
                operation_xdr.InflationOp,
            ),
            "bump_sequence": (
                operation_xdr.OPERATION_TYPE_BUMP_SEQUENCE,
                operation_xdr.BumpSequenceOp,
            ),
            "end_sponsoring_future_reserves": (
                operation_xdr.OPERATION_TYPE_END_SPONSORING_FUTURE_RESERVES,
                operation_xdr.EndSponsoringFutureReservesOp,
            ),
            "extend_footprint_ttl": (
                operation_xdr.OPERATION_TYPE_EXTEND_FOOTPRINT_TTL,
                operation_xdr.ExtendFootprintTTLOp,
            ),
            "restore_footprint": (
                operation_xdr.OPERATION_TYPE_RESTORE_FOOTPRINT,
                operation_xdr.RestoreFootprintOp,
            ),
        }
        for name, encoded in ORACLE_VECTORS.items():
            with self.subTest(operation=name):
                raw = base64.b64decode(encoded, validate=True)
                operation = decode_operation(raw)
                self.assertIsNone(operation.source_account)
                self.assertEqual(operation.body.op_type, expected[name][0])
                payload = operation.body.operation
                self.assertIsInstance(payload, expected[name][1])
                self.assertEqual(encode_operation(operation), raw)
                nested = through_transaction_envelope(operation)
                self.assertEqual(nested, operation)
                self.assertIsInstance(nested.body.operation, expected[name][1])

    def test_decoded_scalar_fields_match_official_values(self) -> None:
        bump = decode_operation(base64.b64decode(ORACLE_VECTORS["bump_sequence"]))
        self.assertEqual(bump.body.operation.bump_to, -(1 << 63))

        extend = decode_operation(base64.b64decode(ORACLE_VECTORS["extend_footprint_ttl"]))
        self.assertEqual(extend.body.operation.extension_type, 0)
        self.assertEqual(extend.body.operation.extend_to, (1 << 32) - 1)

        restore = decode_operation(base64.b64decode(ORACLE_VECTORS["restore_footprint"]))
        self.assertEqual(restore.body.operation.extension_type, 0)

    def test_pointer_discriminant_extension_and_truncation_are_rejected(self) -> None:
        with self.assertRaises(xdr_codec.XdrCodecError):
            decode_operation((2).to_bytes(4, "big") + (9).to_bytes(4, "big"))

        bad_extension = (
            (0).to_bytes(4, "big")
            + operation_xdr.OPERATION_TYPE_EXTEND_FOOTPRINT_TTL.to_bytes(4, "big")
            + (1).to_bytes(4, "big")
            + (0).to_bytes(4, "big")
        )
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "ExtensionPoint"):
            decode_operation(bad_extension)

        unknown_type = (0).to_bytes(4, "big") + (99).to_bytes(4, "big")
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "OperationType arm"):
            decode_operation(unknown_type)

        for encoded in ORACLE_VECTORS.values():
            raw = base64.b64decode(encoded, validate=True)
            for offset in range(len(raw)):
                with self.subTest(encoded=encoded, offset=offset):
                    with self.assertRaises(xdr_codec.XdrCodecError):
                        decode_operation(raw[:offset])

    def test_out_of_range_values_and_wrong_models_are_rejected_on_encode(self) -> None:
        invalid = xdr_codec.Operation(
            source_account=None,
            body=xdr_codec.OperationBody(
                op_type=operation_xdr.OPERATION_TYPE_BUMP_SEQUENCE,
                operation=operation_xdr.BumpSequenceOp(bump_to=1 << 63),
            ),
        )
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "int64 range"):
            encode_operation(invalid)

        below_int64_min = xdr_codec.Operation(
            source_account=None,
            body=xdr_codec.OperationBody(
                op_type=operation_xdr.OPERATION_TYPE_BUMP_SEQUENCE,
                operation=operation_xdr.BumpSequenceOp(bump_to=-(1 << 63) - 1),
            ),
        )
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "int64 range"):
            encode_operation(below_int64_min)

        invalid_ttl = xdr_codec.Operation(
            source_account=None,
            body=xdr_codec.OperationBody(
                op_type=operation_xdr.OPERATION_TYPE_EXTEND_FOOTPRINT_TTL,
                operation=operation_xdr.ExtendFootprintTTLOp(extension_type=0, extend_to=1 << 32),
            ),
        )
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "uint32 range"):
            encode_operation(invalid_ttl)

        negative_ttl = xdr_codec.Operation(
            source_account=None,
            body=xdr_codec.OperationBody(
                op_type=operation_xdr.OPERATION_TYPE_EXTEND_FOOTPRINT_TTL,
                operation=operation_xdr.ExtendFootprintTTLOp(extension_type=0, extend_to=-1),
            ),
        )
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "uint32 range"):
            encode_operation(negative_ttl)

        wrong_model = xdr_codec.Operation(
            source_account=None,
            body=xdr_codec.OperationBody(
                op_type=operation_xdr.OPERATION_TYPE_INFLATION,
                operation=operation_xdr.RestoreFootprintOp(extension_type=0),
            ),
        )
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "InflationOp required"):
            encode_operation(wrong_model)


if __name__ == "__main__":
    unittest.main()
