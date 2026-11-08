"""Three Protocol 28 offer operations against typed official XDR vectors.

Generated with ``stellar-xdr = 28.0.1`` and
``WriteXdr::to_xdr_base64(Limits::none())``; the official ``ReadXdr`` decoder
also roundtripped each typed value. The schema is pinned to stellar/stellar-xdr
commit 9c9c145953e80990d6ff1ae3a6a973a0ce6d0694. These values check XDR
structure, not offer validity, authorization, ledger state, or network behavior.

Typed construction helpers in the oracle program:
``account(b) = AccountId(PublicKey::PublicKeyTypeEd25519(Uint256([b; 32])))``;
``credit4(code, b) = Asset::CreditAlphanum4(AlphaNum4 { asset_code:
AssetCode4(code), issuer: account(b) })``; ``credit12(b)`` uses
``AssetCode12(*b"TWELVE_BYTES")`` and ``account(b)``. Each operation has an
absent source account. The six ``OperationBody`` constructions are described
beside the vectors below. Each envelope is ``TransactionEnvelope::Tx`` with a
source key of ``0xaa`` repeated 32 times, fee 100, sequence 1, no preconditions
or memo, one named operation, V0 transaction extension, and no signatures.
"""

from __future__ import annotations

import base64
import struct
import unittest
from dataclasses import replace

from tests import operation_xdr, price_xdr, xdr_codec

INT64_MIN = -(1 << 63)
INT64_MAX = (1 << 63) - 1
INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1

# Typed OperationBody values:
# sell_boundary = ManageSellOffer { Native, credit4("BUY!", 0x11),
#     amount: i64::MIN, Price { n: i32::MIN, d: i32::MAX }, offer_id: i64::MAX }.
# sell_zero = ManageSellOffer { credit12(0x22), Native,
#     amount: 0, Price { n: 0, d: 0 }, offer_id: 0 }.
# passive_boundary = CreatePassiveSellOffer { credit4("SELL", 0x33),
#     credit12(0x44), amount: i64::MAX,
#     Price { n: i32::MAX, d: i32::MIN } }.
# passive_negative = CreatePassiveSellOffer { Native, credit4("BUY!", 0x55),
#     amount: -1, Price { n: -7, d: 3 } }.
# buy_boundary = ManageBuyOffer { credit12(0x66), credit4("BUY!", 0x77),
#     buy_amount: i64::MIN, Price { n: -1, d: 1 }, offer_id: i64::MIN }.
# buy_max = ManageBuyOffer { Native, Native, buy_amount: i64::MAX,
#     Price { n: 1, d: 2 }, offer_id: 0 }.
OPERATION_ORACLES = {
    "sell_boundary": "AAAAAAAAAAMAAAAAAAAAAUJVWSEAAAAAERERERERERERERERERERERERERERERERERERERERERGAAAAAAAAAAIAAAAB/////f/////////8=",
    "sell_zero": "AAAAAAAAAAMAAAACVFdFTFZFX0JZVEVTAAAAACIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==",
    "passive_boundary": "AAAAAAAAAAQAAAABU0VMTAAAAAAzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMwAAAAJUV0VMVkVfQllURVMAAAAARERERERERERERERERERERERERERERERERERERERERER//////////3////+AAAAA",
    "passive_negative": "AAAAAAAAAAQAAAAAAAAAAUJVWSEAAAAAVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVX///////////////kAAAAD",
    "buy_boundary": "AAAAAAAAAAwAAAACVFdFTFZFX0JZVEVTAAAAAGZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmAAAAAUJVWSEAAAAAd3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3eAAAAAAAAAAP////8AAAABgAAAAAAAAAA=",
    "buy_max": "AAAAAAAAAAwAAAAAAAAAAH//////////AAAAAQAAAAIAAAAAAAAAAA==",
}

ENVELOPE_ORACLES = {
    "sell_boundary": "AAAAAgAAAACqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqgAAAGQAAAAAAAAAAQAAAAAAAAAAAAAAAQAAAAAAAAADAAAAAAAAAAFCVVkhAAAAABERERERERERERERERERERERERERERERERERERERERERgAAAAAAAAACAAAAAf////3//////////AAAAAAAAAAA=",
    "passive_boundary": "AAAAAgAAAACqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqgAAAGQAAAAAAAAAAQAAAAAAAAAAAAAAAQAAAAAAAAAEAAAAAVNFTEwAAAAAMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMAAAACVFdFTFZFX0JZVEVTAAAAAEREREREREREREREREREREREREREREREREREREREREREf/////////9/////gAAAAAAAAAAAAAAA",
    "buy_boundary": "AAAAAgAAAACqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqgAAAGQAAAAAAAAAAQAAAAAAAAAAAAAAAQAAAAAAAAAMAAAAAlRXRUxWRV9CWVRFUwAAAABmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZmZgAAAAFCVVkhAAAAAHd3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3d3gAAAAAAAAAD/////AAAAAYAAAAAAAAAAAAAAAAAAAAA=",
}


