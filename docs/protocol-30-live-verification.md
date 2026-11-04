# Protocol 30 Testnet RPC evidence

The [November 4 Action run](https://github.com/StellarCanary/ProtocolCanary-Action/actions/runs/41810837579)
reported `protocolVersion = 30` on Testnet, while the pinned Protocol 29
fixture expected 29. The Futurenet Protocol 29 check passed in that run.
The [Bell upgrade guide](https://stellar.org/blog/developers/bell-protocol-30-upgrade-guide)
records the Testnet upgrade date.

This candidate uses `getVersionInfo` to check one Protocol 30 Testnet
version field. Its exact live request, response, UTC timestamp, host,
network identity and verification record must come from the existing
read-only tool, not from a mocked test or a manually invented record.

```bash
python3 tools/evidence/capture_live.py protocol-30 \
  --endpoint soroban-testnet.stellar.org \
  --output-dir protocol-30/evidence/live/testnet \
  --require-matched
python3 tools/validate/validate.py protocol-30 \
  --evidence protocol-30/evidence/live/testnet/records
```

The capture tool calls only approved read-only methods, checks the Testnet
network passphrase, and refuses mismatched results. A captured version
number is evidence only for that endpoint and timestamp. It is not
proof that Protocol 30's XDR and other features work.

Do not change or rewrite Protocol 29 evidence. A separate later PR will
update the network matrix and recurring Action integration.
