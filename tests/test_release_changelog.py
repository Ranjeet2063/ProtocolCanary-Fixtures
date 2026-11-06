"""Deterministic release notes from uniquely named changelog fragments."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "release" / "changelog.py"
SPEC = importlib.util.spec_from_file_location("release_changelog", TOOL)
changelog = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(changelog)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


class ReleaseChangelogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="release-changelog-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        git(self.root, "init", "--quiet")
        git(self.root, "config", "user.name", "Fixture changelog test")
        git(self.root, "config", "user.email", "fixtures@example.invalid")
        (self.root / "README.md").write_text("test-only repository\n", encoding="utf-8")
        git(self.root, "add", "README.md")
        git(self.root, "commit", "--quiet", "-m", "baseline")
        git(self.root, "tag", "fixtures-p28-v1.0.0")

    def write_fragment(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit_fragments(self) -> None:
        git(self.root, "add", "changelog.d")
        git(self.root, "commit", "--quiet", "-m", "add independent fragments")

    def test_added_pack_and_common_fragments_are_sorted_and_deterministic(self) -> None:
        self.write_fragment(
            "changelog.d/protocol-28/z-last.md", "- Test-only second contribution.\n"
        )
        self.write_fragment(
            "changelog.d/common/a-common.md", "- Test-only common tooling note.\n"
        )
        self.write_fragment(
            "changelog.d/protocol-28/a-first.md", "- Test-only first contribution.\n"
        )
        self.write_fragment(
            "changelog.d/protocol-29/other-pack.md", "- Must not appear in Protocol 28.\n"
        )
        self.commit_fragments()

        first = changelog.render_changelog(self.root, 28, "1.1.0")
        second = changelog.render_changelog(self.root, 28, "1.1.0")
        self.assertEqual(first, second)
        self.assertLess(first.index("### a-common"), first.index("### a-first"))
        self.assertLess(first.index("### a-first"), first.index("### z-last"))
        self.assertNotIn("other-pack", first)

    def test_fragments_from_previous_release_are_not_repeated(self) -> None:
        self.write_fragment("changelog.d/protocol-28/first.md", "- First released note.\n")
        self.commit_fragments()
        git(self.root, "tag", "fixtures-p28-v1.1.0")
        self.write_fragment("changelog.d/protocol-28/second.md", "- Later note.\n")
        git(self.root, "add", "changelog.d/protocol-28/second.md")
        git(self.root, "commit", "--quiet", "-m", "add a later fragment")

        output = changelog.render_changelog(self.root, 28, "1.2.0")
        self.assertIn("Later note", output)
        self.assertNotIn("First released note", output)

    def test_no_fragment_additions_still_produce_deterministic_release_notes(self) -> None:
        output = changelog.render_changelog(self.root, 28, "1.1.0")
        self.assertIn("No changelog fragments were added since `fixtures-p28-v1.0.0`.", output)

    def test_first_release_collects_only_common_and_selected_pack_fragments(self) -> None:
        git(self.root, "tag", "--delete", "fixtures-p28-v1.0.0")
        self.write_fragment("changelog.d/common/common.md", "- Test-only shared note.\n")
        self.write_fragment("changelog.d/protocol-28/p28.md", "- Test-only pack note.\n")
        self.write_fragment("changelog.d/protocol-29/p29.md", "- Other pack note.\n")

        output = changelog.render_changelog(self.root, 28, "0.1.0")
        self.assertIn("Test-only shared note", output)
        self.assertIn("Test-only pack note", output)
        self.assertNotIn("Other pack note", output)

    def test_malformed_older_release_tag_is_ignored(self) -> None:
        git(self.root, "tag", "fixtures-p28-v1.2")
        self.write_fragment("changelog.d/protocol-28/later.md", "- A later note.\n")
        self.commit_fragments()

        self.assertEqual(changelog.previous_tag(self.root, 28, "1.1.0"), "fixtures-p28-v1.0.0")

    def test_other_protocol_release_tags_are_ignored(self) -> None:
        git(self.root, "tag", "fixtures-p29-v9.0.0")

        self.assertEqual(changelog.previous_tag(self.root, 28, "1.1.0"), "fixtures-p28-v1.0.0")

    def test_release_tags_newer_than_the_selected_version_are_ignored(self) -> None:
        git(self.root, "tag", "fixtures-p28-v1.2.0")

        self.assertEqual(changelog.previous_tag(self.root, 28, "1.1.0"), "fixtures-p28-v1.0.0")

    def test_first_release_without_fragments_has_clear_output(self) -> None:
        output = changelog.render_changelog(self.root, 30, "0.1.0")

        self.assertIn("No changelog fragments are recorded for this pack yet.", output)

    def test_first_release_rejects_invalid_fragment_names(self) -> None:
        git(self.root, "tag", "--delete", "fixtures-p28-v1.0.0")
        self.write_fragment("changelog.d/protocol-28/BAD.md", "- Test-only note.\n")

        with self.assertRaisesRegex(changelog.ChangelogError, "invalid changelog fragment path"):
            changelog.render_changelog(self.root, 28, "0.1.0")

    def test_first_release_rejects_non_file_fragments(self) -> None:
        git(self.root, "tag", "--delete", "fixtures-p28-v1.0.0")
        directory = self.root / "changelog.d" / "protocol-28" / "directory.md"
        directory.mkdir(parents=True)

        with self.assertRaisesRegex(changelog.ChangelogError, "regular file, not a symlink"):
            changelog.render_changelog(self.root, 28, "0.1.0")

    def test_git_failure_is_reported(self) -> None:
        with self.assertRaisesRegex(changelog.ChangelogError, "not-a-git-command"):
            changelog.run_git(self.root, "not-a-git-command")

    def test_empty_fragment_fails_closed(self) -> None:
        self.write_fragment("changelog.d/protocol-28/empty.md", " \n")
        self.commit_fragments()
        with self.assertRaisesRegex(changelog.ChangelogError, "fragment is empty"):
            changelog.render_changelog(self.root, 28, "1.1.0")

    def test_invalid_utf8_fragment_fails_closed(self) -> None:
        path = self.root / "changelog.d" / "protocol-28" / "invalid.md"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"- invalid \xff\n")
        git(self.root, "add", "changelog.d")
        git(self.root, "commit", "--quiet", "-m", "add invalid fragment")
        with self.assertRaisesRegex(changelog.ChangelogError, "cannot read fragment safely"):
            changelog.render_changelog(self.root, 28, "1.1.0")

    def test_symlink_fragment_is_rejected(self) -> None:
        outside = self.root / "outside.md"
        outside.write_text("- Outside note.\n", encoding="utf-8")
        link = self.root / "changelog.d" / "protocol-28" / "linked.md"
        link.parent.mkdir(parents=True)
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlink creation is unavailable: {error}")
        git(self.root, "add", "changelog.d")
        git(self.root, "commit", "--quiet", "-m", "add symlink fragment")
        with self.assertRaisesRegex(changelog.ChangelogError, "regular file, not a symlink"):
            changelog.render_changelog(self.root, 28, "1.1.0")

    def test_cli_writes_release_notes_atomically(self) -> None:
        self.write_fragment("changelog.d/protocol-28/cli.md", "- CLI test note.\n")
        self.commit_fragments()
        output = self.root / "out" / "notes.md"
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = changelog.main(
                [
                    "--protocol",
                    "28",
                    "--version",
                    "1.1.0",
                    "--output",
                    str(output),
                    "--repo-root",
                    str(self.root),
                ]
            )
        self.assertEqual(code, 0)
        self.assertIn("OK: wrote", stdout.getvalue())
        self.assertIn("CLI test note", output.read_text(encoding="utf-8"))

    def test_cli_rejects_invalid_protocol_and_version(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            bad_protocol = changelog.main(
                ["--protocol", "0", "--version", "1.1.0", "--output", str(self.root / "out.md")]
            )
        self.assertEqual(bad_protocol, 1)
        self.assertIn("protocol must be a positive integer", stderr.getvalue())

        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            bad_version = changelog.main(
                ["--protocol", "28", "--version", "1.1", "--output", str(self.root / "out.md"), "--repo-root", str(self.root)]
            )
        self.assertEqual(bad_version, 1)
        self.assertIn("invalid release version", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
