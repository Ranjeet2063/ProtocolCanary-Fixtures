# Protocol 30 fixture pack

This pack has two separate kinds of evidence: offline structural XDR vectors
for selected CAP-84 and CAP-88 types, and one live Testnet RPC identity check.
The offline vectors are synthetic, deterministic byte encodings. They do not
come from a network capture and do not establish consensus validity or live
protocol behavior. The live fixture verifies only the observed RPC protocol
identity at the captured Testnet endpoint and time.

Together these fixtures do not establish complete Protocol 30 compatibility.
They do not verify CAP-84 host behavior, CAP-88 consensus signatures or ledger
semantics, Soroban execution, RPC behavior beyond the identity field, or
Mainnet. The existing Protocol 29 pack and its historical evidence remain
unchanged.

| Fixture | Surface | CAP | What it proves |
| --- | --- | --- | --- |
| [`p30-rpc-version-info-protocol-30`](rpc/p30-rpc-version-info-protocol-30.toml) | rpc | - | `getVersionInfo.protocolVersion` equals 30 |
| [`p30-xdr-cap0084-muxed-contract-address-roundtrip`](xdr/cap-0084/p30-xdr-cap0084-muxed-contract-address-roundtrip.toml) | xdr | cap-0084 | A `ScVal` containing `SC_ADDRESS_TYPE_MUXED_CONTRACT` round-trips with the CAP-84 `id` and `contractId` fields |
| [`p30-xdr-cap0088-stellar-value-signed-ms-roundtrip`](xdr/cap-0088/p30-xdr-cap0088-stellar-value-signed-ms-roundtrip.toml) | xdr | cap-0088 | `STELLAR_VALUE_SIGNED_MS` decodes with `closeTimeMs` and the signature structure |
| [`p30-xdr-cap0088-stellar-value-empty-tx-set-ms-roundtrip`](xdr/cap-0088/p30-xdr-cap0088-stellar-value-empty-tx-set-ms-roundtrip.toml) | xdr | cap-0088 | `STELLAR_VALUE_EMPTY_TX_SET_MS` decodes with `closeTimeMs`, proposed hashes and previous ledger version |

The RPC method is defined in the [Stellar RPC documentation](https://developers.stellar.org/docs/data/apis/rpc/api-reference/methods/getVersionInfo).
Protocol definitions: [CAP-84](https://github.com/stellar/stellar-protocol/blob/1ae39233055a0fb94bb737650a39ede8d77d924c/core/cap-0084.md) and [CAP-88](https://github.com/stellar/stellar-protocol/blob/1ae39233055a0fb94bb737650a39ede8d77d924c/core/cap-0088.md). The tagged `stellar-xdr` v30.0.0 definitions used to verify the XDR layout are [ScAddress](https://github.com/stellar/rs-stellar-xdr/blob/v30.0.0/src/generated/sc_address.rs), [MuxedContract](https://github.com/stellar/rs-stellar-xdr/blob/v30.0.0/src/generated/muxed_contract.rs), [StellarValueExt](https://github.com/stellar/rs-stellar-xdr/blob/v30.0.0/src/generated/stellar_value_ext.rs) and [StellarValueType](https://raw.githubusercontent.com/stellar/rs-stellar-xdr/v30.0.0/src/generated/stellar_value_type.rs).

The offline XDR vectors are checked by the repository's independent Python
codecs and compared with fixed expected fields in the tests. Their sentinel
hashes, node ID and signature are not cryptographically verified and are not
claims about a real ledger object.

The corresponding structural CF-04 records only state that the fixture files
pass repository validation. They do not claim that an XDR payload was accepted
by a Stellar node or that a consensus signature is valid. The release gate
continues to require fresh live Testnet identity evidence for the RPC fixture.

The table above lists representative fixtures, not the complete pack. Each
independent fixture contribution has its own file and focused test; adding one
does not require changing this README or a central fixture-count assertion.

The repository's read-only capture tool must create evidence under
`evidence/live/testnet/`. Without a passing fresh capture and its matched
verification record, do not claim the live fixture pack is verified.

The release selector supports a Protocol 30 scoped tag only when the
Testnet-only verified evidence gate passes. Live evidence still proves only
RPC protocol identity. A release requires a separately reviewed tag,
protected tag ruleset, archive verification and provenance attestation.
