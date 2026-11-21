"""SPEC §29.3: the text-level JSON editor behind the plane.json records changes one member and keeps every
other byte of the text."""
from __future__ import annotations

import json
import unittest
from unittest import mock

from ccp import jsonedit

INDENTED = '{\n  "project_id": "demo",\n  "suite": {"lanes": {"gate": ["true"]}},\n  "upgrade": {\n    "taken": {\n      "0001-a": "kept"\n    }\n  }\n}\n'
TRICKY = '{"a": "x{y}z", "b": "q\\"u{o}te\\\\", "c": "café } {", "d": [1, {"e": "]"}], "f": {}}'


class Spliced(unittest.TestCase):
    def spliced(self, before: str, after: str, at: int, removed: str, inserted: str) -> None:
        """`after` is `before` with `removed`, found at `at`, replaced by `inserted`: every other byte kept."""
        self.assertEqual(before[at:at + len(removed)], removed)
        self.assertEqual(after[:at], before[:at])
        self.assertEqual(after[at + len(inserted):], before[at + len(removed):])
        self.assertEqual(after[at:at + len(inserted)], inserted)
        self.assertEqual(len(after), len(before) - len(removed) + len(inserted))


class SetMember(Spliced):
    def test_a_new_member_in_an_indented_object_goes_on_its_own_line_indented_like_the_last(self):
        after = jsonedit.set_member(INDENTED, ["upgrade", "taken"], "0002-b", "also")
        at = INDENTED.index('"kept"') + len('"kept"')
        self.spliced(INDENTED, after, at, "", ',\n      "0002-b": "also"')
        self.assertEqual(json.loads(after)["upgrade"]["taken"], {"0001-a": "kept", "0002-b": "also"})

    def test_a_new_top_level_member_in_an_indented_file_goes_on_its_own_line(self):
        after = jsonedit.set_member(INDENTED, [], "language", "none")
        at = INDENTED.rindex("}\n  }") + len("}\n  }")
        self.spliced(INDENTED, after, at, "", ',\n  "language": "none"')

    def test_a_new_member_in_an_inline_object_is_written_inline(self):
        before = '{\n  "suite": {"lanes": {"gate": ["true"]}},\n  "x": 1\n}\n'
        after = jsonedit.set_member(before, ["suite", "lanes"], "full", ["a", "b"])
        at = before.index('["true"]') + len('["true"]')
        self.spliced(before, after, at, "", ', "full": ["a", "b"]')

    def test_a_new_member_in_an_empty_object_is_written_inside_it(self):
        before = '{"project_id": "demo", "upgrade": {"taken": {}}}'
        after = jsonedit.set_member(before, ["upgrade", "taken"], "0001-a", "kept")
        at = before.index("{}") + 1
        self.spliced(before, after, at, "", '"0001-a": "kept"')
        self.assertEqual(jsonedit.set_member("{}", [], "k", 1), '{"k": 1}')

    def test_an_existing_members_value_is_replaced_in_its_span(self):
        after = jsonedit.set_member(INDENTED, ["upgrade", "taken"], "0001-a", "changed")
        at = INDENTED.index('"kept"')
        self.spliced(INDENTED, after, at, '"kept"', '"changed"')

    def test_an_existing_object_value_is_replaced_whole(self):
        before = '{"a": {"b": [1, 2]}, "c": 3}'
        after = jsonedit.set_member(before, [], "a", {"z": None})
        self.spliced(before, after, before.index('{"b"'), '{"b": [1, 2]}', '{"z": null}')

    def test_a_missing_object_on_the_path_is_made_inline(self):
        before = '{\n  "project_id": "demo",\n  "architect": false\n}\n'
        after = jsonedit.set_member(before, ["upgrade", "taken"], "0185", "kept off")
        at = before.index("false") + len("false")
        self.spliced(before, after, at, "", ',\n  "upgrade": {"taken": {"0185": "kept off"}}')
        inline = '{"project_id": "demo", "upgrade": {"declined": {"0001-a": "no"}}}'
        after = jsonedit.set_member(inline, ["upgrade", "taken"], "0002-b", "yes")
        at = inline.index('"no"}') + len('"no"}')
        self.spliced(inline, after, at, "", ', "taken": {"0002-b": "yes"}')

    def test_strings_holding_braces_quotes_backslashes_and_non_ascii_are_read_and_written(self):
        after = jsonedit.set_member(TRICKY, ["f"], "g", 'a{b}"c\\dé')
        at = TRICKY.rindex("{}") + 1
        self.spliced(TRICKY, after, at, "", '"g": "a{b}\\"c\\\\dé"')
        self.assertEqual(json.loads(after)["f"], {"g": 'a{b}"c\\dé'})
        after = jsonedit.set_member(TRICKY, [], "b", "é")
        at = TRICKY.index('"q')
        self.spliced(TRICKY, after, at, '"q\\"u{o}te\\\\"', '"é"')

    def test_a_path_through_a_value_that_is_not_an_object_or_text_that_is_not_an_object_is_refused(self):
        for text, path in (('{"a": [1]}', ["a"]), ('{"a": "x"}', ["a", "b"]), ("[1, 2]", []), ("{not json", []),
                           ('{"a": 1} 2', []), ('{"a": "x\n"}', [])):
            with self.assertRaises(ValueError, msg=text):
                jsonedit.set_member(text, path, "k", 1)


