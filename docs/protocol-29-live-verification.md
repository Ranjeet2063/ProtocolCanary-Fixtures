# Protocol 29 live verification

Protocol 29 uses a separate read-only scheduled workflow, leaving the
Protocol 28 schedule and evidence workflow unchanged:
[`.github/workflows/protocol29-live-evidence.yml`](../.github/workflows/protocol29-live-evidence.yml).
The workflow runs a Testnet and Futurenet matrix leg independently and uploads
each leg's raw captures, verification records and command log as an artifact.
It does not write to the repository.

## Endpoints and network identity

The allowlist in `tools/evidence/capture_live.py` contains only:

| Network | Host | URL | Required `getNetwork` passphrase |
|---|---|---|---|
| Testnet | `soroban-testnet.stellar.org` | `https://soroban-testnet.stellar.org` | `Test SDF Network ; September 2015` |
| Futurenet | `rpc-futurenet.stellar.org` | `https://rpc-futurenet.stellar.org` | `Test SDF Future Network ; October 2022` |

The endpoint URLs are the official Stellar SDK network defaults
([`stellar/js-stellar-sdk`](https://github.com/stellar/js-stellar-sdk)). The
passphrases are checked against the live `getNetwork` response and are also
specified by Stellar's official network setup
([`stellar/quickstart`](https://github.com/stellar/quickstart/blob/main/start)).
A response with a different passphrase is retained as a raw capture, but it
cannot create a verification record. No Mainnet hostname is in the allowlist.

## Executed checks and success criteria

The Protocol 29 pack currently has one RPC fixture. The capture tool maps its
`get-version-info` fixture method to the Engine-supported `getVersionInfo`
JSON-RPC method, calls `getNetwork` to identify the network, and captures
`getLatestLedger` as an additional read-only network observation. Only the
fixture's own `getVersionInfo` assertion counts as a fixture check. The
command prints separate executed, passed, failed and skipped fixture-check
counts.

Both workflow legs pass `--require-matched`. A leg fails if zero fixture
checks execute, any check fails, any fixture is skipped, any capture fails,
or any generated record fails evidence validation. A protocol mismatch is
preserved in the uploaded capture and record with `outcome: "mismatched"`;
it is not converted to success.

## Artifacts

Each successful network leg writes an evidence artifact with this layout:

```text
protocol-29/evidence/live/<network>/
├── captures/
│   ├── get-latest-ledger.json
│   ├── get-network.json
│   └── get-version-info.json
├── records/
│   └── p29-rpc-version-info-protocol-29.live-read-only.json
└── run/
    ├── capture.log
    └── exit-code.txt
```

`exit-code.txt` is the actual process exit code. On a failed capture, the
artifact includes any responses actually captured and the command log; no
record is created for a call that did not produce a valid JSON-RPC result.
A live verification record links to the `getVersionInfo` capture, records the
capture timestamp, endpoint host, observed passphrase and protocol version,
fixture SHA-256, verifier commit and evidence reference.

The schedule is weekly on Monday at 07:42 UTC and can also be run manually.
The workflow has read-only repository permissions and publishes no release.
