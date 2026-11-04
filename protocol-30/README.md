# Protocol 30 Testnet RPC fixture pack

This is an initial RPC network-version check for Stellar Testnet after the
November 3, 2026 Bell upgrade. It does not verify Protocol 30 XDR, Soroban,
transaction semantics or Mainnet. The existing Protocol 29 pack and its
historical evidence remain unchanged.

| Fixture | Surface | CAP | What it proves |
| --- | --- | --- | --- |
| [`p30-rpc-version-info-protocol-30`](rpc/p30-rpc-version-info-protocol-30.toml) | rpc | - | `getVersionInfo.protocolVersion` equals 30 |

Source: [Stellar RPC method documentation](https://developers.stellar.org/docs/data/apis/rpc/api-reference/methods/getVersionInfo).
Upgrade context: [Bell upgrade guide](https://stellar.org/blog/developers/bell-protocol-30-upgrade-guide).
The repository's read-only capture tool must create evidence under
`evidence/live/testnet/`. Without a passing fresh capture and its matched
verification record, do not claim this pack is verified.

The current pack-release selector supports only Protocol 28 and 29. This
initial fixture does **not** authorize a Protocol 30 release tag.