class DeleteMember(Spliced):
    def test_the_first_member_goes_with_its_comma(self):
        before = '{"a": 1, "b": 2, "c": 3}'
        self.spliced(before, jsonedit.delete_member(before, [], "a"), before.index('"a"'), '"a": 1, ', "")
        before = '{\n  "a": 1,\n  "b": 2\n}\n'
        self.spliced(before, jsonedit.delete_member(before, [], "a"), before.index('"a"'), '"a": 1,\n  ', "")

    def test_a_middle_member_goes_with_its_comma(self):
        before = '{"a": 1, "b": "}", "c": 3}'
        self.spliced(before, jsonedit.delete_member(before, [], "b"), before.index('"b"'), '"b": "}", ', "")
        after = jsonedit.delete_member(INDENTED, [], "suite")
        at = INDENTED.index('"suite"')
        self.spliced(INDENTED, after, at, '"suite": {"lanes": {"gate": ["true"]}},\n  ', "")

    def test_the_last_member_goes_with_the_comma_before_it(self):
        before = '{"a": 1, "b": 2, "c": 3}'
        self.spliced(before, jsonedit.delete_member(before, [], "c"), before.index(', "c"'), ', "c": 3', "")
        before = '{\n  "a": 1,\n  "b": 2\n}\n'
        self.spliced(before, jsonedit.delete_member(before, [], "b"), before.index(',\n  "b"'), ',\n  "b": 2', "")

    def test_the_only_member_leaves_an_empty_object(self):
        after = jsonedit.delete_member(INDENTED, ["upgrade", "taken"], "0001-a")
        at = INDENTED.index('"taken": {') + len('"taken": {')
        self.spliced(INDENTED, after, at, '\n      "0001-a": "kept"\n    ', "")
        self.assertEqual(json.loads(after)["upgrade"]["taken"], {})

    def test_every_member_of_a_repeated_name_goes(self):
        self.assertEqual(jsonedit.delete_member('{"a": 1, "b": 2, "a": 3}', [], "a"), '{"b": 2}')

    def test_a_key_or_path_that_is_not_there_leaves_the_text_unchanged(self):
        for path, key in (([], "zz"), (["upgrade", "declined"], "0001-a"), (["project_id"], "x"),
                          (["upgrade", "taken"], "0002-b")):
            self.assertEqual(jsonedit.delete_member(INDENTED, path, key), INDENTED, (path, key))

    def test_strings_holding_braces_quotes_backslashes_and_non_ascii_are_skipped(self):
        after = jsonedit.delete_member(TRICKY, [], "c")
        at = TRICKY.index('"c"')
        self.spliced(TRICKY, after, at, '"c": "café } {", ', "")


class Guard(unittest.TestCase):
    def test_an_edit_that_does_not_read_as_the_same_edit_on_the_loaded_data_is_refused(self):
        text = '{"a": 1}'
        with mock.patch("ccp.jsonedit._set_text", return_value='{"a": 1, "k": 2}'):
            with self.assertRaises(ValueError):
                jsonedit.set_member(text, [], "k", 1)
        with mock.patch("ccp.jsonedit._set_text", return_value='{"a": 1, "k": 1'):
            with self.assertRaises(ValueError):
                jsonedit.set_member(text, [], "k", 1)
        with mock.patch("ccp.jsonedit._delete_text", return_value=text):
            with self.assertRaises(ValueError):
                jsonedit.delete_member(text, [], "a")


if __name__ == "__main__":
    unittest.main()
