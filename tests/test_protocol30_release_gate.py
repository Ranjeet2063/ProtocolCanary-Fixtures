"""Fail-closed Protocol 30 Testnet release gate tests (synthetic mutations)."""
from __future__ import annotations

import datetime
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pack_support as support  # noqa: E402

pack = support.pack
ROOT = support.REPO_ROOT


class Protocol30ReleaseEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pack_dir = Path(self.temp.name) / "protocol-30"
        shutil.copytree(ROOT / "protocol-30", self.pack_dir)
        self.record = next((self.pack_dir / "evidence/live/testnet/records").glob("*.json"))
        self.version = self.pack_dir / "evidence/live/testnet/captures/get-version-info.json"
        self.network = self.pack_dir / "evidence/live/testnet/captures/get-network.json"
        now = datetime.datetime.now(datetime.UTC).replace(microsecond=0)
        record_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        network_time = (now - datetime.timedelta(seconds=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.mutate(self.record, lambda r: r.update(checkedAt=record_time))
        self.mutate(self.version, lambda c: c.update(capturedAt=record_time))
        self.mutate(self.network, lambda c: c.update(capturedAt=network_time))

    def mutate(self, path, change):
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def assert_rejected(self, message):
        with self.assertRaisesRegex(pack.PackError, message):
            pack.check_verified_evidence(self.pack_dir)

    def test_valid_testnet_evidence_passes(self):
        pack.check_verified_evidence(self.pack_dir)

    def test_stale_capture_fails(self):
        self.mutate(self.record, lambda r: r.update(checkedAt="2020-01-01T00:00:00Z"))
        self.assert_rejected("freshness")

    def test_structural_evidence_is_not_a_release_gate(self):
        self.mutate(self.record, lambda r: r.update(method="structural"))
        self.assert_rejected("live-read-only")

    def test_other_network_is_not_accepted(self):
        self.mutate(self.record, lambda r: r["network"].update(
            name="futurenet", passphrase="Test SDF Future Network ; October 2022"
        ))
        self.assert_rejected("Testnet identity")

    def test_wrong_version_capture_protocol_fails(self):
        self.mutate(self.version, lambda c: c["response"]["result"].update(protocolVersion=29))
        self.assert_rejected("incorrect RPC identity")

    def test_wrong_network_passphrase_fails(self):
        self.mutate(self.network, lambda c: c["response"]["result"].update(passphrase="wrong network"))
        self.assert_rejected("passphrase mismatch")

    def test_missing_network_capture_fails(self):
        self.network.unlink()
        self.assert_rejected("missing or a symlink")

    def test_missing_json_rpc_ids_are_rejected(self):
        self.mutate(self.version, lambda c: (c["request"].pop("id"), c["response"].pop("id")))
        self.assert_rejected("incorrect RPC identity")

    def test_json_rpc_id_type_mismatch_is_rejected(self):
        self.mutate(self.version, lambda c: c["response"].update(id=2.0))
        self.assert_rejected("incorrect RPC identity")

    @unittest.skipIf(sys.platform == "win32", "symlink privileges vary on Windows")
    def test_symlinked_capture_directory_is_rejected(self):
        capture_dir = self.version.parent
        outside = self.pack_dir.parent / "external-captures"
        capture_dir.rename(outside)
        capture_dir.symlink_to(outside, target_is_directory=True)
        self.assert_rejected("symbolic link|resolves outside the pack")

    def test_wrong_endpoint_host_fails(self):
        self.mutate(self.version, lambda c: c.update(endpointHost="example.invalid"))
        self.assert_rejected("incorrect RPC identity")

    def test_wrong_version_capture_timestamp_fails(self):
        self.mutate(self.version, lambda c: c.update(capturedAt="2026-01-01T00:00:00Z"))
        self.assert_rejected("timestamp mismatch")

    def test_not_contemporaneous_network_capture_fails(self):
        self.mutate(self.network, lambda c: c.update(capturedAt="2026-01-01T00:00:00Z"))
        self.assert_rejected("not contemporaneous")

    def test_wrong_fixture_digest_fails(self):
        self.mutate(self.record, lambda r: r.update(fixtureSha256="0" * 64))
        self.assert_rejected("fixture")

    def test_missing_record_fails(self):
        self.record.unlink()
        self.assert_rejected("missing")

    def test_wrong_evidence_reference_fails(self):
        self.mutate(self.record, lambda r: r.update(evidenceRef="protocol-29/evidence/live/testnet/captures/get-version-info.json"))
        self.assert_rejected("exact raw capture")


if __name__ == "__main__":
    unittest.main()
