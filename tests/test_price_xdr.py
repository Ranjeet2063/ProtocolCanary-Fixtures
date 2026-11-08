"""Protocol 28 Price codec against typed official stellar-xdr vectors."""

from __future__ import annotations

import base64
import struct
import unittest

from tests import price_xdr, xdr_codec

# Generated with official stellar-xdr = 28.0.1 using typed Price values,
# WriteXdr::to_xdr_base64(Limits::none()), and an official ReadXdr roundtrip.
# Pinned definition: stellar/stellar-xdr commit
# 9c9c145953e80990d6ff1ae3a6a973a0ce6d0694,
# Stellar-ledger-entries.x, struct Price { int32 n; int32 d; }.
# Construction expressions are listed beside the resulting base64 bytes.
ORACLE_VECTORS = {
    "positive": (price_xdr.Price(n=1, d=2), "AAAAAQAAAAI="),  # Price { n: 1, d: 2 }
    "negative_numerator": (
        price_xdr.Price(n=-7, d=3),
        "////+QAAAAM=",  # Price { n: -7, d: 3 }
    ),
    "negative_denominator": (
        price_xdr.Price(n=7, d=-3),
        "AAAAB/////0=",  # Price { n: 7, d: -3 }
    ),
    "zero_fields": (
        price_xdr.Price(n=0, d=0),
        "AAAAAAAAAAA=",  # Price { n: 0, d: 0 }
    ),
    "min_max": (
        price_xdr.Price(n=-(1 << 31), d=(1 << 31) - 1),
        "gAAAAH////8=",  # Price { n: i32::MIN, d: i32::MAX }
    ),
    "max_min": (
        price_xdr.Price(n=(1 << 31) - 1, d=-(1 << 31)),
        "f////4AAAAA=",  # Price { n: i32::MAX, d: i32::MIN }
    ),
}


class PriceCodecTests(unittest.TestCase):
    def test_typed_official_vectors_preserve_field_order_and_bytes(self) -> None:
        for name, (expected, encoded) in ORACLE_VECTORS.items():
            with self.subTest(price=name):
                raw = base64.b64decode(encoded, validate=True)
                self.assertEqual(len(raw), 8)
                self.assertEqual(raw[:4], struct.pack(">i", expected.n))
                self.assertEqual(raw[4:], struct.pack(">i", expected.d))
                self.assertEqual(price_xdr.decode_price_xdr(raw), expected)
                self.assertEqual(price_xdr.encode_price_xdr(expected), raw)
                self.assertEqual(price_xdr.encode_price_xdr(price_xdr.decode_price_xdr(raw)), raw)

    def test_composes_with_existing_reader_and_writer(self) -> None:
        price = price_xdr.Price(n=-7, d=3)
        writer = xdr_codec.XdrWriter()
        writer.write_int32(19)
        price_xdr.encode_price(writer, price)
        writer.write_uint32(42)
        reader = xdr_codec.XdrReader(writer.to_bytes())
        self.assertEqual(reader.read_int32(), 19)
        self.assertEqual(price_xdr.decode_price(reader), price)
        self.assertEqual(reader.read_uint32(), 42)
        reader.assert_eof()

    def test_out_of_range_values_and_wrong_models_are_rejected(self) -> None:
        for field in ("n", "d"):
            for value in (-(1 << 31) - 1, 1 << 31):
                with self.subTest(field=field, value=value):
                    fields = {"n": 1, "d": 2}
                    fields[field] = value
                    with self.assertRaisesRegex(price_xdr.PriceCodecError, "int32 range"):
                        price_xdr.encode_price_xdr(price_xdr.Price(**fields))
            for value in (True, 1.5, "1", None):
                with self.subTest(field=field, type=type(value).__name__):
                    fields = {"n": 1, "d": 2}
                    fields[field] = value
                    with self.assertRaisesRegex(price_xdr.PriceCodecError, "int32 integer"):
                        price_xdr.encode_price_xdr(price_xdr.Price(**fields))
        for wrong in (None, (1, 2), {"n": 1, "d": 2}):
            with self.subTest(model=type(wrong).__name__):
                with self.assertRaisesRegex(price_xdr.PriceCodecError, "Price model required"):
                    price_xdr.encode_price_xdr(wrong)

    def test_validation_precedes_writes_to_shared_writer(self) -> None:
        writer = xdr_codec.XdrWriter()
        writer.write_int32(19)
        original = writer.to_bytes()
        with self.assertRaises(price_xdr.PriceCodecError):
            price_xdr.encode_price(writer, price_xdr.Price(n=1, d=1 << 31))
        self.assertEqual(writer.to_bytes(), original)

    def test_truncation_and_trailing_bytes_are_rejected(self) -> None:
        raw = base64.b64decode(ORACLE_VECTORS["min_max"][1], validate=True)
        for end in range(len(raw)):
            with self.subTest(truncated_at=end):
                with self.assertRaisesRegex(xdr_codec.XdrCodecError, "truncated input"):
                    price_xdr.decode_price_xdr(raw[:end])
        for extra in (b"\x00", b"\x00\x00\x00\x00"):
            with self.subTest(trailing=len(extra)):
                with self.assertRaisesRegex(xdr_codec.XdrCodecError, "trailing bytes"):
                    price_xdr.decode_price_xdr(raw + extra)

    def test_standalone_decoder_requires_bytes(self) -> None:
        for wrong in (None, 0, "AAAAAAAAAAA=", bytearray(8)):
            with self.subTest(type=type(wrong).__name__):
                with self.assertRaisesRegex(price_xdr.PriceCodecError, "must be bytes"):
                    price_xdr.decode_price_xdr(wrong)


if __name__ == "__main__":
    unittest.main()
