"""`ccp tasks close` (SPEC §10.5): its refusals on what the PR host did with the merge, judged on plain values."""
from __future__ import annotations

import unittest

from ccp import lifecycle
from ccp.prhost import MergeResult, PrFacts

LABEL, PR, TID, HEAD = "a host", "7", "0002-second", "c" * 40


class MergeRefused(unittest.TestCase):
    def test_a_merge_the_host_made_is_no_refusal(self):
        self.assertIsNone(lifecycle.merge_refused(LABEL, PR, TID, HEAD, False, MergeResult(True, "merged")))

    def test_a_merge_the_host_refuses_names_the_host_the_pr_and_its_words(self):
        why = lifecycle.merge_refused(LABEL, PR, TID, HEAD, False, MergeResult(False, "refused here"))
        self.assertIn(f"{LABEL} did not merge PR {PR}: refused here", why)
        self.assertNotIn("ccp prompt merge", why)
        self.assertNotIn(HEAD[:7], why)

    def test_a_conflict_points_to_the_merge_prompt(self):
        why = lifecycle.merge_refused(LABEL, PR, TID, HEAD, False, MergeResult(False, "conflict", conflict=True))
        self.assertIn("ccp prompt merge", why)

    def test_a_head_close_caught_up_is_named_for_the_rerun(self):
        why = lifecycle.merge_refused(LABEL, PR, TID, HEAD, True, MergeResult(False, "refused here"))
        self.assertIn(HEAD[:7], why)
        self.assertIn(f"ccp tasks close {TID} --pr {PR}", why)


class NotMerged(unittest.TestCase):
    def test_a_merge_the_host_has_not_completed_names_the_hosts_own_state_word(self):
        why = lifecycle.not_merged(LABEL, PR, TID, PrFacts(number=7, state="open", head=HEAD), True)
        self.assertIn(f"{LABEL} merged PR {PR} without error, but it is OPEN", why)
        self.assertIn(f"ccp tasks close {TID} --pr {PR}", why)

    def test_a_merged_pr_without_a_merge_commit_names_the_host(self):
        why = lifecycle.not_merged(LABEL, PR, TID, PrFacts(number=7, state="merged", head=HEAD), True)
        self.assertIn(f"PR {PR} is merged but {LABEL} names no merge commit", why)

    def test_a_pr_merged_before_close_is_judged_only_on_its_merge_commit(self):
        open_with_commit = PrFacts(number=7, state="open", head=HEAD, merge_commit="d" * 40)
        self.assertIsNone(lifecycle.not_merged(LABEL, PR, TID, open_with_commit, False))
        no_commit = PrFacts(number=7, state="merged", head=HEAD)
        self.assertIn("names no merge commit", lifecycle.not_merged(LABEL, PR, TID, no_commit, False))

    def test_a_merged_pr_with_a_merge_commit_is_no_refusal(self):
        merged = PrFacts(number=7, state="merged", head=HEAD, merge_commit="d" * 40)
        for merged_now in (True, False):
            self.assertIsNone(lifecycle.not_merged(LABEL, PR, TID, merged, merged_now))


if __name__ == "__main__":
    unittest.main()
