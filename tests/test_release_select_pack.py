"""Release events must select one explicit protocol pack and version."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pack_support as support  # noqa: E402

selector = support.load_tool("canary_select_pack", "tools/release/select_pack.py")


class PackSelectionTests(unittest.TestCase):
    def test_versioned_tags_select_exact_protocol_and_version(self) -> None:
        for protocol in ("28", "29"):
            with self.subTest(protocol=protocol):
                self.assertEqual(
                    selector.select(
                        event="push", tag=f"fixtures-p{protocol}-v1.2.3"
                    ),
                    {
                        "pack": f"protocol-{protocol}",
                        "protocol": protocol,
                        "version": "1.2.3",
                        "verified": "true" if protocol == "29" else "false",
                    },
                )

    def test_manual_dispatch_requires_an_explicit_supported_protocol(self) -> None:
        selected = selector.select(
            event="workflow_dispatch", protocol="29", version="2.0.1"
        )
        self.assertEqual(selected["pack"], "protocol-29")
        self.assertEqual(selected["version"], "2.0.1")
        self.assertEqual(selected["verified"], "true")

    def test_unscoped_or_legacy_tags_are_rejected(self) -> None:
        for tag in ("v1.2.3", "fixtures-v1.2.3", "protocol-29", "fixtures-p30-v1.2.3"):
            with self.subTest(tag=tag), self.assertRaises(selector.SelectionError):
                selector.select(event="release", tag=tag)

    def test_malformed_versions_and_ambiguous_inputs_are_rejected(self) -> None:
        for version in ("1.2", "01.2.3", "1.2.3-rc.1", "1.2.3\n"):
            with self.subTest(version=version), self.assertRaises(selector.SelectionError):
                selector.select(
                    event="workflow_dispatch", protocol="29", version=version
                )
        with self.assertRaises(selector.SelectionError):
            selector.select(event="push", tag="fixtures-p28-v1.2.3", protocol="28")
        with self.assertRaises(selector.SelectionError):
            selector.select(event="workflow_dispatch", protocol="30", version="1.2.3")


class ReleaseRefValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.git("init")
        self.git("checkout", "-b", "main")
        self.git("config", "user.name", "Fixture Test")
        self.git("config", "user.email", "fixture-test@example.invalid")
        (self.repo / "README.md").write_text("trusted main commit\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "trusted main commit")
        self.main_sha = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.main_sha)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def test_push_and_published_release_accept_only_exact_main_tag_commit(self) -> None:
        tag = "fixtures-p29-v1.2.3"
        ref = f"refs/tags/{tag}"
        self.git("tag", tag)

        for event in ("push", "release"):
            with self.subTest(event=event):
                selection = selector.validate_release_ref(
                    event=event,
                    tag=tag,
                    ref=ref,
                    sha=self.main_sha,
                    repo=self.repo,
                )
                self.assertEqual(selection["pack"], "protocol-29")
                self.assertEqual(selection["verified"], "true")
                self.assertEqual(selection["commit"], self.main_sha)

    def test_release_ref_must_match_event_tag_and_commit(self) -> None:
        tag = "fixtures-p28-v1.2.3"
        self.git("tag", tag)

        with self.assertRaisesRegex(selector.SelectionError, "does not exactly match"):
            selector.validate_release_ref(
                event="release",
                tag="fixtures-p29-v1.2.3",
                ref=f"refs/tags/{tag}",
                sha=self.main_sha,
                repo=self.repo,
            )

        with self.assertRaisesRegex(selector.SelectionError, "not event commit"):
            selector.validate_release_ref(
                event="push",
                tag=tag,
                ref=f"refs/tags/{tag}",
                sha="0" * 40,
                repo=self.repo,
            )

    def test_release_tag_on_commit_outside_main_history_is_rejected(self) -> None:
        tag = "fixtures-p28-v1.2.4"
        self.git("checkout", "-b", "untrusted")
        (self.repo / "untrusted.txt").write_text("not on main\n", encoding="utf-8")
        self.git("add", "untrusted.txt")
        self.git("commit", "-m", "untrusted side commit")
        side_sha = self.git("rev-parse", "HEAD")
        self.git("tag", tag)

        with self.assertRaisesRegex(selector.SelectionError, "not in protected main history"):
            selector.validate_release_ref(
                event="push",
                tag=tag,
                ref=f"refs/tags/{tag}",
                sha=side_sha,
                repo=self.repo,
            )


if __name__ == "__main__":
    unittest.main()
