"""Exercise two independent Protocol 30 additions using test-only inputs.

These synthetic files exercise registry, evidence and release plumbing only.
They are not Stellar protocol vectors and make no conformance claim.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.evidence import record_structural
from tools.pack import pack
from tools.registry import generate

ROOT = Path(__file__).resolve().parents[1]
PACK30 = ROOT / "protocol-30"
SHARED_PATHS = (
    "README.md",
    "CHANGELOG.md",
    "protocol-30/README.md",
    "tests/test_protocol30_pack.py",
)


def fixture_bytes(fixture_id: str, payload_name: str) -> bytes:
    """A structurally valid test-only XDR-shaped input, not a protocol vector."""
    return (
        "# TEST ONLY: registry and evidence isolation input.\n"
        "# This synthetic data asserts no Protocol 30 behavior.\n"
        f'id = "{fixture_id}"\n'
        "protocol = 30\n"
        'surface = "xdr"\n'
        'category = "cap-0088"\n'
        'description = "TEST ONLY registry isolation input; no protocol claim"\n'
        'source_reference = "CAP-0088"\n'
        f'input_file = "{payload_name}"\n'
        'type = "StellarValue"\n'
        'kind = "roundtrip"\n'
        'value_base64 = "AAAAAA=="\n'
    ).encode()


class IndependentFixtureContributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="fixture-contributions-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "base"
        self.base.mkdir()
        shutil.copytree(PACK30, self.base / "protocol-30")
        for relative in SHARED_PATHS:
            source = ROOT / relative
            target = self.base / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        self.shared_before = {
            relative: (self.base / relative).read_bytes() for relative in SHARED_PATHS
        }

    def _add_contribution(self, branch: Path, slug: str) -> tuple[str, list[str]]:
        fixture_id = f"p30-xdr-test-only-isolation-{slug}"
        pack_dir = branch / "protocol-30"
        fixture_relative = f"xdr/cap-0088/test-only-{slug}.toml"
        payload_relative = f"xdr/cap-0088/test-only-{slug}.bin"
        fixture_path = pack_dir / fixture_relative
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        fixture_path.write_bytes(fixture_bytes(fixture_id, f"test-only-{slug}.bin"))
        (pack_dir / payload_relative).write_bytes(
            f"synthetic test-only payload {slug}; not XDR evidence\n".encode("ascii")
        )

        test_path = f"tests/test_fixture_test_only_{slug}.py"
        (branch / test_path).write_text(
            '"""Test-only contribution metadata regression; no protocol claim."""\n'
            f'FIXTURE_ID = "{fixture_id}"\n',
            encoding="utf-8",
        )
        fragment_path = f"changelog.d/protocol-30/test-only-{slug}.md"
        fragment = branch / fragment_path
        fragment.parent.mkdir(parents=True, exist_ok=True)
        fragment.write_text(
            f"- Add isolated test-only registry input {slug}.\n", encoding="utf-8"
        )

        # Generate records outside the checkout. Only this contribution's
        # uniquely named record is copied into its branch.
        generated = self.root / f"generated-records-{slug}"
        record_structural.run(pack_dir, output_dir=generated, version="test-only")
        record_path = generated / f"{fixture_id}.json"
        self.assertTrue(record_path.is_file())
        evidence_relative = f"protocol-30/evidence/records/{fixture_id}.json"
        evidence_target = branch / evidence_relative
        evidence_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(record_path, evidence_target)
        return fixture_id, [
            f"protocol-30/{fixture_relative}",
            f"protocol-30/{payload_relative}",
            evidence_relative,
            test_path,
            fragment_path,
        ]

    def _branch(self, slug: str) -> tuple[Path, str, list[str]]:
        branch = self.root / f"branch-{slug}"
        shutil.copytree(self.base, branch)
        fixture_id, added = self._add_contribution(branch, slug)
        return branch, fixture_id, added

    def test_two_contributions_merge_with_unique_files_and_stable_release_inputs(self) -> None:
        branch_a, id_a, files_a = self._branch("a")
        branch_b, id_b, files_b = self._branch("b")
        self.assertEqual(set(files_a).intersection(files_b), set())

        for branch in (branch_a, branch_b):
            for relative, before in self.shared_before.items():
                self.assertEqual((branch / relative).read_bytes(), before, relative)
            self.assertFalse((branch / "protocol-30/registry-v1.json").exists())

        merged = self.root / "merged"
        shutil.copytree(branch_a, merged)
        for relative in files_b:
            destination = merged / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(branch_b / relative, destination)

        for relative, before in self.shared_before.items():
            self.assertEqual((merged / relative).read_bytes(), before, relative)
        self.assertFalse((merged / "protocol-30/registry-v1.json").exists())

        merged_pack = merged / "protocol-30"
        canonical = generate.generate(merged_pack)
        self.assertEqual(canonical.encode("utf-8"), generate.generate(merged_pack).encode("utf-8"))
        registry = json.loads(canonical)
        entries = {item["id"]: item for item in registry["fixtures"]}
        self.assertIn(id_a, entries)
        self.assertIn(id_b, entries)
        self.assertEqual(
            entries[id_a]["payloads"][0]["path"], "xdr/cap-0088/test-only-a.bin"
        )
        self.assertEqual(
            entries[id_b]["payloads"][0]["path"], "xdr/cap-0088/test-only-b.bin"
        )

        # Contribution order does not affect canonical bytes or the digest.
        reversed_pack = self.root / "reverse-order" / "protocol-30"
        shutil.copytree(self.base / "protocol-30", reversed_pack)
        for relative in [*files_b[:2], *files_a[:2]]:
            source = merged / relative
            destination = reversed_pack / Path(relative).relative_to("protocol-30")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        self.assertEqual(canonical, generate.generate(reversed_pack))
        self.assertTrue(registry["packDigest"].startswith("sha256:"))
        archive_members, archive_digest, archive_protocol = pack.collect_members(merged_pack)
        self.assertEqual(archive_members["registry.json"], canonical.encode("utf-8"))
        self.assertEqual(archive_digest, registry["packDigest"])
        self.assertEqual(archive_protocol, 30)

        # Existing P30 release evidence remains valid with per-fixture records.
        pack.check_verified_evidence(merged_pack)
        (merged_pack / "evidence/records" / f"{id_b}.json").unlink()
        with self.assertRaisesRegex(pack.PackError, id_b):
            pack.check_verified_evidence(merged_pack)

    def test_duplicate_fixture_id_is_rejected_after_two_additions(self) -> None:
        branch_a, id_a, _files_a = self._branch("a")
        branch_b, _id_b, files_b = self._branch("b")
        merged_pack = self.root / "duplicate" / "protocol-30"
        shutil.copytree(branch_a / "protocol-30", merged_pack)
        for relative in files_b[:2]:
            destination = merged_pack / Path(relative).relative_to("protocol-30")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(branch_b / relative, destination)
        fixture_b = merged_pack / Path(files_b[0]).relative_to("protocol-30")
        contents = fixture_b.read_text(encoding="utf-8")
        old_id = "p30-xdr-test-only-isolation-b"
        fixture_b.write_text(contents.replace(old_id, id_a), encoding="utf-8")
        with self.assertRaisesRegex(generate.PackError, "duplicate fixture id"):
            generate.generate(merged_pack)


if __name__ == "__main__":
    unittest.main()
