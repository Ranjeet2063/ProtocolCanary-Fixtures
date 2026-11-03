"""Release events must select one explicit protocol pack and version."""
from __future__ import annotations

import sys
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


if __name__ == "__main__":
    unittest.main()
