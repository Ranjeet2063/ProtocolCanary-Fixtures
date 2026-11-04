# Fixture Pack Release Procedure

This document describes the end-to-end procedure for packaging, verifying,
attesting, and publishing deterministic fixture pack releases for
`ProtocolCanary-Fixtures`.

Consumers, including GitHub Actions and integration workflows across the
Stellar ecosystem, rely on release archives being byte-reproducible,
cryptographically attested, and consistently tagged.

---

## 1. Overview and Automation Boundary

The release procedure separates tag validation and attestation from GitHub
Release asset publication:

- **Manual steps (maintainer):**
  1. Complete pre-release quality and consistency checks.
  2. Select the protocol pack and release version (Semantic Versioning `MAJOR.MINOR.PATCH`).
  3. Update `CHANGELOG.md` with the release version and UTC date.
  4. Ensure the candidate commit is on protected `main`, then create and push
     its protocol-scoped tag: `fixtures-p28-vX.Y.Z`, `fixtures-p29-vX.Y.Z`, or `fixtures-p30-vX.Y.Z`.
  5. After the tag workflow succeeds, publish a GitHub Release for that exact
     tag when ready to distribute the assets.
- **Tag-push automation (`.github/workflows/release-pack.yml`):** selects the
  pack from the scoped tag, checks that the tag ref and commit agree and that
  the commit is in `origin/main` history, builds twice, verifies the archive,
  creates the manifest and checksum, then attests the archive and manifest.
  A tag push does not publish GitHub Release assets.
- **Manual dispatch:** builds and verifies a candidate only. It receives no
  write permissions and does not attest or publish.
- **Release-published automation:** independently validates the exact release
  tag and main-history commit, rebuilds and re-verifies the candidate, then a
  separate narrowly permissioned job uploads the three assets to that release.
  This event does not create a tag or a GitHub Release.

---

## 2. Pre-Release Checks

Before creating a release tag, run all validation and test suites against a clean
working tree on the `main` branch:

### Step 2.1: Structural fixture validation
Verify schema conformance, unique IDs, source references, and payload references:

```bash
python3 tools/validate/validate.py
```

Expected output:
```
OK: 95 fixture file(s) valid across 4 root(s)
```

### Step 2.2: Fixtures count badge freshness
Confirm the README badge matches the fixture inventory:

```bash
python3 tools/badge/badge.py --check
```

Expected output:
```
OK: README.md fixtures badge is current (95 fixture file(s))
```

### Step 2.3: Repository test suite
Run all unit tests across the repository:

```bash
python3 -m unittest discover tests -v
```

Expected output:
```
OK
```

### Step 2.4: Registry freshness
Verify that committed registries match what `tools/registry/generate.py` generates.
For non-empty packs (such as `protocol-28`):

```bash
python3 tools/registry/generate.py protocol-28 --stdout
```

An empty pack cannot be promoted as verified. Do not generate a release registry
for an empty baseline. Protocol 29 must have non-empty, sourced fixture coverage
before a verified release can be built:

```bash
python3 tools/registry/generate.py protocol-29 --stdout
```

### Step 2.5: Protocol 29 live coverage

Before selecting Protocol 29 for a release, require a current matched
`live-read-only` record and linked raw capture for every fixture on both Testnet
and Futurenet. Records must identify the actual network, endpoint host, UTC
observation time, observed protocol 29, fixture SHA-256 and evidence reference.
The release packer enforces both networks and the 30-day live-evidence freshness
window; structural records and records under `history/` do not satisfy it.
Protocol 28 releases keep their existing unverified packing behavior.

### Step 2.6: Protocol 30 Testnet evidence gate

Protocol 30 releases must have a fresh, matched, read-only verification
record linked to two coherent raw Testnet captures (`getVersionInfo`
and `getNetwork`). The release gate requires the correct Testnet
passphrase, Protocol 30, endpoint host, fixture hash, UTC observation
times and the exact supported identity assertion. Evidence must be
no more than 30 days old. This is **RPC identity only**, not XDR,
Soroban, Mainnet or Futurenet Protocol 30 verification.

