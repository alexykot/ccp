"""The prompt-template and board-page helpers the tests share. Holds no tests.

What renders a page or a prompt: `phase_values`, `render_phase_values` and `PROMPT_TEMPLATES`, and `BoardPage`, a
mixin for a `TestCase` whose `page` runs the board page's script under node."""
from __future__ import annotations

import json
import re
import subprocess

from tests.helpers import PLANE_ROOT


class BoardPage:
    """Mixin for a `TestCase`: `page` runs the board page's script under node against a built board and
    returns the html it wrote and the drill panels it opened."""

    def page(self, b, h: str = "", patch=None):
        from ccp import board  # noqa: PLC0415
        from tests.board_drill_fixture import HASH_STUB
        js = (patch or (lambda t: t))(board.PAGE.read_text()).replace("/*__BOARD__*/null", board.embed(b)).split("<script>", 1)[1].split("</script>", 1)[0]
        loc = "globalThis.location = {hash: %s, pathname: '/b', search: ''};\n" % json.dumps(h)
        r = subprocess.run(["node", "-e", HASH_STUB + loc + js + "\nprocess.stdout.write(JSON.stringify({out: out.join(''), panel}));"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        return d["out"], d["panel"]


PROMPT_TEMPLATES = PLANE_ROOT / "templates" / "prompts"


def phase_values(**over) -> dict:
    """Every name the templates use, set to a placeholder, with the given overrides."""
    from ccp import prompt  # noqa: PLC0415
    names = set()
    for f in PROMPT_TEMPLATES.glob("*.md"):
        t = f.read_text()
        names |= set(prompt.VAR_RE.findall(t)) | {m[1] for m in re.findall(r"\{\{([#^/])(\w+)\}\}", t)}
    v = {n: f"<{n}>" for n in names}
    v.update(refactor=False, prior_reports="", note="", worker_env="", rules_doc="", fragment="", main_checkout="/m",
             accept_cache=False, review_cache=False, cold_gate=False, architect_checks="", pregate_lane="", cache_max_age_days="",
             budgets=False, resolution=False, resolved_verify=False, has_affected=False, has_old=False)
    v.update(over)
    return v


def render_phase_values(phase: str, **over) -> str:
    from ccp import prompt  # noqa: PLC0415
    return prompt.render_phase(phase, phase_values(**over))