def key(byte: int) -> xdr_codec.PublicKey:
    return xdr_codec.PublicKey(xdr_codec.PUBLIC_KEY_TYPE_ED25519, bytes([byte]) * 32)


def native() -> xdr_codec.Asset:
    return xdr_codec.Asset(asset_type=xdr_codec.ASSET_TYPE_NATIVE)


def credit4(code: bytes, issuer: int) -> xdr_codec.Asset:
    return xdr_codec.Asset(
        asset_type=xdr_codec.ASSET_TYPE_CREDIT_ALPHANUM4,
        alpha_num4=xdr_codec.AlphaNum4(code, key(issuer)),
    )


def credit12(issuer: int) -> xdr_codec.Asset:
    return xdr_codec.Asset(
        asset_type=xdr_codec.ASSET_TYPE_CREDIT_ALPHANUM12,
        alpha_num12=xdr_codec.AlphaNum12(b"TWELVE_BYTES", key(issuer)),
    )


def operation(tag: int, payload: object) -> xdr_codec.Operation:
    return xdr_codec.Operation(
        source_account=None, body=xdr_codec.OperationBody(op_type=tag, operation=payload)
    )


EXPECTED = {
    "sell_boundary": operation(
        operation_xdr.OPERATION_TYPE_MANAGE_SELL_OFFER,
        operation_xdr.ManageSellOfferOp(
            native(),
            credit4(b"BUY!", 0x11),
            INT64_MIN,
            price_xdr.Price(INT32_MIN, INT32_MAX),
            INT64_MAX,
        ),
    ),
    "sell_zero": operation(
        operation_xdr.OPERATION_TYPE_MANAGE_SELL_OFFER,
        operation_xdr.ManageSellOfferOp(
            credit12(0x22),
            native(),
            0,
            price_xdr.Price(0, 0),
            0,
        ),
    ),
    "passive_boundary": operation(
        operation_xdr.OPERATION_TYPE_CREATE_PASSIVE_SELL_OFFER,
        operation_xdr.CreatePassiveSellOfferOp(
            credit4(b"SELL", 0x33),
            credit12(0x44),
            INT64_MAX,
            price_xdr.Price(INT32_MAX, INT32_MIN),
        ),
    ),
    "passive_negative": operation(
        operation_xdr.OPERATION_TYPE_CREATE_PASSIVE_SELL_OFFER,
        operation_xdr.CreatePassiveSellOfferOp(
            native(),
            credit4(b"BUY!", 0x55),
            -1,
            price_xdr.Price(-7, 3),
        ),
    ),
    "buy_boundary": operation(
        operation_xdr.OPERATION_TYPE_MANAGE_BUY_OFFER,
        operation_xdr.ManageBuyOfferOp(
            credit12(0x66),
            credit4(b"BUY!", 0x77),
            INT64_MIN,
            price_xdr.Price(-1, 1),
            INT64_MIN,
        ),
    ),
    "buy_max": operation(
        operation_xdr.OPERATION_TYPE_MANAGE_BUY_OFFER,
        operation_xdr.ManageBuyOfferOp(
            native(),
            native(),
            INT64_MAX,
            price_xdr.Price(1, 2),
            0,
        ),
    ),
}


def decode_operation(raw: bytes) -> xdr_codec.Operation:
    reader = xdr_codec.XdrReader(raw)
    decoded = xdr_codec._decode_operation(reader)
    reader.assert_eof()
    return decoded


def encode_operation(value: xdr_codec.Operation) -> bytes:
    writer = xdr_codec.XdrWriter()
    xdr_codec._encode_operation(writer, value)
    return writer.to_bytes()