### Step 2.7: CHANGELOG and version selection
1. Choose an exact version string following `MAJOR.MINOR.PATCH` (e.g. `0.1.0`).
2. Update the `## [Unreleased]` section in [`CHANGELOG.md`](../CHANGELOG.md) by
   creating a new heading for the version with the current UTC date in
   `YYYY-MM-DD` format (for example, `## [0.1.0] - YYYY-MM-DD`).
3. Commit the changelog change and ensure the branch is merged into `main`.

---

## 3. Local Build and Verification

Maintainers may run the packaging and verification tools locally to inspect the
resulting artifacts before tagging:

### Step 3.1: Build the deterministic pack archive
Run `tools/pack/pack.py`:

```bash
python3 tools/pack/pack.py protocol-28 --version 0.1.0 --output-dir dist
```

For a Protocol 29 candidate, include `--verified`; this fails closed unless
every fixture has current live evidence on both Testnet and Futurenet:

```bash
python3 tools/pack/pack.py protocol-29 --version 0.1.0 --output-dir dist --verified
```

For Protocol 30, the same `--verified` release option requires fresh
Testnet-only evidence (it does not require Protocol 30 Futurenet):

```bash
python3 tools/pack/pack.py protocol-30 --version 0.1.0 --output-dir dist --verified
```

Expected output:
```
OK: wrote dist/protocolcanary-fixtures-0.1.0.tar.gz
sha256   25db2c1e3cdeeba302cf4dcc3d0c28d3b3728ae0260d990dcba51bcd13b81e92
bytes    44774
entries  106
digest   sha256:7bfce5afab4874b3e1622ef313dc4c398193d037d80fda306129677e556f1750
```

### Step 3.2: Verify the archive contents
Run `tools/pack/verify_archive.py`:

```bash
python3 tools/pack/verify_archive.py dist/protocolcanary-fixtures-0.1.0.tar.gz
```

Expected output:
```
OK: protocolcanary-fixtures-0.1.0.tar.gz: 93 fixture(s), 93 file(s) valid; registry and pack digest match
```

### Step 3.3: Generate the release manifest
Run `tools/release/manifest.py` with the 40-character commit SHA:

```bash
python3 tools/release/manifest.py dist/protocolcanary-fixtures-0.1.0.tar.gz \
  --revision $(git rev-parse HEAD) \
  --output dist/protocolcanary-fixtures-0.1.0.manifest.json \
  --sha256-file dist/protocolcanary-fixtures-0.1.0.sha256
```

Expected output:
```
OK: wrote dist/protocolcanary-fixtures-0.1.0.manifest.json
```

### Step 3.4: Verify archive against manifest and checksum
Verify that the archive matches the generated manifest:

```bash
python3 tools/pack/verify_archive.py dist/protocolcanary-fixtures-0.1.0.tar.gz \
  --manifest dist/protocolcanary-fixtures-0.1.0.manifest.json
```

Expected output:
```
OK: protocolcanary-fixtures-0.1.0.tar.gz: 93 fixture(s), 93 file(s) valid; registry and pack digest match
```

Verify the checksum file:

```bash
(cd dist && sha256sum -c protocolcanary-fixtures-0.1.0.sha256)
```

Expected output:
```
protocolcanary-fixtures-0.1.0.tar.gz: OK
```

---

## 4. Tag Naming Rules and Required Repository Protection

### Tag naming convention
Releases are selected with an explicit protocol in the tag:
- Protocol 28: `fixtures-p28-v<MAJOR>.<MINOR>.<PATCH>`
- Protocol 29: `fixtures-p29-v<MAJOR>.<MINOR>.<PATCH>`
- Protocol 30: `fixtures-p30-v<MAJOR>.<MINOR>.<PATCH>`

For example, `fixtures-p28-v0.1.0` selects only `protocol-28`, and
`fixtures-p29-v0.1.0` selects only `protocol-29`. Unscoped tags such as
`v0.1.0`, `fixtures-v0.1.0` and `protocol-29` are rejected by the release
selector; they never default to Protocol 28. The manual workflow dispatch
requires both a protocol choice and a semantic version and only builds the
candidate. It does not attest or publish assets.

### Required tag ruleset
A GitHub repository tag ruleset is required for release tags (`fixtures-p28-v*`,
`fixtures-p29-v*`, and `fixtures-p30-v*`). Configure it to restrict tag creation to authorized
maintainers and block tag updates and deletion. Protect `main` with the
repository's normal review and status-check rules.

