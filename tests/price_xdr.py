"""Structural codec for the Protocol 28 XDR ``Price`` value.

The pinned definition is ``Stellar-ledger-entries.x`` at stellar/stellar-xdr
commit 9c9c145953e80990d6ff1ae3a6a973a0ce6d0694: signed int32 ``n``
followed by signed int32 ``d``. XDR structure does not establish that a price
is suitable for an offer or accepted by a ledger.

The reader and writer entry points accept the existing XDR primitives. The
standalone helpers import those primitives lazily so operation payload codecs
can import this module without a cycle through ``tests.xdr_codec``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_INT32_MIN = -(1 << 31)
_INT32_MAX = (1 << 31) - 1


class PriceCodecError(ValueError):
    """Raised for an invalid Price model or signed int32 field."""


@dataclass(frozen=True)
class Price:
    n: int
    d: int


def decode_price(reader: Any) -> Price:
    """Read Price from a larger XDR stream, consuming exactly eight bytes."""
    return Price(n=reader.read_int32(), d=reader.read_int32())


def encode_price(writer: Any, price: Price) -> None:
    """Append Price to a larger XDR stream after checking both fields."""
    if not isinstance(price, Price):
        raise PriceCodecError("Price model required")
    for name, value in (("n", price.n), ("d", price.d)):
        if type(value) is not int:
            raise PriceCodecError(f"Price.{name} must be a signed int32 integer")
        if not _INT32_MIN <= value <= _INT32_MAX:
            raise PriceCodecError(f"Price.{name} is outside the XDR int32 range")
    writer.write_int32(price.n)
    writer.write_int32(price.d)


def decode_price_xdr(data: bytes) -> Price:
    """Decode a standalone Price, rejecting truncated or trailing bytes."""
    if not isinstance(data, bytes):
        raise PriceCodecError("Price XDR input must be bytes")
    from .xdr_codec import XdrReader

    reader = XdrReader(data)
    price = decode_price(reader)
    reader.assert_eof()
    return price


def encode_price_xdr(price: Price) -> bytes:
    """Encode a standalone Price using the repository's XDR writer."""
    from .xdr_codec import XdrWriter

    writer = XdrWriter()
    encode_price(writer, price)
    return writer.to_bytes()
