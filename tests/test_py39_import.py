"""launchd starts the telemetry receiver with the system python3, which on macOS can be 3.9. Every
module of the package must import there, so PEP 604 annotations (`str | None`) need
`from __future__ import annotations` in each module that uses them."""
import pathlib
import re
import unittest

PKG = pathlib.Path(__file__).resolve().parent.parent / "ccp"
PEP604 = re.compile(r"(->|:)\s*[^=\n]*\w\s*\|\s*None")


class EveryModuleImportsOnTheSystemPython(unittest.TestCase):
    def test_pep604_annotations_are_postponed(self):
        missing = [
            str(p.relative_to(PKG.parent))
            for p in sorted(PKG.rglob("*.py"))
            if PEP604.search(p.read_text())
            and "from __future__ import annotations" not in p.read_text()
        ]
        self.assertEqual(missing, [], "add `from __future__ import annotations` to these modules")


if __name__ == "__main__":
    unittest.main()
