"""The ids the observability scripts check (SPEC §7, §17, §19): an architect pass's id (`Kind.rid_re`) and a spec
question's (`spec_maintainer.QID_RE`) take their shape from ccp/refs.py."""
from __future__ import annotations

import secrets
import sys
import unittest
from datetime import datetime, timezone

from ccp import architect
from tests.helpers import PLANE_ROOT

sys.path.insert(0, str(PLANE_ROOT / "scripts" / "observability"))

import spec_maintainer as sm  # noqa: E402


class PassId(unittest.TestCase):
    def test_a_fresh_pass_or_shape_id_matches(self):
        for mode in ("pass", "shape"):
            with self.subTest(mode=mode):
                self.assertRegex(architect._new_rid(mode), architect.ARCH.rid_re)  # noqa: SLF001

    def test_a_three_hex_digit_suffix_does_not(self):
        self.assertNotRegex(architect._new_rid("pass")[:-1], architect.ARCH.rid_re)  # noqa: SLF001


class QuestionId(unittest.TestCase):
    @staticmethod
    def fresh() -> str:
        """A question id made as spec_maintainer's `raise` makes one."""
        return f"sm-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(2)}"

    def test_a_fresh_question_id_matches(self):
        self.assertRegex(self.fresh(), sm.QID_RE)

    def test_a_three_hex_digit_suffix_does_not(self):
        self.assertNotRegex(self.fresh()[:-1], sm.QID_RE)


if __name__ == "__main__":
    unittest.main()
