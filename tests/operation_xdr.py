"""Independent XDR payload codecs for selected Stellar ``OperationBody`` arms.

Definitions follow ``stellar/stellar-xdr`` v28.0 at commit
``9c9c145953e80990d6ff1ae3a6a973a0ce6d0694``, principally
``Stellar-transaction.x``. This module handles XDR structure only. It does not
check transaction validity, authorization, ledger state, or host execution.

The operation dispatch in :mod:`tests.xdr_codec` supplies its existing codecs
for AccountID, MuxedAccount, and Asset. ClaimableBalanceID and ExtensionPoint
unions used here are decoded locally; ManageData pointers and bounded Asset
paths are handled in this module. Keeping operation payloads here avoids
mixing them into the reserved LedgerEntry decoder.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class OperationCodecError(ValueError):
    """Raised for unsupported or malformed OperationBody payloads."""


# OperationType values from the pinned Protocol 28 XDR definition.
OPERATION_TYPE_CREATE_ACCOUNT = 0
OPERATION_TYPE_PATH_PAYMENT_STRICT_RECEIVE = 2
OPERATION_TYPE_ACCOUNT_MERGE = 8
OPERATION_TYPE_INFLATION = 9
OPERATION_TYPE_MANAGE_DATA = 10
OPERATION_TYPE_BUMP_SEQUENCE = 11
OPERATION_TYPE_PATH_PAYMENT_STRICT_SEND = 13
OPERATION_TYPE_CLAIM_CLAIMABLE_BALANCE = 15
OPERATION_TYPE_BEGIN_SPONSORING_FUTURE_RESERVES = 16
OPERATION_TYPE_END_SPONSORING_FUTURE_RESERVES = 17
OPERATION_TYPE_CLAWBACK = 19
OPERATION_TYPE_CLAWBACK_CLAIMABLE_BALANCE = 20
OPERATION_TYPE_EXTEND_FOOTPRINT_TTL = 25
OPERATION_TYPE_RESTORE_FOOTPRINT = 26

EXTENSION_POINT_V0 = 0
MAX_ASSET_PATH_LENGTH = 5
MAX_DATA_NAME_LENGTH = 64
MAX_DATA_VALUE_LENGTH = 64
_INT64_MIN = -(1 << 63)
_INT64_MAX = (1 << 63) - 1
_UINT32_MAX = (1 << 32) - 1


@dataclass(frozen=True)
class CreateAccountOp:
    destination: Any  # AccountID, decoded by the shared PublicKey codec
    starting_balance: int  # int64


@dataclass(frozen=True)
class PathPaymentStrictReceiveOp:
    send_asset: Any
    send_max: int  # int64
    destination: Any  # MuxedAccount
    dest_asset: Any
    dest_amount: int  # int64
    path: list[Any]  # Asset<5>


@dataclass(frozen=True)
class AccountMergeOp:
    destination: Any  # MuxedAccount, decoded by the shared account codec


@dataclass(frozen=True)
class InflationOp:
    """The Protocol 28 INFLATION arm has no payload fields."""


@dataclass(frozen=True)
class ManageDataOp:
    data_name: str  # string64
    data_value: bytes | None  # DataValue*; opaque<64>


@dataclass(frozen=True)
class BumpSequenceOp:
    bump_to: int  # SequenceNumber, XDR int64


@dataclass(frozen=True)
class PathPaymentStrictSendOp:
    send_asset: Any
    send_amount: int  # int64
    destination: Any  # MuxedAccount
    dest_asset: Any
    dest_min: int  # int64
    path: list[Any]  # Asset<5>


@dataclass(frozen=True)
class ClaimableBalanceID:
    id_type: int  # ClaimableBalanceIDType; V0 only
    v0: bytes  # Hash, exactly 32 bytes


@dataclass(frozen=True)
class ClaimClaimableBalanceOp:
    balance_id: ClaimableBalanceID


@dataclass(frozen=True)
class BeginSponsoringFutureReservesOp:
    sponsored_id: Any  # AccountID, decoded by the shared PublicKey codec


@dataclass(frozen=True)
class EndSponsoringFutureReservesOp:
    """The Protocol 28 END_SPONSORING_FUTURE_RESERVES arm is void."""


@dataclass(frozen=True)
class ClawbackOp:
    asset: Any
    from_account: Any  # MuxedAccount; XDR field name is ``from``
    amount: int  # int64


@dataclass(frozen=True)
class ClawbackClaimableBalanceOp:
    balance_id: ClaimableBalanceID


@dataclass(frozen=True)
class ExtendFootprintTTLOp:
    extension_type: int  # ExtensionPoint union discriminant; V0 only
    extend_to: int  # uint32


@dataclass(frozen=True)
class RestoreFootprintOp:
    extension_type: int  # ExtensionPoint union discriminant; V0 only


_SUPPORTED_OPERATION_TYPES = frozenset(
    {
        OPERATION_TYPE_CREATE_ACCOUNT,
        OPERATION_TYPE_PATH_PAYMENT_STRICT_RECEIVE,
        OPERATION_TYPE_ACCOUNT_MERGE,
        OPERATION_TYPE_INFLATION,
        OPERATION_TYPE_MANAGE_DATA,
        OPERATION_TYPE_BUMP_SEQUENCE,
        OPERATION_TYPE_PATH_PAYMENT_STRICT_SEND,
        OPERATION_TYPE_CLAIM_CLAIMABLE_BALANCE,
        OPERATION_TYPE_BEGIN_SPONSORING_FUTURE_RESERVES,
        OPERATION_TYPE_END_SPONSORING_FUTURE_RESERVES,
        OPERATION_TYPE_CLAWBACK,
        OPERATION_TYPE_CLAWBACK_CLAIMABLE_BALANCE,
        OPERATION_TYPE_EXTEND_FOOTPRINT_TTL,
        OPERATION_TYPE_RESTORE_FOOTPRINT,
    }
)


def supports_operation_type(operation_type: int) -> bool:
    """Return whether this module implements the complete selected arm."""
    return operation_type in _SUPPORTED_OPERATION_TYPES


def _read_extension_point(reader: Any) -> int:
    extension_type = reader.read_int32()
    if extension_type != EXTENSION_POINT_V0:
        raise OperationCodecError(f"unknown ExtensionPoint discriminant: {extension_type}")
    return extension_type


def _write_extension_point(writer: Any, extension_type: int) -> None:
    if extension_type != EXTENSION_POINT_V0:
        raise OperationCodecError(f"unknown ExtensionPoint discriminant: {extension_type}")
    writer.write_int32(extension_type)


def _decode_claimable_balance_id(reader: Any) -> ClaimableBalanceID:
    id_type = reader.read_int32()
    if id_type != 0:
        raise OperationCodecError(f"unknown ClaimableBalanceIDType discriminant: {id_type}")
    return ClaimableBalanceID(id_type=id_type, v0=reader.read_fixed_opaque(32))


def _encode_claimable_balance_id(writer: Any, balance_id: ClaimableBalanceID) -> None:
    if not isinstance(balance_id, ClaimableBalanceID):
        raise OperationCodecError("ClaimableBalanceID required for this operation")
    if balance_id.id_type != 0:
        raise OperationCodecError(
            f"unknown ClaimableBalanceIDType discriminant: {balance_id.id_type}"
        )
    if len(balance_id.v0) != 32:
        raise OperationCodecError("ClaimableBalanceID v0 hash must be 32 bytes")
    writer.write_int32(balance_id.id_type)
    writer.write_fixed_opaque(balance_id.v0)


def _decode_asset_path(reader: Any, decode_asset: Callable[[Any], Any]) -> list[Any]:
    length = reader.read_uint32()
    if length > MAX_ASSET_PATH_LENGTH:
        raise OperationCodecError(
            f"Asset path length {length} exceeds maximum {MAX_ASSET_PATH_LENGTH}"
        )
    return [decode_asset(reader) for _ in range(length)]


def _encode_asset_path(
    writer: Any, path: list[Any], encode_asset: Callable[[Any, Any], None]
) -> None:
    if not isinstance(path, (list, tuple)):
        raise OperationCodecError("Asset path must be a list or tuple")
    if len(path) > MAX_ASSET_PATH_LENGTH:
        raise OperationCodecError(
            f"Asset path length {len(path)} exceeds maximum {MAX_ASSET_PATH_LENGTH}"
        )
    writer.write_uint32(len(path))
    for asset in path:
        encode_asset(writer, asset)


def _decode_manage_data(reader: Any) -> ManageDataOp:
    data_name = reader.read_string(max_length=MAX_DATA_NAME_LENGTH)
    pointer = reader.read_int32()
    if pointer == 0:
        data_value = None
    elif pointer == 1:
        data_value = reader.read_var_opaque(max_length=MAX_DATA_VALUE_LENGTH)
    else:
        raise OperationCodecError(
            f"invalid ManageDataOp.dataValue pointer discriminant: {pointer}"
        )
    return ManageDataOp(data_name=data_name, data_value=data_value)


def _encode_manage_data(writer: Any, value: ManageDataOp) -> None:
    writer.write_string(value.data_name, max_length=MAX_DATA_NAME_LENGTH)
    if value.data_value is None:
        writer.write_int32(0)
    else:
        if not isinstance(value.data_value, bytes):
            raise OperationCodecError("ManageDataOp.dataValue must be bytes or None")
        if len(value.data_value) > MAX_DATA_VALUE_LENGTH:
            raise OperationCodecError(
                f"ManageDataOp.dataValue length {len(value.data_value)} exceeds maximum "
                f"{MAX_DATA_VALUE_LENGTH}"
            )
        writer.write_int32(1)
        writer.write_var_opaque(value.data_value, max_length=MAX_DATA_VALUE_LENGTH)


def decode_operation_body(
    reader: Any,
    operation_type: int,
    *,
    decode_account_id: Callable[[Any], Any],
    decode_muxed_account: Callable[[Any], Any],
    decode_asset: Callable[[Any], Any],
) -> Any:
    """Decode a selected OperationBody arm after its discriminant was read."""
    if operation_type == OPERATION_TYPE_CREATE_ACCOUNT:
        return CreateAccountOp(
            destination=decode_account_id(reader), starting_balance=reader.read_int64()
        )
    if operation_type == OPERATION_TYPE_PATH_PAYMENT_STRICT_RECEIVE:
        return PathPaymentStrictReceiveOp(
            send_asset=decode_asset(reader),
            send_max=reader.read_int64(),
            destination=decode_muxed_account(reader),
            dest_asset=decode_asset(reader),
            dest_amount=reader.read_int64(),
            path=_decode_asset_path(reader, decode_asset),
        )
    if operation_type == OPERATION_TYPE_ACCOUNT_MERGE:
        return AccountMergeOp(destination=decode_muxed_account(reader))
    if operation_type == OPERATION_TYPE_INFLATION:
        return InflationOp()
    if operation_type == OPERATION_TYPE_MANAGE_DATA:
        return _decode_manage_data(reader)
    if operation_type == OPERATION_TYPE_BUMP_SEQUENCE:
        return BumpSequenceOp(bump_to=reader.read_int64())
    if operation_type == OPERATION_TYPE_PATH_PAYMENT_STRICT_SEND:
        return PathPaymentStrictSendOp(
            send_asset=decode_asset(reader),
            send_amount=reader.read_int64(),
            destination=decode_muxed_account(reader),
            dest_asset=decode_asset(reader),
            dest_min=reader.read_int64(),
            path=_decode_asset_path(reader, decode_asset),
        )
    if operation_type == OPERATION_TYPE_CLAIM_CLAIMABLE_BALANCE:
        return ClaimClaimableBalanceOp(balance_id=_decode_claimable_balance_id(reader))
    if operation_type == OPERATION_TYPE_BEGIN_SPONSORING_FUTURE_RESERVES:
        return BeginSponsoringFutureReservesOp(sponsored_id=decode_account_id(reader))
    if operation_type == OPERATION_TYPE_END_SPONSORING_FUTURE_RESERVES:
        return EndSponsoringFutureReservesOp()
    if operation_type == OPERATION_TYPE_CLAWBACK:
        return ClawbackOp(
            asset=decode_asset(reader),
            from_account=decode_muxed_account(reader),
            amount=reader.read_int64(),
        )
    if operation_type == OPERATION_TYPE_CLAWBACK_CLAIMABLE_BALANCE:
        return ClawbackClaimableBalanceOp(balance_id=_decode_claimable_balance_id(reader))
    if operation_type == OPERATION_TYPE_EXTEND_FOOTPRINT_TTL:
        return ExtendFootprintTTLOp(
            extension_type=_read_extension_point(reader),
            extend_to=reader.read_uint32(),
        )
    if operation_type == OPERATION_TYPE_RESTORE_FOOTPRINT:
        return RestoreFootprintOp(extension_type=_read_extension_point(reader))
    raise OperationCodecError(
        f"unsupported OperationType arm: {operation_type} is not implemented by the "
        "independent codec"
    )


def _require_payload(operation_type: int, payload: Any, expected_type: type) -> Any:
    if not isinstance(payload, expected_type):
        raise OperationCodecError(
            f"{expected_type.__name__} required for OperationType {operation_type}"
        )
    return payload


def _write_int64(writer: Any, value: int, field_name: str) -> None:
    if not _INT64_MIN <= value <= _INT64_MAX:
        raise OperationCodecError(f"{field_name} is outside the XDR int64 range")
    writer.write_int64(value)


def _write_uint32(writer: Any, value: int, field_name: str) -> None:
    if not 0 <= value <= _UINT32_MAX:
        raise OperationCodecError(f"{field_name} is outside the XDR uint32 range")
    writer.write_uint32(value)


def encode_operation_body(
    writer: Any,
    operation_type: int,
    payload: Any,
    *,
    encode_account_id: Callable[[Any, Any], None],
    encode_muxed_account: Callable[[Any, Any], None],
    encode_asset: Callable[[Any, Any], None],
) -> None:
    """Encode a selected OperationBody arm; the caller writes its discriminant."""
    if operation_type == OPERATION_TYPE_CREATE_ACCOUNT:
        value = _require_payload(operation_type, payload, CreateAccountOp)
        encode_account_id(writer, value.destination)
        _write_int64(writer, value.starting_balance, "CreateAccountOp.startingBalance")
        return
    if operation_type == OPERATION_TYPE_PATH_PAYMENT_STRICT_RECEIVE:
        value = _require_payload(operation_type, payload, PathPaymentStrictReceiveOp)
        encode_asset(writer, value.send_asset)
        _write_int64(writer, value.send_max, "PathPaymentStrictReceiveOp.sendMax")
        encode_muxed_account(writer, value.destination)
        encode_asset(writer, value.dest_asset)
        _write_int64(writer, value.dest_amount, "PathPaymentStrictReceiveOp.destAmount")
        _encode_asset_path(writer, value.path, encode_asset)
        return
    if operation_type == OPERATION_TYPE_ACCOUNT_MERGE:
        value = _require_payload(operation_type, payload, AccountMergeOp)
        encode_muxed_account(writer, value.destination)
        return
    if operation_type == OPERATION_TYPE_INFLATION:
        _require_payload(operation_type, payload, InflationOp)
        return
    if operation_type == OPERATION_TYPE_MANAGE_DATA:
        value = _require_payload(operation_type, payload, ManageDataOp)
        _encode_manage_data(writer, value)
        return
    if operation_type == OPERATION_TYPE_BUMP_SEQUENCE:
        value = _require_payload(operation_type, payload, BumpSequenceOp)
        _write_int64(writer, value.bump_to, "BumpSequenceOp.bumpTo")
        return
    if operation_type == OPERATION_TYPE_PATH_PAYMENT_STRICT_SEND:
        value = _require_payload(operation_type, payload, PathPaymentStrictSendOp)
        encode_asset(writer, value.send_asset)
        _write_int64(writer, value.send_amount, "PathPaymentStrictSendOp.sendAmount")
        encode_muxed_account(writer, value.destination)
        encode_asset(writer, value.dest_asset)
        _write_int64(writer, value.dest_min, "PathPaymentStrictSendOp.destMin")
        _encode_asset_path(writer, value.path, encode_asset)
        return
    if operation_type == OPERATION_TYPE_CLAIM_CLAIMABLE_BALANCE:
        value = _require_payload(operation_type, payload, ClaimClaimableBalanceOp)
        _encode_claimable_balance_id(writer, value.balance_id)
        return
    if operation_type == OPERATION_TYPE_BEGIN_SPONSORING_FUTURE_RESERVES:
        value = _require_payload(operation_type, payload, BeginSponsoringFutureReservesOp)
        encode_account_id(writer, value.sponsored_id)
        return
    if operation_type == OPERATION_TYPE_END_SPONSORING_FUTURE_RESERVES:
        _require_payload(operation_type, payload, EndSponsoringFutureReservesOp)
        return
    if operation_type == OPERATION_TYPE_CLAWBACK:
        value = _require_payload(operation_type, payload, ClawbackOp)
        encode_asset(writer, value.asset)
        encode_muxed_account(writer, value.from_account)
        _write_int64(writer, value.amount, "ClawbackOp.amount")
        return
    if operation_type == OPERATION_TYPE_CLAWBACK_CLAIMABLE_BALANCE:
        value = _require_payload(operation_type, payload, ClawbackClaimableBalanceOp)
        _encode_claimable_balance_id(writer, value.balance_id)
        return
    if operation_type == OPERATION_TYPE_EXTEND_FOOTPRINT_TTL:
        value = _require_payload(operation_type, payload, ExtendFootprintTTLOp)
        _write_extension_point(writer, value.extension_type)
        _write_uint32(writer, value.extend_to, "ExtendFootprintTTLOp.extendTo")
        return
    if operation_type == OPERATION_TYPE_RESTORE_FOOTPRINT:
        value = _require_payload(operation_type, payload, RestoreFootprintOp)
        _write_extension_point(writer, value.extension_type)
        return
    raise OperationCodecError(
        f"unsupported OperationType arm: {operation_type} is not implemented by the "
        "independent codec"
    )