The workflow also checks that a tag event's exact ref and commit match and that
the tagged commit is an ancestor of `origin/main`. This is defense in depth; a
workflow check alone does not protect against untrusted tag content, because a
tag can select the workflow file and scripts that are run. The GitHub tag
ruleset restricting creation, updates and deletion is therefore required, not
optional. Do not claim release safety from the workflow check alone.

Downstream consumers, reproducibility proofs, and attestations bind to the tag
and commit. Never move or delete a published tag; any correction requires a
new, incremented version tag.

---

## 5. Publishing the Release

Once pre-release checks pass and the candidate commit is on protected `main`,
create and push the protocol-scoped tag. For a Protocol 29 release:

```bash
git tag -a fixtures-p29-v0.1.0 -m "Protocol 29 fixture pack 0.1.0"
git push upstream fixtures-p29-v0.1.0
```

Use `fixtures-p28-v0.1.0` for Protocol 28 or `fixtures-p30-v0.1.0`
for Protocol 30, after confirming the Protocol 30 tag ruleset. A successful tag-push workflow
builds and attests the archive and manifest, but does not upload release assets.
After reviewing its result, create and publish a GitHub Release using that same
scoped tag. The `release.published` workflow event rebuilds and verifies the
candidate; only its `publish` job has `contents: write` and uploads exactly
these three assets to the matching GitHub Release:

1. `protocolcanary-fixtures-<version>.tar.gz`
2. `protocolcanary-fixtures-<version>.manifest.json`
3. `protocolcanary-fixtures-<version>.sha256`

GitHub build-provenance attestations are generated on the tag-push workflow for
the archive and manifest. Release uploads do not replace existing assets; a
duplicate asset name fails. Manual dispatches receive no write permissions and
cannot attest or publish.

On tag push, `.github/workflows/release-pack.yml` builds twice in independent
directories (`/tmp/build1` and `/tmp/build2`), checks bit-for-bit identity,
verifies the archive and its manifest/checksum, and attests the archive and
manifest. On release publication, it revalidates the exact tag/ref and commit,
rebuilds and re-verifies the assets, then uploads them to that tag's release.

---

## 6. Post-Release Verification

After the release workflow completes, verify the published assets directly from GitHub:

### Step 6.1: Check SHA-256 checksums
Download `protocolcanary-fixtures-<version>.tar.gz` and
`protocolcanary-fixtures-<version>.sha256`, then verify:

```bash
sha256sum -c protocolcanary-fixtures-0.1.0.sha256
```

### Step 6.2: Verify archive and manifest integrity
Verify that the archive contents conform to the manifest:

```bash
python3 tools/pack/verify_archive.py protocolcanary-fixtures-0.1.0.tar.gz \
  --manifest protocolcanary-fixtures-0.1.0.manifest.json
```

### Step 6.3: Verify build provenance attestation
Using the GitHub CLI (`gh`), verify that the archive was built by this repository's
release workflow:

```bash
gh attestation verify protocolcanary-fixtures-0.1.0.tar.gz \
  --repo StellarCanary/ProtocolCanary-Fixtures \
  --signer-workflow StellarCanary/ProtocolCanary-Fixtures/.github/workflows/release-pack.yml
```

And verify the manifest attestation:

```bash
gh attestation verify protocolcanary-fixtures-0.1.0.manifest.json \
  --repo StellarCanary/ProtocolCanary-Fixtures \
  --signer-workflow StellarCanary/ProtocolCanary-Fixtures/.github/workflows/release-pack.yml
```

---

## 7. Rollback and Superseding Bad Releases

If a defect is discovered in a published release archive or manifest:

1. **Do not move or delete the tag.** Moving tags breaks consumer caches and
   violates provenance guarantees.
2. **Author the fix.** Prepare a pull request addressing the defect.
3. **Bump the patch version.** Update `CHANGELOG.md` with an incremented patch
   version (e.g. `0.1.1`), explicitly stating that it supersedes `0.1.0` and
   describing the issue resolved.
4. **Publish the superseding release.** Merge to `main` and use a new
   protocol-scoped patch tag (e.g. `fixtures-p29-v0.1.1` or
   `fixtures-p28-v0.1.1`).
5. **Update release notes.** Edit the GitHub release notes of the superseded
   release to point users to the new version.
