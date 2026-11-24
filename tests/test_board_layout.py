"""§28 layout: the header strip on every tab, five hash-routed tabs, each section in its tab."""
from __future__ import annotations

import re
import shutil
import unittest

from tests.helpers import machine_file
from tests.ledger_helpers import good_then_failed
from tests.render_helpers import BoardPage
from tests.board_drill_fixture import Fixture
from tests.board_quality_fixture import HOSTILE, _hostile

PANES = re.compile(r'<div class="pane grid" id="pane-(\w+)"[^>]*?( hidden)?>')
# The pane a section's heading must sit in, and the header strip's headings (before the first pane).
WHERE = {"performance": ["<h2>Seats</h2>", "Tokens by seat", "Tokens per day, by seat", "Wall time per task",
                         "Runs with usage", "Suite and prompt, last 30 merged"],
         "quality": ["Architect passes and triage", "Friction notes", "House rules and budgets"],
         "backlog": ["ADR register", "Burn-up", "Dependency graph, open tasks"],
         "queue": ["Now, in detail", "<h2>Forecast</h2>", "Ready queue", "Review points", "Task board"],
         "health": ["<h2>Plane health</h2>", "<h2>Allowance</h2>"]}


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class Layout(BoardPage, Fixture, unittest.TestCase):
    def shown(self, html: str) -> list[str]:
        return [k for k, hid in PANES.findall(html) if not hid]

    def test_each_section_sits_in_its_tab_and_the_strip_is_above_them(self):
        self.seed()
        self.arch_on()
        self.a_pass()
        html, _ = self.page(self.build()[0])
        panes = PANES.findall(html)
        self.assertEqual([k for k, _ in panes], ["performance", "quality", "backlog", "queue", "health"])
        head, rest = html.split('<div class="pane grid"', 1)
        for t in ("Weekly allowance", "Tokens, last 7 days", 'aria-label="Now"', 'role="tablist"'):
            self.assertIn(t, head)
        body = dict(zip([k for k, _ in panes], re.split(r'<div class="pane grid" id="pane-\w+"', html)[1:]))
        for tab, titles in WHERE.items():
            for t in titles:
                self.assertIn(t, body[tab], (tab, t))
                for other in set(body) - {tab}:
                    self.assertNotIn(t, body[other], (other, t))
        self.assertEqual(self.shown(html), ["performance"])  # no hash, nothing stored: the first tab

    def test_the_hash_picks_the_tab_and_a_bad_one_falls_back(self):
        self.seed()
        b = self.build()[0]
        self.assertEqual(self.shown(self.page(b, "#tab=queue")[0]), ["queue"])
        for h in ("#tab=__proto__", "#tab=<img src=x onerror=alert(1)>", "#tab=%E0%A4%A", "#tab=", "#tab=Queue"):
            html, panel = self.page(b, h)
            self.assertEqual(self.shown(html), ["performance"], h)
            self.assertEqual(panel, [], h)
        html, panel = self.page(b, "#tab=health&task=0002-second")
        self.assertEqual(self.shown(html), ["health"])
        self.assertEqual(len(panel), 1)
        self.assertIn("Runs of 0002-second on a time axis", panel[0])
        self.assertEqual(self.page(b, "#tab=backlog&task=%3Cimg%3E")[1], [])

    def test_the_strip_and_badges_render_hostile_strings_as_text(self):
        self.seed()
        b = self.build()[0]
        b["now"]["held"] = [{"task_id": "0009-x", "by": "lead", "reason": "r"}]  # ccp tasks hold, when present
        b["now"]["next_tasks"] = {"tasks": ["0002-second", "0004-x"], "by": "lead", "reason": "r"}
        b["health"]["stale_sources"] = ["events"]
        b["health"]["last_rebuild_failure"] = "boom"
        html, _ = self.page(_hostile(b))
        head = html.split('<div class="pane grid"', 1)[0]
        for t in ("Held", "Next (lead)", "Stale sources", "Last rebuild failed", "&lt;!--&lt;script&gt;"):
            self.assertIn(t, head)
        self.assertRegex(head, r'id="tab-health"[^>]*>.*?<span class="badge warn"[^>]*>2</span>')
        for raw in ("<!--", "<script", "<img", "</script"):
            self.assertNotIn(raw, html)
        self.assertNotIn(HOSTILE, html)

    def test_a_stale_proposal_is_flagged_in_plane_health_and_counts_in_its_badge(self):
        self.seed()
        b = self.build()[0]
        b["health"]["proposals_open"] = [{"id": "pp-old", "need": "old need", "again": 0, "stale": True},
                                         {"id": "pp-new", "need": "new need", "again": 0, "stale": False}]
        html, _ = self.page(b, "#tab=health")
        line = re.search(r"Open ccp proposals: (.*?)</li>", html).group(1)
        old, new = line.split("; ")
        self.assertIn("untriaged 7+ days", old)
        self.assertNotIn("untriaged 7+ days", new)
        self.assertRegex(html, r'id="tab-health"[^>]*>.*?<span class="badge warn"[^>]*>1</span>')

    def test_the_weekly_tile_shows_the_latest_good_figure_and_its_age_after_a_failed_read(self):
        self.seed()
        machine_file(self, allowance_cmd="false", allowance_stop_weekly=90)
        good_then_failed(self.q, 86400)
        b = self.build()[0]
        html = self.page(b, "#tab=health")[0]
        head = html.split('<div class="pane grid"', 1)[0]
        self.assertRegex(html.split("<h2>Allowance</h2>", 1)[1], r"Weekly: <b>95%</b> · 5-hour: 10% · read 2\.\d h ago")
        tile = re.search(r'<div class="k">Weekly allowance</div><div class="v">(.*?)</div>(.*?)<div class="d">(.*?)</div>', head, re.S)
        self.assertEqual(tile.group(1), "95%")
        self.assertIn('style="width:95%"', tile.group(2))  # the meter, from the good reading too
        self.assertIn("checkpoint 90%", tile.group(3))
        self.assertIn(" · resets ", tile.group(3))  # the good reading's weekly reset, not "reset unknown"
        self.assertNotIn("reset unknown", tile.group(3))
        self.assertRegex(tile.group(3), r"last good reading 2\.\d h ago")
        self.assertIn("allowance at the checkpoint: 95% of 90%", head)
        b["usage"]["usage_read"] = False  # no allowance command: the tile says so, as before
        head = self.page(b)[0].split('<div class="pane grid"', 1)[0]
        self.assertIn('<div class="v">usage unread</div>', head)
        self.assertNotIn("last good reading", head)

    def test_a_card_that_throws_shows_its_banner_and_the_rest_renders(self):
        self.seed()
        b = self.build()[0]
        b["now"]["allowance"] = {"latest_good": {"seven_day": "x"}}  # .toFixed throws: the tiles and the Allowance card
        b["usage"]["usage_read"] = True  # an allowance command is set: the tile shows the weekly figure
        b["usage"]["seats"] = {"implementer": None}
        b["runs"] = [{}]
        b["headless"] = [None]
        b["health"]["sources"] = {"events": None}
        b["now"]["open_runs"] = None
        html, _ = self.page(b)
        for name in ("Tiles", "Tokens by seat", "Runs with usage", "Headless runs", "Plane health", "Allowance",
                     "Now, in detail"):
            self.assertIn(f"⚠ {name} section failed", html, name)
        for t in ('aria-label="Now"', "Tokens per day, by seat", "Wall time per task", "Ready queue", "Burn-up",
                  'role="tablist"'):
            self.assertIn(t, html, t)
        self.assertEqual([k for k, _ in PANES.findall(html)], ["performance", "quality", "backlog", "queue", "health"])

    def test_a_tab_that_throws_says_so_and_the_strip_and_other_tabs_render(self):
        self.seed()
        b = self.build()[0]
        html, _ = self.page(b, "#tab=quality", patch=lambda t: t.replace(
            "function quality(Q, tasks) {", "function quality(Q, tasks) { throw new Error('boom <img>');", 1))
        body = dict(zip([k for k, _ in PANES.findall(html)], re.split(r'<div class="pane grid" id="pane-\w+"', html)[1:]))
        self.assertIn("⚠ Quality tab failed", body["quality"])
        self.assertIn("boom &lt;img&gt;", body["quality"])
        self.assertNotIn("<img", html)
        self.assertIn('aria-label="Now"', html.split('<div class="pane grid"', 1)[0])
        for tab, t in (("performance", "Wall time per task"), ("backlog", "ADR register"), ("queue", "Ready queue"),
                       ("health", "<h2>Plane health</h2>")):
            self.assertIn(t, body[tab], tab)


if __name__ == "__main__":
    unittest.main()
