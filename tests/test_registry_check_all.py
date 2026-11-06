"""Tests for isolated deterministic registry generation in tools/registry/check_all.py."""
from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.registry import check_all


class RegistryCheckAllTests(unittest.TestCase):
    def test_populated_pack_generates_and_validates_two_external_outputs(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            code = check_all.main(["protocol-30"])
        self.assertEqual(code, 0)

    def test_empty_pack_does_not_require_a_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = check_all.main([temp])
        self.assertEqual(code, 0)
        self.assertIn("no fixtures and no release registry is required", stdout.getvalue())

    def test_missing_pack_fails_with_a_clear_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            code = check_all.main(["not-a-pack"])
        self.assertEqual(code, 1)
        self.assertIn("not a protocol pack directory", stderr.getvalue())

    def test_different_generated_bytes_fail_determinism_check(self) -> None:
        writes = 0

        def write_different_registry(command: list[str]) -> None:
            nonlocal writes
            writes += 1
            output = Path(command[command.index("--output") + 1])
            output.write_bytes(str(writes).encode())

        with patch.object(check_all, "run", side_effect=write_different_registry):
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                code = check_all.main(["protocol-30"])
        self.assertEqual(code, 1)
        self.assertIn("registry generation is not deterministic", stderr.getvalue())

    def test_failed_subprocess_is_reported(self) -> None:
        with patch.object(check_all.subprocess, "run", return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(RuntimeError, "command failed with exit code 1"):
                check_all.run(["python", "missing-tool.py"])


if __name__ == "__main__":
    unittest.main()
