"""Oracle vectors for operation payloads with optional values and bounded fields."""

from __future__ import annotations

import base64
import unittest

from tests import operation_xdr, xdr_codec

# Produced by typed Operation values using stellar-xdr 28.0.1 and the pinned
# Stellar-transaction.x definition. These bytes establish XDR structure only.
ORACLE_VECTORS = {
    "path_payment_strict_receive": "AAAAAAAAAAIAAAAAf/////////8AAAEA//////////8iIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIgAAAACAAAAAAAAAAAAAAAUAAAAAAAAAAAAAAAAAAAAAAAAAAA==",
    "path_payment_strict_send": "AAAAAAAAAA0AAAAAgAAAAAAAAAAAAAEAAAAAAAAAAAd3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3dwAAAAB//////////wAAAAA=",
    "manage_data_present": "AAAAAAAAAAoAAABAbm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubgAAAAEAAABAAAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4OTo7PD0+Pw==",
    "manage_data_null": "AAAAAAAAAAoAAABAenp6enp6enp6enp6enp6enp6enp6enp6enp6enp6enp6enp6enp6enp6enp6enp6enp6enp6enp6enp6enp6egAAAAA=",
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


class CollectionOperationCodecTests(unittest.TestCase):
    def test_official_operation_vectors_roundtrip_directly_and_in_envelopes(self) -> None:
        for name, encoded in ORACLE_VECTORS.items():
            with self.subTest(operation=name):
                raw = base64.b64decode(encoded, validate=True)
                operation = decode_operation(raw)
                self.assertEqual(encode_operation(operation), raw)
                self.assertEqual(through_transaction_envelope(operation), operation)

    def test_path_payment_fields_and_five_asset_limit(self) -> None:
        receive = decode_operation(
            base64.b64decode(ORACLE_VECTORS["path_payment_strict_receive"], validate=True)
        )
        self.assertEqual(
            receive.body.op_type, operation_xdr.OPERATION_TYPE_PATH_PAYMENT_STRICT_RECEIVE
        )
        receive_payload = receive.body.operation
        self.assertIsInstance(receive_payload, operation_xdr.PathPaymentStrictReceiveOp)
        self.assertEqual(receive_payload.send_asset.asset_type, xdr_codec.ASSET_TYPE_NATIVE)
        self.assertEqual(receive_payload.send_max, (1 << 63) - 1)
        self.assertEqual(receive_payload.destination.muxed.id, (1 << 64) - 1)
        self.assertEqual(receive_payload.destination.muxed.ed25519, b"\x22" * 32)
        self.assertEqual(receive_payload.dest_asset.asset_type, xdr_codec.ASSET_TYPE_NATIVE)
        self.assertEqual(receive_payload.dest_amount, -(1 << 63))
        self.assertEqual(len(receive_payload.path), operation_xdr.MAX_ASSET_PATH_LENGTH)
        self.assertTrue(
            all(asset.asset_type == xdr_codec.ASSET_TYPE_NATIVE for asset in receive_payload.path)
        )

        send = decode_operation(
            base64.b64decode(ORACLE_VECTORS["path_payment_strict_send"], validate=True)
        )
        self.assertEqual(send.body.op_type, operation_xdr.OPERATION_TYPE_PATH_PAYMENT_STRICT_SEND)
        send_payload = send.body.operation
        self.assertIsInstance(send_payload, operation_xdr.PathPaymentStrictSendOp)
        self.assertEqual(send_payload.send_asset.asset_type, xdr_codec.ASSET_TYPE_NATIVE)
        self.assertEqual(send_payload.send_amount, -(1 << 63))
        self.assertEqual(send_payload.destination.muxed.id, 7)
        self.assertEqual(send_payload.destination.muxed.ed25519, b"\x77" * 32)
        self.assertEqual(send_payload.dest_asset.asset_type, xdr_codec.ASSET_TYPE_NATIVE)
        self.assertEqual(send_payload.dest_min, (1 << 63) - 1)
        self.assertEqual(send_payload.path, [])

    def test_manage_data_pointer_and_opaque_boundaries(self) -> None:
        present = decode_operation(
            base64.b64decode(ORACLE_VECTORS["manage_data_present"], validate=True)
        )
        self.assertEqual(present.body.op_type, operation_xdr.OPERATION_TYPE_MANAGE_DATA)
        present_payload = present.body.operation
        self.assertIsInstance(present_payload, operation_xdr.ManageDataOp)
        self.assertEqual(present_payload.data_name, "n" * 64)
        self.assertEqual(present_payload.data_value, bytes(range(64)))

        absent = decode_operation(
            base64.b64decode(ORACLE_VECTORS["manage_data_null"], validate=True)
        )
        self.assertEqual(absent.body.op_type, operation_xdr.OPERATION_TYPE_MANAGE_DATA)
        absent_payload = absent.body.operation
        self.assertIsInstance(absent_payload, operation_xdr.ManageDataOp)
        self.assertEqual(absent_payload.data_name, "z" * 64)
        self.assertIsNone(absent_payload.data_value)

    def test_overlong_vectors_pointers_and_opaque_values_are_rejected(self) -> None:
        receive = bytearray(
            base64.b64decode(ORACLE_VECTORS["path_payment_strict_receive"], validate=True)
        )
        # The path count follows the source flag, arm discriminant and fixed fields.
        path_count_offset = 4 + 4 + 4 + 8 + 44 + 4 + 8
        receive[path_count_offset : path_count_offset + 4] = (6).to_bytes(4, "big")
        with self.assertRaisesRegex(
            xdr_codec.XdrCodecError, "Asset path length 6 exceeds maximum 5"
        ):
            decode_operation(bytes(receive))

        invalid_path_asset = bytearray(
            base64.b64decode(ORACLE_VECTORS["path_payment_strict_receive"], validate=True)
        )
        last_asset_offset = path_count_offset + 4 + 4 * (operation_xdr.MAX_ASSET_PATH_LENGTH - 1)
        invalid_path_asset[last_asset_offset : last_asset_offset + 4] = (9).to_bytes(4, "big")
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "unknown AssetType discriminant: 9"):
            decode_operation(bytes(invalid_path_asset))

        too_long_path = xdr_codec.Operation(
            source_account=None,
            body=xdr_codec.OperationBody(
                op_type=operation_xdr.OPERATION_TYPE_PATH_PAYMENT_STRICT_RECEIVE,
                operation=operation_xdr.PathPaymentStrictReceiveOp(
                    send_asset=xdr_codec.Asset(asset_type=xdr_codec.ASSET_TYPE_NATIVE),
                    send_max=1,
                    destination=xdr_codec.MuxedAccount(
                        key_type=xdr_codec.KEY_TYPE_ED25519, ed25519=b"\x11" * 32
                    ),
                    dest_asset=xdr_codec.Asset(asset_type=xdr_codec.ASSET_TYPE_NATIVE),
                    dest_amount=1,
                    path=[xdr_codec.Asset(asset_type=xdr_codec.ASSET_TYPE_NATIVE)] * 6,
                ),
            ),
        )
        with self.assertRaisesRegex(
            xdr_codec.XdrCodecError, "Asset path length 6 exceeds maximum 5"
        ):
            encode_operation(too_long_path)

        present = bytearray(base64.b64decode(ORACLE_VECTORS["manage_data_present"], validate=True))
        pointer_offset = 4 + 4 + 4 + 64
        present[pointer_offset : pointer_offset + 4] = (2).to_bytes(4, "big")
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "dataValue pointer discriminant: 2"):
            decode_operation(bytes(present))

        oversized_value = bytearray(
            base64.b64decode(ORACLE_VECTORS["manage_data_present"], validate=True)
        )
        value_length_offset = pointer_offset + 4
        oversized_value[value_length_offset : value_length_offset + 4] = (65).to_bytes(4, "big")
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "exceeds maximum allowed 64"):
            decode_operation(bytes(oversized_value))

        oversized_data = xdr_codec.Operation(
            source_account=None,
            body=xdr_codec.OperationBody(
                op_type=operation_xdr.OPERATION_TYPE_MANAGE_DATA,
                operation=operation_xdr.ManageDataOp(data_name="x" * 64, data_value=b"x" * 65),
            ),
        )
        with self.assertRaisesRegex(
            xdr_codec.XdrCodecError, "dataValue length 65 exceeds maximum 64"
        ):
            encode_operation(oversized_data)

        overlong_name = xdr_codec.Operation(
            source_account=None,
            body=xdr_codec.OperationBody(
                op_type=operation_xdr.OPERATION_TYPE_MANAGE_DATA,
                operation=operation_xdr.ManageDataOp(data_name="x" * 65, data_value=None),
            ),
        )
        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "exceeds maximum allowed 64"):
            encode_operation(overlong_name)


if __name__ == "__main__":
    unittest.main()
