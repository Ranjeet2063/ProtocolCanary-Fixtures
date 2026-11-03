"""Release workflow permissions and ref checks must stay narrowly scoped."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release-pack.yml"
RELEASING_DOC = ROOT / "docs" / "releasing.md"


def job_block(workflow: str, name: str) -> str:
    lines = workflow.splitlines()
    try:
        start = lines.index(f"  {name}:")
    except ValueError as error:
        raise AssertionError(f"workflow is missing job {name!r}") from error
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("  ") and not lines[index].startswith("    "):
            end = index
            break
    return "\n".join(lines[start:end])


class ReleaseWorkflowSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.docs = RELEASING_DOC.read_text(encoding="utf-8")

    def test_workflow_defaults_to_no_permissions_and_scopes_write_access(self) -> None:
        self.assertRegex(self.workflow, r"(?m)^permissions: \{\}$")

        build = job_block(self.workflow, "build")
        self.assertRegex(build, r"(?m)^    permissions:\n      contents: read$")
        self.assertNotRegex(build, r"(?m)^      [a-z_-]+: write$")

        attest = job_block(self.workflow, "attest")
        self.assertIn("id-token: write", attest)
        self.assertIn("attestations: write", attest)
        self.assertNotIn("contents: write", attest)
        self.assertIn("github.event_name == 'push'", attest)

        publish = job_block(self.workflow, "publish")
        self.assertRegex(publish, r"(?m)^      contents: write$")
        self.assertNotIn("id-token: write", publish)
        self.assertNotIn("attestations: write", publish)
        self.assertIn("github.event_name == 'release' && github.event.action == 'published'", publish)

    def test_every_checkout_disables_credential_persistence(self) -> None:
        steps = re.findall(r"(?ms)^      - .*?(?=^      - |\Z)", self.workflow)
        checkout_steps = [step for step in steps if "uses: actions/checkout@" in step]
        self.assertEqual(len(checkout_steps), 2)
        for step in checkout_steps:
            self.assertIn("persist-credentials: false", step)

    def test_tag_and_release_jobs_validate_exact_ref_and_main_ancestry(self) -> None:
        self.assertGreaterEqual(self.workflow.count("--ref \"$EVENT_REF\""), 1)
        self.assertGreaterEqual(self.workflow.count("--sha \"$EVENT_SHA\""), 1)
        self.assertGreaterEqual(
            self.workflow.count("--main-ref refs/remotes/origin/main"), 2
        )
        self.assertIn("github.event.release.tag_name", self.workflow)
        selector = (ROOT / "tools/release/select_pack.py").read_text(encoding="utf-8")
        self.assertIn('"merge-base"', selector)
        self.assertIn('"--is-ancestor"', selector)

    def test_p29_verified_gate_and_tag_attestation_are_separate_from_upload(self) -> None:
        build = job_block(self.workflow, "build")
        attest = job_block(self.workflow, "attest")
        publish = job_block(self.workflow, "publish")
        self.assertIn("VERIFY_ARGS+=(--verified)", build)
        self.assertNotIn("--allow-empty", self.workflow)
        self.assertIn("actions/attest-build-provenance", attest)
        self.assertNotIn("gh release upload", attest)
        self.assertIn("gh release upload", publish)
        self.assertNotIn("--clobber", publish)

    def test_release_docs_require_tag_rules_and_use_current_scoped_examples(self) -> None:
        docs = self.docs.lower()
        self.assertIn("tag ruleset", docs)
        self.assertIn("restrict tag creation", docs)
        self.assertIn("block tag updates and deletion", docs)
        self.assertIn("workflow check alone does not protect against untrusted tag content", docs)
        self.assertIn("tag-push automation", docs)
        self.assertIn("release.published", docs)
        self.assertIn("fixtures-p28-v0.1.0", docs)
        self.assertIn("fixtures-p29-v0.1.0", docs)
        self.assertIn("94 fixture file(s) valid across 3 root(s)", docs)
        self.assertIn("93 fixture(s), 93 file(s) valid", docs)
        self.assertNotIn("OK: 31 fixture file(s)", docs)
        self.assertNotIn("(e.g. `v0.1.1`)", docs)

if __name__ == "__main__":
    unittest.main()