class OfferOperationCodecTests(unittest.TestCase):
    def test_official_operation_vectors_preserve_fields_order_and_bytes(self) -> None:
        for name, encoded in OPERATION_ORACLES.items():
            with self.subTest(operation=name):
                raw = base64.b64decode(encoded, validate=True)
                expected = EXPECTED[name]
                decoded = decode_operation(raw)
                self.assertEqual(decoded, expected)
                self.assertEqual(raw[:4], b"\x00" * 4)
                self.assertEqual(raw[4:8], struct.pack(">i", expected.body.op_type))
                self.assertEqual(encode_operation(decoded), raw)

                reader = xdr_codec.XdrReader(raw)
                self.assertEqual(reader.read_int32(), 0)  # absent sourceAccount
                self.assertEqual(reader.read_int32(), expected.body.op_type)
                payload = expected.body.operation
                self.assertEqual(xdr_codec._decode_asset(reader), payload.selling)
                self.assertEqual(xdr_codec._decode_asset(reader), payload.buying)
                amount = payload.buy_amount if hasattr(payload, "buy_amount") else payload.amount
                self.assertEqual(reader.read_int64(), amount)
                price_offset = reader.pos
                self.assertEqual(price_xdr.decode_price(reader), payload.price)
                self.assertEqual(
                    raw[price_offset : price_offset + 8],
                    struct.pack(">ii", payload.price.n, payload.price.d),
                )
                if hasattr(payload, "offer_id"):
                    self.assertEqual(reader.read_int64(), payload.offer_id)
                reader.assert_eof()

    def test_official_v1_envelopes_roundtrip_exactly(self) -> None:
        for name, encoded in ENVELOPE_ORACLES.items():
            with self.subTest(envelope=name):
                raw = base64.b64decode(encoded, validate=True)
                envelope = xdr_codec.decode_transaction_envelope(raw)
                self.assertEqual(envelope.envelope_type, xdr_codec.ENVELOPE_TYPE_TX)
                self.assertEqual(len(envelope.v1.tx.operations), 1)
                self.assertEqual(envelope.v1.tx.operations[0], EXPECTED[name])
                self.assertEqual(xdr_codec.encode_transaction_envelope(envelope), raw)

    def test_malformed_tags_truncation_and_trailing_bytes_are_rejected(self) -> None:
        for name, encoded in OPERATION_ORACLES.items():
            raw = base64.b64decode(encoded, validate=True)
            with self.subTest(operation=name, malformed="operation tag"):
                bad = bytearray(raw)
                bad[4:8] = (99).to_bytes(4, "big")
                with self.assertRaisesRegex(xdr_codec.XdrCodecError, "OperationType arm"):
                    decode_operation(bytes(bad))
            with self.subTest(operation=name, malformed="selling Asset tag"):
                bad = bytearray(raw)
                bad[8:12] = (3).to_bytes(4, "big")
                with self.assertRaisesRegex(xdr_codec.XdrCodecError, "AssetType discriminant"):
                    decode_operation(bytes(bad))
            reader = xdr_codec.XdrReader(raw)
            reader.read_int32()
            reader.read_int32()
            xdr_codec._decode_asset(reader)
            with self.subTest(operation=name, malformed="buying Asset tag"):
                bad = bytearray(raw)
                bad[reader.pos : reader.pos + 4] = (3).to_bytes(4, "big")
                with self.assertRaisesRegex(xdr_codec.XdrCodecError, "AssetType discriminant"):
                    decode_operation(bytes(bad))
            for end in range(len(raw)):
                with self.subTest(operation=name, truncated_at=end):
                    with self.assertRaises(xdr_codec.XdrCodecError):
                        decode_operation(raw[:end])
            with self.subTest(operation=name, malformed="trailing byte"):
                with self.assertRaisesRegex(xdr_codec.XdrCodecError, "trailing bytes"):
                    decode_operation(raw + b"\x00")

    def test_wrong_operation_and_price_models_are_rejected(self) -> None:
        wrong = {
            operation_xdr.OPERATION_TYPE_MANAGE_SELL_OFFER: EXPECTED[
                "passive_boundary"
            ].body.operation,
            operation_xdr.OPERATION_TYPE_CREATE_PASSIVE_SELL_OFFER: EXPECTED[
                "buy_boundary"
            ].body.operation,
            operation_xdr.OPERATION_TYPE_MANAGE_BUY_OFFER: EXPECTED[
                "sell_boundary"
            ].body.operation,
        }
        for name in ENVELOPE_ORACLES:
            expected = EXPECTED[name]
            tag = expected.body.op_type
            with self.subTest(operation=name, field="operation model"):
                bad = replace(expected, body=replace(expected.body, operation=wrong[tag]))
                with self.assertRaisesRegex(xdr_codec.XdrCodecError, "required for OperationType"):
                    encode_operation(bad)
            for bad_price in (
                (1, 2),
                price_xdr.Price(INT32_MAX + 1, 1),
                price_xdr.Price(1, INT32_MIN - 1),
            ):
                with self.subTest(operation=name, price=bad_price):
                    payload = replace(expected.body.operation, price=bad_price)
                    bad = replace(expected, body=replace(expected.body, operation=payload))
                    with self.assertRaises(xdr_codec.XdrCodecError):
                        encode_operation(bad)

    def test_signed_amount_and_offer_id_bounds_are_enforced(self) -> None:
        for name in ENVELOPE_ORACLES:
            expected = EXPECTED[name]
            payload = expected.body.operation
            fields = ["buy_amount" if hasattr(payload, "buy_amount") else "amount"]
            if hasattr(payload, "offer_id"):
                fields.append("offer_id")
            for field in fields:
                for value in (INT64_MIN - 1, INT64_MAX + 1):
                    with self.subTest(operation=name, field=field, value=value):
                        bad_payload = replace(payload, **{field: value})
                        bad = replace(expected, body=replace(expected.body, operation=bad_payload))
                        with self.assertRaisesRegex(xdr_codec.XdrCodecError, "int64 range"):
                            encode_operation(bad)


if __name__ == "__main__":
    unittest.main()
