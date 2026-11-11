"""`ccp` — every command the plane runs inside a product checkout (SPEC §10, §19).

  ccp tasks list [--status S] | next [--scope IDS] [--allow-overdue REASON] [--explain] | check | index [--stdout]
  ccp tasks check --lease [--staged]  (a leased task's file edited on the integration branch, SPEC §10.5)
  ccp tasks orphans --since REF [--json]  (the lead: integration-branch commits no task covers, SPEC §10.7)
  ccp docs check
  ccp budgets check --base REF  (house-rule budgets on the files this change grew, SPEC §20.2)
  ccp tasks estimate ID | --all [--max N] [--detach]                           (the estimator seat, SPEC §26.3)
  ccp tasks estimate ID --baseline | --all --baseline [--dry-run] | show ID      (advisory, SPEC §26.3)
  ccp estimate accuracy [--json] | calibration [--json] | backfill [--dry-run]
  ccp forecast [--point R<n> | --backlog] [--json]     (completion and allowance, advisory, SPEC §26.4)
  ccp allowance status [--sample] | continue --to P --reason T
                | session-wake [--sample | --armed | --fire]  (the weekly checkpoint, the 5-hour wake, SPEC §25.4)
  ccp review-points [list|show R<n>] [--json] | tag R<n> [IDS] [--from-work] [--dry-run]
                    | migrate --from OLD --to R<n> [--dry-run] [--merge]     (the register, SPEC §22)
  ccp adr new TITLE | status N STATUS [--note T] | decide N Dn STATE [--by REF] [--note T]
          | supersede OLD NEW [--decisions D2,D4] [--by Dn] [--archive] | check | index [--stdout]
          | list [--json] | migrate --markers [--dry-run]                     (ADRs, SPEC §6)
  ccp architect due | run [--mode pass|shape] [--lens L,…] [--adr ID] [--force] [--detach] [--scope IDS]
               | triage <id> | status
  ccp health [--since DATE] [--json] | note --text T [--task ID] | record --task ID --metric k=v …
  ccp verify record FILE|- | merge-ok PR [--task ID] | check TASK_ID --head SHA

The seat toolkit (SPEC §10.4; every command needs QUEUE_ROOT and writes its own events):
  ccp tasks prefer [ID... [--reason T] | --clear]  (the lead: the runner's next tasks, in order, ahead of `next`'s own pick)
  ccp tasks hold [ID [--reason T] | --clear ID]  (the lead: `next` passes over a held task; no args: list)
  ccp tasks sign-off ID --by WHO --words T [--stage brief|build] [--head SHA]  (the lead records the operator's
            sign-off: claim needs a brief one, close every declared one, a build one at the head it merges, SPEC §3.5)
  ccp tasks claim ID | phase ID PHASE [--note T] | wait ID REASON [--until T] [--detail T]
            | resume ID REASON [--detail T] | close ID --pr N [--summary T]
            | sync [--dry-run]  (the queue follows the task log: done or dropped tasks lose waits and leases)
  ccp prompt implement|fix|review|verify ID [--pr N --head SHA] [--base SHA] [--worktree P] [--note T] [--supersede]
             [--allow-unreviewed-fix --reason T]
  ccp report RUN_ID FILE
  ccp runs gc [--dry-run]  (abandon runs that will never report: superseded by a later round, or
            of a done or dropped task, SPEC §11.1)
  ccp suite run [--lane NAME] [--run RUN_ID | --task ID [--phase P]] [--full | --summary] [--log PATH] [-- COMMAND …] | list [--task ID]
            (every test run: the exit code passes through, the output goes to a log and a summary is
            printed (--full streams it), the time and counts are recorded)
  ccp notify render TRIGGER [--task ID] [--id ID] [--reason R] [--json] | pending
            | sent TRIGGER [--task ID] [--id ID] --via command|lead [--note T]  (the operator's notices, SPEC §3.6)
  ccp plane propose --need T --generic T [--task ID] [--workaround T] [--frequency F] | propose --again ID
            | triage ID --accept|--merge-into ID|--decline --reason T | list [--open] | check
  ccp agent start|stop          (the SubagentStart / SubagentStop hooks; hook JSON on stdin)
  ccp init [--project-id ID] [--queue-root DIR] [--integration-branch B] [--gate CMD] [--starter-rules] [--force]
            (adopt this repository: footprint, binding and queue, SPEC §4.3, §8.3; the starter
            house rules, §20.5)

`tasks` and `docs check` are free and deterministic (`index` writes INDEX.yaml; `docs check` also
holds the house rules' shape and runs the product's `architect.checks`; every budget is `architect due`'s
and `health`'s; `budgets check` gates only on the files a change grew). With an `architect` block, `tasks next` reads the queue
(QUEUE_ROOT) and exits 4 while a pass or a triage is overdue (§19.6). `architect run` launches a
headless read-only Claude session; it and `health note|record` need QUEUE_ROOT. Exit codes: 0 ok,
1 check failures or a failed run, 2 usage or configuration, 3 not due / busy / nothing ready, 4 an
architect pass or triage is overdue, 5 the weekly allowance checkpoint (claim), 6 the session park:
the 5-hour window is at its park % (claim, prompt; §25.4), 7 the runner holds what it can: carry on
with the tasks in flight (next, claim; §16.3).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ccp.envvars import envvar
from ccp import config, pkgdocs, refs, rules, tasklog
from ccp.queue import QueueError


def _print_errs(label: str, errs: list[str], clean: str) -> int:
    if not errs:
        print(f"{label}: clean{clean}")
        return 0
    print(f"{label}: {len(errs)} failure(s)")
    for e in errs:
        print(f"  {e}")
    return 1


def cmd_tasks_list(cfg: config.Config, a: argparse.Namespace) -> int:
    rows = [(t.get("task_id") or "?", t.get("status") or "?", t.get("title") or "",
             ",".join(tasklog._as_list(t.get("depends_on"))) or "-", tasklog.kind_of(t))
            for t in tasklog.load(cfg) if not a.status or t.get("status") == a.status]
    if a.json:
        print(json.dumps([dict(zip(("task_id", "status", "title", "depends_on", "kind"), r)) for r in rows], indent=2))
        return 0
    if rows:
        w = max(28, *(len(r[0]) for r in rows))
        print(f"{'TASK':<{w}} {'STATUS':<12} {'TITLE':<52}   DEPS")
        for r in rows:
            print(f"{r[0]:<{w}} {r[1]:<12} {r[2][:52]:<52}   {r[3]}".rstrip())
    return 0


def _architect_gate(cfg: config.Config, a: argparse.Namespace, scope: list[str] | None,
                    t: dict | None) -> int | None:
    """§19.6 at `next`: exit 4 (printing why and what to do) while a pass or a triage is overdue.
    None lets `next` go on; architect notices go to stderr either way."""
    from ccp import architect, health  # noqa: PLC0415  (only products with an architect block pay for it)
    q = architect.queue_root(required=False)
    if q is None:
        print("ccp tasks next: this product has an architect block (SPEC §19.6): set QUEUE_ROOT to its runtime "
              "queue so `next` can check the architect's passes", file=sys.stderr)
        return 2
    g = architect.gate(cfg, q, scope, t)
    for n in g["notices"]:
        print(f"architect: {n}", file=sys.stderr)
    if not g["blocked"]:
        return None
    if a.allow_overdue is not None:
        if not a.allow_overdue.strip():
            print("ccp tasks next: --allow-overdue needs a reason", file=sys.stderr)
            return 2
        try:
            health.add_note(q, f"allow-overdue: {a.allow_overdue.strip()} (was: {g['blocked']})",
                            str(t.get("task_id")) if t else None, os.environ.get("ACTOR") or "task-runner",
                            "allow-overdue")
        except ValueError as e:
            print(f"ccp tasks next: --allow-overdue: {e}", file=sys.stderr)
            return 2
        print(f"architect: overridden once ({g['blocked']}); recorded as a friction note", file=sys.stderr)
        a.board_dirty = True
        return None
    if a.json:
        print(json.dumps({"task_id": None, "architect": {k: g.get(k) for k in ("blocked", "kind", "review_id", "action")}},
                         indent=2))
    else:
        print(g["blocked"])
        print(f"  {g['action']} (SPEC §19.6)")
        print('  override once, on the owner\'s word: ccp tasks next --allow-overdue "<reason>"')
    return 4


def cmd_tasks_next(cfg: config.Config, a: argparse.Namespace) -> int:
    from ccp import selection  # noqa: PLC0415  (the board's ready queue reads the same function, §20)
    scope = [s.strip() for s in (a.scope or "").split(",") if s.strip()] or None
    q = os.environ.get("QUEUE_ROOT")
    sel = selection.pick(cfg, Path(q) if q else None, scope)
    scope = sel["scope"]
    if sel["scope_from_work"]:
        print(f"ccp tasks next: scope from work.json ({len(scope)} task(s))", file=sys.stderr)
    for note in sel["prefer_notes"]:
        print(f"ccp tasks next: {note}", file=sys.stderr)
    for tid in sel["passed_over"]:  # §10.4: the lead's holds
        h = sel["held"].get(tid) or {}
        print(f"ccp tasks next: passed over {tid}: held ({', '.join(x for x in (h.get('by') or '?', h.get('reason')) if x)}; "
              f"`ccp tasks hold --clear {tid}`)", file=sys.stderr)
    if getattr(a, "explain", False):
        _explain(cfg, sel)
    from ccp import parallel  # noqa: PLC0415  (§16.3: the board's ready queue reads the same choice)
    choice = parallel.next_choice(cfg, Path(q) if q else None, sel)
    t, why = choice["pick"] or (None, None)
    why = why or None
    if cfg.architect is not None:
        code = _architect_gate(cfg, a, scope, t)
        if code is not None:
            return code
    if choice["slots_full"]:
        return _slots_full(a, choice["slots_full"])
    if a.json:
        print(json.dumps(None if not t else {
            "task_id": t.get("task_id"), "title": t.get("title"), "path": cfg.rel(t["_file"]),
            "kind": tasklog.kind_of(t), "why": why,
            "spec_refs": tasklog._as_list(t.get("spec_refs")),
            "adr_refs": tasklog._as_list(t.get("adr_refs")),
            "rule_refs": tasklog._as_list(t.get("rule_refs")),
            "review_refs": tasklog._as_list(t.get("review_refs")), "checks": t["_checks"]}, indent=2))
        return 0 if t else 3
    if not t:
        print("nothing ready" + (" in scope" if scope else "")
              + ": every pending task is blocked on a dependency, or all are done")
        return 3
    print(f"{t['task_id']}  {t.get('title')}")
    print(f"  file:      {cfg.rel(t['_file'])}")
    if tasklog.kind_of(t) != "feature":
        print(f"  kind:      {tasklog.kind_of(t)}")
    for k in dict.fromkeys([*cfg.task_log["refs_any"], *tasklog.kind_refs(cfg, tasklog.kind_of(t))]):
        print(f"  {k + ':':<10} {', '.join(tasklog._as_list(t.get(k))) or '-'}")
    print(f"  checks:    {', '.join(t['_checks'])}")
    if why:
        print(f"  why:       {why}")
    return 0


def _slots_full(a: argparse.Namespace, held: dict) -> int:
    """§16.3: exit 7, the runner carries on with what it holds (exit 3 stays "nothing ready")."""
    from ccp import parallel  # noqa: PLC0415
    if a.json:
        print(json.dumps({"slots_full": True, **held}, indent=2))
    else:
        head = f"{held['head']} waits: " if held.get("head") else ""
        print(f"slots full: {head}{held['reason']}. Carry on with {', '.join(held['in_flight'])} (SPEC §16.3)")
    return parallel.EXIT_SLOTS


def _explain(cfg: config.Config, sel: dict) -> None:
    """`ccp tasks next --explain`: the full ranked queue on stderr, held tasks marked, the pick first."""
    held = sel["held"]
    rows = sel["ranked_all"]
    pick = sel["ranked"][0][0].get("task_id") if sel["ranked"] else None
    print(f"ccp tasks next --explain: {len(rows)} ready, {len(sel['passed_over'])} held", file=sys.stderr)
    for n, (t, why) in enumerate(rows, 1):
        tid = str(t.get("task_id"))
        mark = "held" if tid in held else ("next" if tid == pick else "")
        h = held.get(tid) or {}
        extra = f" held by {h.get('by') or '?'}" + (f": {h['reason']}" if h.get("reason") else "") if tid in held else ""
        print(f"  {n:>2}. {mark:<4} {tid}  {t.get('title') or ''}{'  — ' + why if why else ''}{extra}", file=sys.stderr)
    for tid in sorted(set(held) - {str(t.get('task_id')) for t, _ in rows}):
        h = held[tid]
        print(f"   -  held {tid}  (not ready now){': ' + h['reason'] if h.get('reason') else ''}", file=sys.stderr)


def cmd_tasks_lease_check(cfg: config.Config, a: argparse.Namespace) -> int:
    """`ccp tasks check --lease [--staged]` (§10.5): a claimed task's file is edited only in its PR. Exit 1
    naming each edit on the integration branch to a task file with a live lease, 2 without QUEUE_ROOT."""
    from ccp import lifecycle, queue  # noqa: PLC0415
    try:
        q = queue.root()
    except QueueError as e:
        print(f"ccp tasks check --lease: {e}", file=sys.stderr)
        return 2
    integ = queue.integration_branch(q)
    errs = [f"{e['task_id']}: leased by {e['holder']}, and its task file {e['file']} "
            + (f"is changed in the commit staged on {integ}" if e["sha"] is None
               else f"changed on {integ} in {e['sha'][:7]} {e['subject']!r}")
            + ". A claimed task's file changes only in its PR: send a ruling or clarification to the runner holding the task;"
            + " any other change (intent, scope, dod_checks, id, dependencies) needs the task released or superseded first (SPEC §10.5)"
            for e in lifecycle.lease_edits(cfg, q, staged=a.staged)]
    return _print_errs("tasks --lease", errs, " (no leased task's file edited on " + integ + ")")


def cmd_tasks_check(cfg: config.Config, a: argparse.Namespace) -> int:
    if getattr(a, "staged", False) and not getattr(a, "lease", False):
        print("ccp tasks check: --staged goes with --lease", file=sys.stderr)
        return 2
    if getattr(a, "lease", False):
        return cmd_tasks_lease_check(cfg, a)
    errs = tasklog.check(cfg)
    code = _print_errs("tasks", errs, f" ({len(tasklog.load(cfg))} tasks)")
    from ccp import reviewpoints  # noqa: PLC0415
    from ccp import parallel  # noqa: PLC0415
    for w in tasklog.warnings(cfg) + reviewpoints.notes(cfg) + parallel.scope_warnings(cfg, tasklog.load(cfg)):
        print(f"  warning: {w}")
    from ccp import estimator  # noqa: PLC0415  (§26.3: advisory; never changes the exit code)
    for n in estimator.notice(cfg):
        print(f"  note: {n}")
    return code


def cmd_tasks_index(cfg: config.Config, a: argparse.Namespace) -> int:
    gone = tasklog.missing_task_files(cfg)
    if gone:
        return _print_errs("tasks index: refused", gone, "")
    if not cfg.task_log.get("index", True):
        print("tasks index: this product keeps no index (task_log.index is false, SPEC §5.7)", file=sys.stderr)
        return 0
    if a.stdout:
        sys.stdout.write(tasklog.render_index(cfg))
    else:
        print(f"wrote {tasklog.write_index(cfg)}")
        from ccp import estimator  # noqa: PLC0415  (§26.3: the task-writing flow's trigger; advisory)
        for n in estimator.notice(cfg):
            print(f"  note: {n}")
    return 0


PLANE_PATH_SKIP = ("docs/delivery/tasks/", "docs/delivery/reviews/", ".control-plane/")


def plane_path_warnings(cfg: config.Config) -> list[str]:
    """SPEC §4.4: product docs name the plane in one line and restate none of it. A plane checkout
    path in a tracked product file is a warning (the task log and reviews are history, and exempt)."""
    import subprocess  # noqa: PLC0415
    r = subprocess.run(["git", "-C", str(cfg.root), "grep", "-l", "-I", "-E",
                        r"/control-plane(-run)?/(bin/ccp|scripts/|templates/|plugin/|projects/|SPEC\.md)"],
                       capture_output=True, text=True)
    return [f"{f}: names a control-plane checkout path; say `ccp`, or point at the plane in one line (SPEC §4.4)"
            for f in r.stdout.split() if not f.startswith(PLANE_PATH_SKIP)]


def cmd_docs_history_paths(cfg: config.Config, a: argparse.Namespace) -> int:
    from ccp import docrules  # noqa: PLC0415
    attr = a.attr or ((cfg.package_docs or {}).get("rules") or {}).get("history_attr")
    if not attr:
        print("ccp docs history-paths: name the attribute (--attr) or set package_docs.rules.history_attr",
              file=sys.stderr)
        return 2
    for p in sorted(docrules.history_paths(cfg, attr)):
        print(p)
    return 0


def cmd_docs_check(cfg: config.Config, _a: argparse.Namespace) -> int:
    # The task log and the house rules are part of the documentation contract: one command, one gate.
    from ccp import adr  # noqa: PLC0415
    docs_checks = [f"docs check {e}" for e in rules.run_checks(cfg, cfg.docs["checks"])]  # §21.5 docs.checks
    code = _print_errs("docs", pkgdocs.check(cfg) + tasklog.check(cfg) + rules.check(cfg) + rules.starter_check(cfg)
                       + adr.check(cfg) + docs_checks, "")
    for n in rules.starter_notes(cfg):  # §20.5: what the product declined, and the checks that skips
        print(f"  {n}")
    from ccp import reviewpoints  # noqa: PLC0415
    warns = plane_path_warnings(cfg) + reviewpoints.notes(cfg) + adr.warnings(cfg) + pkgdocs.notes(cfg)
    for w in warns:
        print(f"  warning: {w}")
    if warns:
        print("  (warnings are not failures: the gate is the line above)")
    return code


def cmd_budgets_check(cfg: config.Config, a: argparse.Namespace) -> int:
    """SPEC §20.2: the house-rule budgets on the files this change touches (the implementer's pre-gate
    and the verifier's gate). Exit 1 when the change grew a file over its budget."""
    try:
        r = rules.budget_check(cfg, a.base)
    except (ValueError, OSError) as exc:  # exit 1 is a budget failure only; anything else is 2
        print(f"ccp budgets check: {exc}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(r, indent=2, default=str))
        return 1 if r["failures"] else 0
    for row in r["failures"]:
        print(f"budgets: {row['text']}")
    for row in r["warnings"]:
        print(f"  warning: {row['text']}")
    print(f"budgets: {'FAIL' if r['failures'] else 'ok'} ({r.get('note') or str(r['touched']) + ' file(s) touched since ' + str(r['merge_base'])[:12]})")
    return 1 if r["failures"] else 0


def cmd_wt(cfg: config.Config, a: argparse.Namespace) -> int:
    """SPEC §12.1: worktrees and environments."""
    from ccp import wt  # noqa: PLC0415
    try:
        q = wt._queue_root()
        command = list(getattr(a, "command", None) or [])
        if command and not (a.action == "create" and a.kind == "base"):
            raise QueueError("only `ccp wt create --kind base` runs a command after `--`", 2)
        if a.action == "create":
            if not a.task:
                raise QueueError("usage: ccp wt create --kind KIND --task ID [--sha SHA] [--name N] [--seat S] [--tag T] "
                                 "[-- COMMAND (base only)]", 2)
            from ccp.queue import task_meta  # noqa: PLC0415
            tid = str(task_meta(cfg, a.task)["task_id"])
            if a.kind == "base":  # §12.1: made, the command run there, removed again; exit with its code
                res = wt.run_on_base(cfg, q, tid, a.sha or "", command, a.name, a.seat, a.tag)
                for w in res["warnings"]:
                    print(f"warning: {w}", file=sys.stderr)
                print(json.dumps(res, indent=2, ensure_ascii=False))
                return int(res["exit"])
            body: object = wt.create(cfg, q, tid, a.kind or "impl", a.sha, a.name, a.seat, a.tag)
        elif a.action == "list":
            body = wt.listing(cfg, q, a.task)
        elif a.action == "gc":
            body = wt.gc(cfg, q)
        else:
            if not a.name_arg:
                raise QueueError(f"usage: ccp wt {a.action} NAME", 2)
            name = a.name_arg
            if a.action == "remove":
                body = {"ok": True, "removed": name, "warnings": wt.remove(cfg, q, name)}
            elif a.action == "up":
                body = wt.up(cfg, q, name)
            elif a.action == "down":
                body = wt.down(cfg, q, name)
            else:
                body = wt.urls(cfg, q, name)
    except QueueError as e:
        print(f"ccp wt {a.action}: {e}", file=sys.stderr)
        return e.code
    if isinstance(body, dict):
        for w in body.get("warnings") or []:
            print(f"warning: {w}", file=sys.stderr)
    print(json.dumps(body, indent=2, ensure_ascii=False))
    return 0


def cmd_wt_exec(a: argparse.Namespace, args: list[str]) -> int:
    """SPEC §12.1: run (or print) a worktree's own bin/ccp. It needs no plane.json, so a change the
    installed ccp cannot load can still be tried."""
    from ccp import wt  # noqa: PLC0415
    try:
        if a.print_path and args:
            raise QueueError("--print runs nothing: give no arguments after `--`", 2)
        exe = wt.own_ccp(None if a.name_arg is not None else config.find_root(a.root), a.name_arg)
    except QueueError as e:
        print(f"ccp wt exec: {e}", file=sys.stderr)
        return e.code
    except config.ConfigError as e:
        print(f"ccp wt exec: {e}", file=sys.stderr)
        return 2
    if a.print_path:
        print(exe)
        return 0
    return wt.exec_ccp(exe, args)


def cmd_auth(cfg: config.Config, a: argparse.Namespace) -> int:
    """SPEC §30: run plane.json auth_check.probes; exit 1 when one fails."""
    from ccp import wt  # noqa: PLC0415
    q = os.environ.get("QUEUE_ROOT")
    body = wt.auth_check(cfg, Path(q) if q and Path(q).is_dir() else None)
    if not (cfg.auth_check or {}).get("probes"):
        body["note"] = "plane.json declares no auth_check.probes"
    print(json.dumps(body, indent=2, ensure_ascii=False))
    return 0 if body["ok"] else 1


def cmd_adr(cfg: config.Config, a: argparse.Namespace) -> int:
    """SPEC §6.6: the ADR tool. `ccp docs adr index|list` is the same command."""
    from ccp import adr  # noqa: PLC0415
    try:
        if a.action == "new":
            f = adr.new(cfg, " ".join(a.args))
            print(f"wrote {cfg.rel(f)} (status proposed); fill in its decisions, then `ccp adr status {f.name[:f.name.index('-')]} accepted`")
            return 0
        if a.action == "status":
            if len(a.args) != 2:
                raise adr.AdrError("usage: ccp adr status N STATUS [--note T]")
            r = adr.set_status(cfg, a.args[0], a.args[1], a.note)
            print(f"{r['path']}: status {r['status']}" + (f"; decisions: {', '.join(r['decisions'])}" if r.get("decisions") else ""))
            return 0
        if a.action == "decide":
            if len(a.args) != 3:
                raise adr.AdrError("usage: ccp adr decide N Dn STATE [--by REF] [--note T]")
            r = adr.decide(cfg, a.args[0], a.args[1], a.args[2], a.by, a.note)
            print(f"{r['path']}: {r['decision']} {r['state']}")
            return 0
        if a.action == "supersede":
            if len(a.args) != 2:
                raise adr.AdrError("usage: ccp adr supersede OLD NEW [--decisions D2,D4] [--by Dn] [--archive]")
            r = adr.supersede(cfg, a.args[0], a.args[1], a.decisions.split(",") if a.decisions else None, a.by, a.archive)
            print(f"{r['new']} supersedes {', '.join(r['supersedes'])}" + (f"; moved to {r['archived_to']}" if r["archived_to"] else ""))
            return 0
        if a.action == "migrate":
            if not a.markers:
                raise adr.AdrError("usage: ccp adr migrate --markers [--dry-run]")
            r = adr.migrate_markers(cfg, a.dry_run)
            for row in r["files"]:
                if row["changed"] or row.get("error"):
                    print(f"{'would rewrite' if a.dry_run else 'rewrote'} {row['path']}: {row['changed']} decision marker(s)"
                          + (f" — {row['error']}" if row.get("error") else ""))
            for path, dec in r["left"]:
                print(f"left      {path}: {dec} is one item of a list of other things; rewrite it by hand")
            print(f"{r['changed_files']} file(s), {r['changed_lines']} marker(s) {'to rewrite' if a.dry_run else 'rewritten'}"
                  + (f", {len(r['left'])} left" if r["left"] else ""))
            return 1 if r["errors"] else 0
    except adr.AdrError as e:
        print(f"ccp adr {a.action}: {e}", file=sys.stderr)
        return e.code
    except adr.ParseError as e:
        print(f"ccp adr {a.action}: {e}", file=sys.stderr)
        return 2
    if a.action == "check":
        if cfg.adr is None:
            print("ccp adr check: plane.json has no adr block (SPEC §6.1)", file=sys.stderr)
            return 2
        _, errs, warns = adr.analyse(cfg)
        code = _print_errs("adr", errs, "")
        for w in warns:
            print(f"  warning: {w}")
        return code
    if a.action == "index":
        if not cfg.adr or not cfg.adr.get("index"):
            print("ccp adr index: plane.json has no adr.index (SPEC §6.1)", file=sys.stderr)
            return 2
        if a.stdout:
            sys.stdout.write(adr.render_index(cfg))
        else:
            print(f"wrote {adr.write_index(cfg)}")
        return 0
    metas, errs = adr.load(cfg, getattr(a, "dir", None))
    if a.json:
        print(json.dumps({"adrs": [adr.public(m) for m in metas], "errors": errs}, indent=2, default=str))
    else:
        for m in metas:
            pts = m.get("review_points") if isinstance(m.get("review_points"), list) else []
            b = adr.built(m)
            print(f"{m.get('id', '?'):<9} {str(m.get('status') or '?'):<12} {str(m.get('date') or ''):<10} "
                  f"{str(m.get('title') or '')[:70]}" + ("  (archived)" if m.get("_archived") else "")
                  + (f"  [{', '.join(map(str, pts))}]" if pts else "")
                  + (f"  built {b[0]}/{b[1]}" if b and b[1] else "  all decisions retired" if b else ""))
    return 0


def cmd_architect(cfg: config.Config, a: argparse.Namespace) -> int:
    from ccp import architect
    return architect.main(cfg, a)


def cmd_verify(cfg: config.Config, a: argparse.Namespace) -> int:
    from ccp import verify
    return verify.main(cfg, a)


def cmd_health(cfg: config.Config, a: argparse.Namespace) -> int:
    from ccp import health
    return health.main(cfg, a)


def _toolkit(fn) -> object:
    """Run a §10 toolkit command: JSON on stdout; a refusal on stderr with its exit code."""
    def run(cfg: config.Config, a: argparse.Namespace) -> int:
        try:
            out = fn(cfg, a)
        except QueueError as e:
            print(f"ccp {a.group}: {e}", file=sys.stderr)
            return e.code
        body, code = out if isinstance(out, tuple) else (out, 0)
        for w in body.get("warnings") or []:
            print(f"warning: {w}", file=sys.stderr)
        print(json.dumps(body, indent=2, ensure_ascii=False))
        return code
    return run


def _lifecycle(cfg: config.Config, a: argparse.Namespace):
    from ccp import lifecycle
    if a.cmd == "claim":
        return lifecycle.claim(cfg, a.task, a.holder)
    if a.cmd == "worktree":
        return lifecycle.runner_worktree(cfg, a.runner)
    if a.cmd == "prefer":
        a.board_dirty = bool(a.tasks) or a.clear  # §28: a set or a clear changes the Now panel
        return lifecycle.prefer(cfg, a.tasks, (a.reason or "").strip(), a.clear)
    if a.cmd == "hold":
        a.board_dirty = a.task is not None or a.clear is not None  # §28: the Now panel shows holds
        return lifecycle.hold(cfg, a.task, (a.reason or "").strip(), a.clear)
    if a.cmd == "release":
        return lifecycle.release(cfg, a.task, (a.reason or "").strip())
    if a.cmd == "sign-off":
        return lifecycle.sign_off(cfg, a.task, a.stage, a.by or "", a.words or "", a.head)
    if a.cmd == "drop":
        return lifecycle.drop(cfg, a.task, (a.reason or "").strip())
    if a.cmd == "phase":
        return lifecycle.phase(cfg, a.task, a.phase, a.note or "")
    if a.cmd in ("wait", "resume"):
        return lifecycle.wait(cfg, a.task, "set" if a.cmd == "wait" else "clear", a.reason,
                              getattr(a, "until", None), a.detail)
    if a.cmd == "sync":
        body = lifecycle.sync(cfg, a.dry_run)
        a.board_dirty = bool(body["changed"]) and not a.dry_run  # §28.3: the board follows a sync that wrote
        return body
    return lifecycle.close(cfg, a.task, a.pr, a.summary or "")


def _est_queue(what: str) -> Path | None:
    q = os.environ.get("QUEUE_ROOT")
    if q and Path(q).is_dir():
        return Path(q)
    print(f"ccp {what}: set QUEUE_ROOT to this project's runtime queue (SPEC §26.5)", file=sys.stderr)
    return None


def cmd_tasks_estimate(cfg: config.Config, a: argparse.Namespace) -> int:
    """§26: `tasks estimate ID --baseline`, `--all --baseline`, `show ID`. Advisory records only."""
    from ccp import estimate  # noqa: PLC0415
    q = _est_queue("tasks estimate")
    if q is None:
        return 2
    args = list(a.args or [])
    if args[:1] == ["show"]:
        if len(args) != 2:
            print("ccp tasks estimate show: give one task id", file=sys.stderr)
            return 2
        try:
            tid = str(config_task(cfg, args[1]))
        except QueueError as e:
            print(f"ccp tasks estimate: {e}", file=sys.stderr)
            return 2
        from ccp import calibrate  # noqa: PLC0415  (phase D: raw and calibrated)
        rs = estimate.rows(q, tid)
        cal = calibrate.model(q, cfg)
        if a.json:
            print(json.dumps({"task_id": tid, "rows": rs, "latest": {s: estimate.latest(rs, s) for s in
                                                                    (*estimate.SOURCES, "actual")},
                              "calibrated": {s: estimate.latest(rs, s, calibrated=True, cal=cal) for s in estimate.SOURCES}},
                             indent=2))
        else:
            print(estimate.show_text(tid, rs, cal))
        return 0
    if a.all == bool(args):
        print("ccp tasks estimate: give one task id, or --all", file=sys.stderr)
        return 2
    if not a.baseline:
        return _tasks_estimate_agent(cfg, q, a, args)
    try:
        body = estimate.estimate_tasks(cfg, q, None if a.all else args, a.dry_run, a.force)
    except QueueError as e:
        print(f"ccp tasks estimate: {e}", file=sys.stderr)
        return e.code
    a.board_dirty = bool(body["written"])
    if a.json:
        print(json.dumps(body, indent=2, ensure_ascii=False))
        return 0
    for r in body["tasks"]:
        print(f"{r['task_id']}: {r['action']} ({r['reason']})" + (f"\n  {estimate.row_text(r['row'])}" if r.get("row") else ""))
    print(f"{body['written']} row(s) written" + (" (dry run: nothing written)" if a.dry_run else ""))
    return 0


def _tasks_estimate_agent(cfg: config.Config, q: Path, a: argparse.Namespace, args: list[str]) -> int:
    """§26.3 phase B: the estimator seat (ccp/estimator.py). Advisory rows only."""
    from ccp import estimator  # noqa: PLC0415
    if a.print_prompt:
        if len(args) != 1:
            print("ccp tasks estimate --print-prompt: give one task id", file=sys.stderr)
            return 2
        try:
            sys.stdout.write(estimator.prompt_for(cfg, q, args[0]))
        except QueueError as e:
            print(f"ccp tasks estimate: {e}", file=sys.stderr)
            return e.code
        return 0
    if a.max < 1:
        print("ccp tasks estimate: --max must be at least 1", file=sys.stderr)
        return 2
    if a.detach:
        if args or a.dry_run:
            print("ccp tasks estimate --detach: only with --all, and not with --dry-run", file=sys.stderr)
            return 2
        if estimator.running(q):
            print("ccp tasks estimate: an estimator batch is already running", file=sys.stderr)
            return 3
        body = estimator.spawn(cfg, q, a.max, a.actor or "system")
        print(json.dumps(body, indent=2) if a.json else f"started {body['run_id']} in the background; log {body['log']}")
        return 0
    try:
        body = estimator.run(cfg, q, None if a.all else args, a.max, a.dry_run, a.force, a.actor or "system", a.run_id)
    except QueueError as e:
        print(f"ccp tasks estimate: {e}", file=sys.stderr)
        return e.code
    a.board_dirty = bool(body.get("written"))
    print(json.dumps(body, indent=2, ensure_ascii=False) if a.json else estimator.run_text(body))
    return 3 if not body.get("ok") else 1 if body.get("failed") else 0


def config_task(cfg: config.Config, task: str) -> str:
    from ccp.queue import task_meta  # noqa: PLC0415
    return str(task_meta(cfg, task)["task_id"])


def cmd_forecast(cfg: config.Config, a: argparse.Namespace) -> int:
    """§26.4 phase C: the review point's and the backlog's completion, tokens, cost and weekly %."""
    from ccp import forecast  # noqa: PLC0415
    q = _est_queue("forecast")
    if q is None:
        return 2
    f = forecast.run(cfg, q, a.point)
    if a.json:
        print(json.dumps(f, indent=2))
    else:
        print(forecast.text(f, "backlog" if a.backlog else "point" if a.point else None))
    return 0


def cmd_estimate(cfg: config.Config, a: argparse.Namespace) -> int:
    """§26.6: `estimate accuracy [--json]`, `estimate calibration [--json]`, `estimate backfill [--dry-run] [--json]`."""
    from ccp import estimate  # noqa: PLC0415
    q = _est_queue("estimate")
    if q is None:
        return 2
    if a.action == "accuracy":
        acc = estimate.accuracy(estimate.all_rows(q))
        print(json.dumps(acc, indent=2) if a.json else estimate.accuracy_text(acc))
        return 0
    if a.action == "calibration":
        from ccp import calibrate  # noqa: PLC0415
        m = calibrate.model(q, cfg)
        print(json.dumps(calibrate.summary(m), indent=2) if a.json else calibrate.text(m))
        return 0
    body = estimate.backfill(cfg, q, a.dry_run)
    a.board_dirty = not a.dry_run and bool(body["baselines"] or body["actuals"])
    if a.json:
        print(json.dumps(body, indent=2))
        return 0
    print(f"{body['tasks']} completed task(s) with a wall time: {body['baselines']} baseline(s) and {body['actuals']} actual "
          f"row(s) {'to write' if a.dry_run else 'written'}; {body['kept']} already estimated; {body['no_pool']} with "
          f"no earlier task to compare with" + (" (dry run: nothing written)" if a.dry_run else ""))
    print(estimate.accuracy_text(body["accuracy"]))
    return 0


def cmd_tasks_orphans(cfg: config.Config, a: argparse.Namespace) -> int:
    from ccp import health  # noqa: PLC0415
    return health.orphans_main(cfg, a)


def cmd_tasks_backfill(cfg: config.Config, a: argparse.Namespace) -> int:
    """§22.6: one line per done task without a point (task, point, evidence), then the counts; --json the body."""
    from ccp import backfill  # noqa: PLC0415
    try:
        body = backfill.backfill(cfg, a.dry_run)
    except QueueError as e:
        print(f"ccp tasks: {e}", file=sys.stderr)
        return e.code
    for w in body.get("warnings") or []:
        print(f"warning: {w}", file=sys.stderr)
    if a.json:
        print(json.dumps(body, indent=2, ensure_ascii=False))
        return 0
    for r in body["tasks"]:
        if r.get("how") == "log":
            ev = f"log: {r['log']}" + (f"; the ledger says {r['ledger_says'] or 'nothing'}" if "ledger_says" in r else "")
        elif r.get("spawn_at"):
            ev = f"{r['how']}: spawn {r['spawn_at']}" + (f", scope {r['scope_hit']}" if r.get("scope_hit") else ", not in scope")
        else:
            ev = r.get("why") or ""
        tail = f" [not stamped: {r['why']}]" if r["action"] == "skip" else ""
        print(f"{r['task_id']} -> {r['review_point'] or '-'}  (claim {r['claim_at'] or '?'} from {r['claim_from']}; {ev}){tail}")
    counts = ", ".join(f"{k} {v}" for k, v in body["counts"].items()) or "none"
    print(f"\n{len(body['tasks'])} done tasks without a review point: {counts}. Already set: {body['already_set']}. "
          f"To stamp: {body['to_stamp']}; not an accepted review point (task_log.review_point_pattern, or the register once it exists): {body['skipped_pattern']}.")
    if body["written"]:
        print(f"Written (working tree only, nothing committed): {len(body['written'])} files. Review the diff, then "
              f"commit them as one change:\n  {body['commit']}")
    elif not a.dry_run:
        print("Nothing written.")
    return 0


def _rp_line(g: dict) -> str:
    st = g.get("status") or ("not in the register" if not g.get("in_register") else "?")
    o = g.get("open") or {}
    opn = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in o.items() if v) or "none open"
    dates = " ".join(x for x in (f"opened {g['opened']}" if g.get("opened") else "",
                                 f"closed {g['closed']}" if g.get("closed") else "") if x)
    return (f"{'*' if g.get('current') else ' '} {g['id']:<5} {str(g.get('name') or '–')[:40]:<40} {st:<8} "
            f"{g['done']}/{g['tasks']} done, {opn}{'  ' + dates if dates else ''}{'  (runner)' if g.get('runner') else ''}")


def cmd_review_points(cfg: config.Config, a: argparse.Namespace) -> int:
    """§22: the review-point register: list, show, tag, migrate."""
    from ccp import reviewpoints as rp  # noqa: PLC0415
    action = a.action or "list"
    if action in ("tag", "migrate"):
        try:
            if action == "tag":
                body = rp.tag(cfg, a.point or "", a.ids, a.from_work, a.dry_run)
            else:
                if not (a.from_ and a.to):
                    print("ccp review-points migrate: needs --from OLD --to R<n>", file=sys.stderr)
                    return 2
                body = rp.migrate(cfg, a.from_, a.to, a.dry_run, a.merge)
        except (rp.RegisterError, QueueError) as e:
            print(f"ccp review-points: {e}", file=sys.stderr)
            return e.code
        a.board_dirty = not a.dry_run and bool(body.get("written") or (body.get("queue") or {}).get("written"))
        for w in body.get("warnings") or []:
            print(f"warning: {w}", file=sys.stderr)
        if a.json:
            print(rp.dumps(body))
            return 0
        if action == "tag":
            for r in body["tasks"]:
                print(f"{r['action']:<8} {r['task_id']}  ({r['status']})")
        else:
            print(f"{len(body['tasks'])} task file(s) carry review_point: {body['from']} -> {body['to']}"
                  + ("" if not body["tasks"] else ": " + ", ".join(refs.ids(cfg).task_number(r["task_id"]) for r in body["tasks"])))
            qb = body.get("queue")
            if qb:
                wj = qb["work_json"]
                print(f"queue {qb['path']}: work.json review_point {wj['review_point'] or '–'}"
                      + (f" -> {body['to']}" if wj["change"] else " (unchanged)")
                      + f"; ledger: {qb['ledger']['events']} runner event(s) name {body['from']} (history, not rewritten"
                      + ("; a rename event maps them" if qb["ledger"]["events"] or wj["change"] else "") + ")")
            if body.get("product_log"):
                pl = body["product_log"]
                print(f"product log {pl['path']}: {pl['tasks']} close entr{'y' if pl['tasks'] == 1 else 'ies'} name "
                      f"{body['from']} (history, not rewritten)")
        if a.dry_run:
            print("Dry run: nothing written.")
        elif body.get("written"):
            print(f"Written (working tree only, nothing committed): {len(body['written'])} file(s). Review the diff, "
                  f"then commit them as one change:\n  {body['commit']}")
        else:
            print("No task file to change.")
        return 0
    from ccp.queue import load_work  # noqa: PLC0415
    entries, errs = rp.load(cfg)
    q = os.environ.get("QUEUE_ROOT")
    work = load_work(Path(q)) if q and Path(q).is_dir() else {}
    groups = rp.summary(rp.task_rows(tasklog.load(cfg)), work, entries, tasklog.in_scope, refs.ids(cfg))
    if action == "show":
        g = next((x for x in groups if x["id"] == a.point), None)
        if g is None:
            print(f"ccp review-points show: no review point {a.point!r} in the register or on any task", file=sys.stderr)
            return 2
        if a.json:
            print(rp.dumps(g))
            return 0
        print(_rp_line(g).strip())
        if g.get("goal"):
            print("\n" + "\n".join("  " + x for x in str(g["goal"]).splitlines()))
        print(f"\nOpen ({len(g['open_ids'])}): {', '.join(g['open_ids']) or 'none'}")
        print(f"Done: {g['done']} of {g['tasks']}" + (f"; {g['dropped']} dropped" if g["dropped"] else ""))
        return 0
    if a.json:
        print(rp.dumps({"register": cfg.rel(rp.path(cfg)), "exists": entries is not None, "errors": errs,
                        "review_points": groups}))
        return 1 if errs else 0
    for w in rp.notes(cfg, entries):
        print(f"warning: {w}", file=sys.stderr)
    for g in groups:
        print(_rp_line(g))
    for e in errs:
        print(f"  problem: {e}")
    return 1 if errs else 0


def _prompt(cfg: config.Config, a: argparse.Namespace):
    from ccp import prompt
    return prompt.build(cfg, a)


def _report(cfg: config.Config, a: argparse.Namespace):
    from ccp import report
    return report.submit(cfg, a.run_id, a.file)


def _runs_gc(cfg: config.Config, a: argparse.Namespace):
    from ccp import runs
    body = runs.gc(cfg, a.dry_run)
    a.board_dirty = bool(body["abandoned"]) and not a.dry_run  # §28: the Seats table follows
    return body


def _suite_list(cfg: config.Config, a: argparse.Namespace):
    from ccp import suite
    return suite.listing(cfg, a)


def _mutate(cfg: config.Config, a: argparse.Namespace):
    from ccp import mutate, wt  # noqa: PLC0415
    return mutate.run(cfg, wt._queue_root(), a.run, a.test, a.mutant or [])


def _plane(cfg: config.Config, a: argparse.Namespace):
    from ccp import plane
    return {"propose": plane.propose, "triage": plane.triage, "list": plane.listing, "check": plane.check}[a.cmd](cfg, a)


def cmd_agent(cfg: config.Config, a: argparse.Namespace) -> int:
    from ccp import plane
    print(json.dumps(plane.agent_hook(cfg, a.action, plane.read_stdin())))
    return 0  # a hook never fails the agent it watches


def build_parser() -> argparse.ArgumentParser:
    # No abbreviations of --root: `ccp suite run`'s `--` split reads the words past it (§14.1).
    ap = argparse.ArgumentParser(prog="ccp", description="Control-plane product tool (SPEC §8)", allow_abbrev=False)
    ap.add_argument("--root", help="product checkout (default: $CCP_ROOT, else the git toplevel here)")
    sub = ap.add_subparsers(dest="group", required=True)

    t = sub.add_parser("tasks", help="the durable task log").add_subparsers(dest="cmd", required=True)
    p = t.add_parser("list", help="every task, in number order")
    p.add_argument("--status")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_tasks_list)
    p = t.add_parser("next", help="lowest pending task whose dependencies are done (exit 3: none; "
                                  "exit 4: an architect pass or triage is overdue; exit 7: the runner "
                                  "holds what it can, carry on with it, SPEC §16.3)")
    p.add_argument("--scope", help="comma-separated task ids or NNNN numbers; only these are candidates")
    p.add_argument("--json", action="store_true")
    p.add_argument("--allow-overdue", metavar="REASON",
                   help="override an exit-4 block once; recorded as a friction note (SPEC §19.6)")
    p.add_argument("--explain", action="store_true",
                   help="also list the full ranked queue on stderr, held tasks marked (SPEC §10.4)")
    p.set_defaults(fn=cmd_tasks_next)
    p = t.add_parser("check", help="validate the log and the index")
    p.add_argument("--lease", action="store_true",
                   help="only this: fail on an edit on the integration branch to the file of a task with a live "
                        "lease, since its claim (needs QUEUE_ROOT, SPEC §10.5)")
    p.add_argument("--staged", action="store_true",
                   help="with --lease: judge the staged change instead, when HEAD is on the integration branch "
                        "(the commit hook)")
    p.set_defaults(fn=cmd_tasks_check)
    p = t.add_parser("index", help="regenerate INDEX.yaml")
    p.add_argument("--stdout", action="store_true", help="print instead of writing")
    p.set_defaults(fn=cmd_tasks_index)
    life = _toolkit(_lifecycle)
    p = t.add_parser("prefer", help="the lead names the runner's next tasks, in order: `tasks next` returns the first "
                                    "ready one; its claim removes only that one, and a new list replaces the old. "
                                    "No arguments: show it (SPEC §10.4)")
    p.add_argument("tasks", nargs="*", metavar="task", help="task ids or NNNN, in the order wanted")
    p.add_argument("--reason", help="one line: why these tasks next")
    p.add_argument("--clear", action="store_true", help="remove the list")
    p.set_defaults(fn=life)
    p = t.add_parser("hold", help="the lead holds a task back: `tasks next` passes over it (a preference or a "
                                  "refactor too) until --clear. No arguments: list the holds (SPEC §10.4)")
    p.add_argument("task", nargs="?", help="task id or NNNN")
    p.add_argument("--reason", help="one line: why it waits")
    p.add_argument("--clear", metavar="ID", help="lift the hold on ID")
    p.set_defaults(fn=life)
    p = t.add_parser("sign-off", help="the lead records the operator's sign-off on a task that declares sign_off: "
                                      "who, the words and the head it covers, in the ledger. claim needs a brief "
                                      "one; close needs every declared one, a build one at the head it merges "
                                      "(SPEC §3.5)")
    p.add_argument("task", help="task id or NNNN")
    p.add_argument("--stage", choices=("brief", "build"), help="which sign-off (default: the one the task declares)")
    p.add_argument("--by", required=True, help="who signed: the operator's id")
    p.add_argument("--words", required=True, help="what they signed with, one line")
    p.add_argument("--head", help="the commit it covers (default: brief, the task file's last commit; build, the "
                                  "verified head)")
    p.set_defaults(fn=life)
    p = t.add_parser("claim", help="lease a task, make its worktree, record it (SPEC §10.5; needs QUEUE_ROOT)")
    p.add_argument("task", help="task id or NNNN")
    p.add_argument("--holder", default="runner", help="the claiming runner's slot (SPEC §16.4; required with "
                                                       "several runners)")
    p.set_defaults(fn=life)
    p = t.add_parser("worktree", help="a runner's own merge worktree, made when missing (SPEC §12.1, §16.5)")
    p.add_argument("--runner", metavar="SLOT", help="the runner's slot (required with several runners; without "
                                                    "it, the one runner's binding runner.worktree)")
    p.set_defaults(fn=life)
    p = t.add_parser("release", help="undo a claim taken too early: a leased task with no run goes back to pending, "
                                     "its lease and wait cleared; its worktree is kept (SPEC §10.4)")
    p.add_argument("task", help="task id or NNNN")
    p.add_argument("--reason", required=True, help="one line: why the claim is undone")
    p.set_defaults(fn=life)
    p = t.add_parser("drop", help="settle a task its file marks dropped while it was in flight (its PR not merged): "
                                  "runs abandoned, lease and wait cleared, out of work.json (SPEC §10.4)")
    p.add_argument("task", help="task id or NNNN")
    p.add_argument("--reason", required=True, help="one line: why it was dropped")
    p.set_defaults(fn=life)
    p = t.add_parser("phase", help="a phase change with no run of its own (operator step, merging)")
    p.add_argument("task")
    p.add_argument("phase")
    p.add_argument("--note")
    p.set_defaults(fn=life)
    for name, hlp in (("wait", "set waiting_on (through set-waiting-on.sh)"), ("resume", "clear waiting_on")):
        p = t.add_parser(name, help=hlp)
        p.add_argument("task")
        p.add_argument("reason", help="wait: why (quota, operator_decision, operator_step, design_seat, …); resume: what cleared it")
        if name == "wait":
            p.add_argument("--until", help="RFC3339 planned resume")
        p.add_argument("--detail")
        p.set_defaults(fn=life)
    p = t.add_parser("close", help="merge-ok, the pinned merge, the reconcile, the queue: one step (SPEC §10.5)")
    p.add_argument("task")
    p.add_argument("--pr", required=True)
    p.add_argument("--summary", help="one line for the product log (reconcile.log)")
    p.set_defaults(fn=life)
    p = t.add_parser("sync", help="the queue follows the task log: a done or dropped task's queue file loses its "
                                  "wait and lease and takes the durable status (SPEC §4, §10.4). A task leased "
                                  "mid-flight is skipped: close it, or release it, first")
    p.add_argument("--dry-run", action="store_true", help="print the planned changes, write nothing")
    p.set_defaults(fn=life)
    p = t.add_parser("orphans", help="the integration branch's commits since a ref that no task covers: not a task's "
                                     "merge or reconcile, not named in a task's covers:, changing more than the task "
                                     "log. Exit 1 when it lists one (SPEC §10.7)")
    p.add_argument("--since", required=True, help="the ref to list from (its own commit is not listed)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_tasks_orphans)
    p = t.add_parser("backfill-review-points",
                     help="stamp review_point into done tasks closed before close stamped it, from the queue's runner "
                          "history; working tree only, never overwrites (SPEC §22.6; needs QUEUE_ROOT)")
    p.add_argument("--dry-run", action="store_true", help="print task -> point with the evidence, write nothing")
    p.add_argument("--json", action="store_true", help="the full plan as JSON")
    p.set_defaults(fn=cmd_tasks_backfill)
    p = t.add_parser("estimate", help="advisory estimates (SPEC §26.3; needs QUEUE_ROOT): ID | --all [--max N] (the "
                                      "estimator seat) | ID --baseline | --all --baseline | show ID. A row is written when "
                                      "the task changed or a dependency merged")
    p.add_argument("args", nargs="*", help="a task id or NNNN; or `show ID`")
    p.add_argument("--baseline", action="store_true", help="the reference-class baseline (no LLM); without it, the "
                                                             "estimator seat (headless Sonnet, phase B)")
    p.add_argument("--all", action="store_true", help="every open task that needs a new row")
    p.add_argument("--max", type=int, default=10, help="the estimator: at most this many tasks per batch (default 10)")
    p.add_argument("--detach", action="store_true", help="the estimator, --all: run in the background and return")
    p.add_argument("--print-prompt", action="store_true", help="the estimator: print the prompt for one task, call nothing")
    p.add_argument("--run-id", help=argparse.SUPPRESS)
    p.add_argument("--actor", help=argparse.SUPPRESS)
    p.add_argument("--force", action="store_true", help="write a row even when the latest still stands")
    p.add_argument("--dry-run", action="store_true", help="say what would be written, write nothing")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_tasks_estimate)

    p = sub.add_parser("estimate", help="estimates against actuals (SPEC §26.6; needs QUEUE_ROOT): accuracy | calibration "
                                        "| backfill")
    p.add_argument("action", choices=("accuracy", "calibration", "backfill"))
    p.add_argument("--dry-run", action="store_true", help="backfill: say what would be written, write nothing")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_estimate)

    p = sub.add_parser("forecast", help="when the review point and the backlog finish, their tokens, cost and weekly %% "
                                        "(P50/P90, advisory; SPEC §26.4; needs QUEUE_ROOT)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--point", metavar="R<n>", help="this review point only (default: the runner's)")
    g.add_argument("--backlog", action="store_true", help="the whole open backlog only")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_forecast)

    p = sub.add_parser("review-points", help="the review-point register (SPEC §22): list | show R<n> | tag R<n> IDS "
                                             "| migrate --from OLD --to R<n>")
    p.add_argument("action", nargs="?", choices=("list", "show", "tag", "migrate"), default="list")
    p.add_argument("point", nargs="?", help="show, tag: the review point (R<n>)")
    p.add_argument("ids", nargs="*", help="tag: task ids or NNNN")
    p.add_argument("--from-work", action="store_true", help="tag: also every task in work.json's scope (needs QUEUE_ROOT)")
    p.add_argument("--from", dest="from_", help="migrate: the old point's name (for example PM)")
    p.add_argument("--to", help="migrate: the register's R<n> it becomes")
    p.add_argument("--merge", action="store_true", help="migrate: rename into a point tasks already carry")
    p.add_argument("--dry-run", action="store_true", help="tag, migrate: say what would change, write nothing")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_review_points)

    p = sub.add_parser("prompt", help="render a worker's prompt, audit it, open its run (SPEC §13.2; needs QUEUE_ROOT)")
    p.add_argument("phase", choices=("implement", "fix", "review", "verify"))
    p.add_argument("task", help="task id or NNNN")
    p.add_argument("--pr")
    p.add_argument("--head", help="the PR head this run works on (fix, review, verify)")
    p.add_argument("--base", help="implement: the integration sha the branch starts from (default origin's)")
    p.add_argument("--worktree", help="the task worktree (default: worktrees.dir/impl-NNNN)")
    p.add_argument("--note", help="at most 4000 characters of runner text for this run")
    p.add_argument("--note-file", metavar="PATH", help="the note read from a file instead (same limit and checks)")
    p.add_argument("--supersede", action="store_true",
                   help="mark a pending run of the same agent type abandoned (its launch never started)")
    p.add_argument("--holder", help="your runner slot (SPEC §16.4): only the slot holding the task's lease opens "
                                    "its rounds; required with several slots")
    p.add_argument("--allow-unreviewed-fix", action="store_true",
                   help="verify: open it although a fix round is newer than the last review (§15.2); needs --reason")
    p.add_argument("--reason", help="with --allow-unreviewed-fix: the lead's or the operator's words, recorded as a friction note")
    p.set_defaults(fn=_toolkit(_prompt))

    p = sub.add_parser("report", help="a worker submits its report and closes its run (SPEC §10.4)")
    p.add_argument("run_id", help="<task_id>/<phase>[-n], as ccp prompt printed it")
    p.add_argument("file")
    p.set_defaults(fn=_toolkit(_report))

    ru = sub.add_parser("runs", help="run records (SPEC §11.1)").add_subparsers(dest="cmd", required=True)
    p = ru.add_parser("gc", help="abandon open runs that will never report: an earlier round of a task's phase "
                                 "superseded by a later one, or a run of a done or dropped task (SPEC §11.1)")
    p.add_argument("--dry-run", action="store_true", help="print what it would abandon, write nothing")
    p.set_defaults(fn=_toolkit(_runs_gc))

    su = sub.add_parser("suite", help="run tests through ccp, which records their time (SPEC §14.1)") \
        .add_subparsers(dest="cmd", required=True)
    p = su.add_parser("run", help="run a test command transparently and record its time, exit code and test count",
                      usage="ccp suite run [--lane NAME] [--run RUN_ID | --task ID [--phase P]] [--wait S] [--full | --summary] "
                            "[--log PATH] [-- COMMAND ...]")
    p.add_argument("--lane", help="a short label; alone, the argv plane.json suite.lanes names for it")
    p.add_argument("--run", help="the run it belongs to (<task_id>/<phase>[-n], as the prompt names it)")
    p.add_argument("--task", help="else the task: its latest open run (of --phase)")
    p.add_argument("--phase", help="implement, fix, review or verify")
    p.add_argument("--wait", type=int, metavar="SECONDS",
                   help="an exclusive lane held by another run: wait up to this long for it instead of exiting 75 "
                        "at once; keep the wait plus the run under your shell's limit (SPEC §16.6)")
    out = p.add_mutually_exclusive_group()
    out.add_argument("--full", dest="output", action="store_const", const="full",
                     help="stream the command's output through unchanged (the default with a terminal on stdin)")
    out.add_argument("--summary", dest="output", action="store_const", const="summary",
                     help="write the output to a log file and print a summary: the counts, and on a failure the "
                          "failing tests' sections (the default without a terminal on stdin)")
    p.add_argument("--log", help="summary mode's log file (default: next to the run's record in the queue)")
    p.set_defaults(fn=None)
    p = su.add_parser("list", help="the recorded suite runs and their totals per run and per task (JSON)")
    p.add_argument("--task", help="only this task's")
    p.set_defaults(fn=_toolkit(_suite_list))

    p = sub.add_parser("mutate", help="does a test bite: apply each mutant in a mutation worktree, run the named test, "
                                      "record killed or survived on the run (SPEC §20.6; needs QUEUE_ROOT)")
    p.add_argument("--run", required=True, help="the calling seat's run (<task_id>/<phase>[-n]); it must be open")
    p.add_argument("--test", required=True, help="the test id plane.json mutate.command runs ({test})")
    p.add_argument("--mutant", action="append", required=True,
                   help="<file>:<old>=><new> (the old text once in the file, relative to the worktree), or a patch "
                        "file; repeat for more")
    p.set_defaults(fn=_toolkit(_mutate))

    from ccp import notify  # noqa: PLC0415
    notify.add_parser(sub, _toolkit)  # §3.6: render, sent, pending

    pl = sub.add_parser("plane", help="propose a ccp tool; the queue's script check (SPEC §31.4)") \
        .add_subparsers(dest="cmd", required=True)
    plane_fn = _toolkit(_plane)
    p = pl.add_parser("propose", help="a step ccp does not cover: propose a tool instead of writing one")
    p.add_argument("--need")
    p.add_argument("--generic", help="why any product would need this, whatever its language, domain or conventions "
                                     "(SPEC §31.4); a need only this product has is product work, not a proposal")
    p.add_argument("--task")
    p.add_argument("--workaround")
    p.add_argument("--frequency", choices=("per-task", "per-run", "once"))
    p.add_argument("--again", metavar="ID", help="the same need came up again and was done by hand")
    p.set_defaults(fn=plane_fn)
    p = pl.add_parser("triage", help="the plane session's decision on a proposal, recorded as plane-session (SPEC §31.5)")
    p.add_argument("id")
    p.add_argument("--accept", action="store_true")
    p.add_argument("--merge-into", metavar="ID")
    p.add_argument("--decline", action="store_true")
    p.add_argument("--reason")
    p.set_defaults(fn=plane_fn)
    p = pl.add_parser("list", help="proposals, most repeated first")
    p.add_argument("--open", action="store_true")
    p.set_defaults(fn=plane_fn)
    pl.add_parser("check", help="files in QUEUE_ROOT/scripts/ that are not the plane's (exit 1 if any)") \
        .set_defaults(fn=plane_fn)

    sub.add_parser("otel", help="the telemetry receiver: serve | env | install | uninstall | status "
                                "(SPEC §24.5, §24; runs without a product)")
    p = sub.add_parser("usage", help="tokens, model and effort per run and per seat (SPEC §24.5; needs QUEUE_ROOT); "
                                     "--system: usage outside every project by cwd and day (§24)")
    p.add_argument("--task", help="only this task's runs")
    p.add_argument("--system", action="store_true", help="the receiver's system sink (no product needed)")
    p.add_argument("--since", help="with --system: YYYY-MM-DD")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_usage)

    p = sub.add_parser("board", help="the project board (SPEC §28.3): build | status | task ID | install | uninstall | timer")
    p.add_argument("action", choices=("build", "status", "task", "install", "uninstall", "timer"))
    p.add_argument("task_id", nargs="?", help="task: the task id or its NNNN")
    p.add_argument("--quiet", action="store_true", help="build: print nothing (the launchd timer)")
    p.add_argument("--drain", action="store_true", help=argparse.SUPPRESS)  # board.refresh's detached build
    p.set_defaults(fn=cmd_board)

    p = sub.add_parser("allowance", help="the weekly checkpoint and the 5-hour session wake (SPEC §25.4): status, the "
                                         "lead records the operator's decision, or session-wake [--sample | --armed | --fire]")
    p.add_argument("action", choices=("status", "continue", "session-wake"))
    p.add_argument("--to", type=float, help="continue: the next checkpoint, in percent of the weekly allowance")
    p.add_argument("--reason", help="continue: the operator's decision, in their words")
    p.add_argument("--sample", action="store_true", help="status, session-wake: take a fresh sample first")
    p.add_argument("--armed", action="store_true", help="session-wake: the lead records the wake it armed (CronCreate)")
    p.add_argument("--fire", action="store_true", help="session-wake: the wake fired; un-park the tasks once the "
                                                       "5-hour window has reset, and say how to resume the runner")
    p.set_defaults(fn=_toolkit(_allowance))

    sub.add_parser("where", help="this product's project id, binding, queue root and plane checkout (SPEC §9.2)") \
        .set_defaults(fn=cmd_where)

    p = sub.add_parser("init", help="adopt this repository: the product footprint, the binding and the queue "
                                    "(SPEC §4.3, §8.3); keeps existing files unless --force")
    p.add_argument("--project-id", help="the project id (default: plane.json's, else the directory's name)")
    p.add_argument("--queue-root", help="the queue directory (default: ~/.delivery-queue/<project_id>)")
    p.add_argument("--integration-branch", help="the binding's integration branch (default: main)")
    p.add_argument("--gate", help="the gate lane's command, written to plane.json suite.lanes.gate; "
                                  "not applied when plane.json exists and is kept (no --force)")
    p.add_argument("--starter-rules", action="store_true",
                   help="adopt the plane's starter house rules (SPEC §20.5): docs/ENGINEERING.md and their "
                        "plane.json settings; the settings are not applied to a kept plane.json")
    p.add_argument("--force", action="store_true", help="overwrite the files init writes")
    p.set_defaults(fn=None)

    p = sub.add_parser("agent", help="the SubagentStart / SubagentStop hooks: bind and stop runs (SPEC §11.1)")
    p.add_argument("action", choices=("start", "stop"))
    p.set_defaults(fn=cmd_agent)

    bg = sub.add_parser("budgets", help="house-rule budgets on this change's files (SPEC §20.2)").add_subparsers(
        dest="cmd", required=True)
    p = bg.add_parser("check", help="fail when the change grew a touched file over its architect.budgets entry; "
                                    "an over-budget file it did not grow only warns")
    p.add_argument("--base", required=True, help="the integration branch, e.g. origin/main: judged from its merge "
                                                 "base with HEAD")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_budgets_check)
    d = sub.add_parser("docs", help="package docs").add_subparsers(dest="cmd", required=True)
    d.add_parser("check", help="package-doc rules + the task log (+ the ADRs' frontmatter with an adr block)") \
        .set_defaults(fn=cmd_docs_check)
    hp = d.add_parser("history-paths", help="tracked paths carrying the history attribute (package_docs.rules."
                                            "history_attr), one per line, for a product's own absence checks")
    hp.add_argument("--attr", help="the git attribute (default: package_docs.rules.history_attr)")
    hp.set_defaults(fn=cmd_docs_history_paths)
    p = d.add_parser("adr", help="alias of `ccp adr index|list` (SPEC §6.7)")
    p.add_argument("action", choices=("index", "list"))
    p.add_argument("--dir", help="list: the ADR directory (default: plane.json adr.dir, else docs/adr)")
    p.add_argument("--stdout", action="store_true", help="index: print instead of writing")
    p.add_argument("--json", action="store_true", help="list: JSON")
    p.set_defaults(fn=cmd_adr, args=[], note=None, by=None, decisions=None, archive=False, markers=False, dry_run=False)
    p = sub.add_parser("wt", help="worktrees and environments (SPEC §12.1): create | remove | list | up | down | urls | gc | "
                                  "exec")
    p.add_argument("action", choices=("create", "remove", "list", "up", "down", "urls", "gc", "exec"))
    p.add_argument("name_arg", nargs="?", metavar="NAME", help="remove, up, down, urls: the worktree (e.g. ver-0042); "
                                                              "exec: the worktree whose ccp runs (default this checkout)")
    p.add_argument("--kind", choices=("impl", "rev", "ver", "mut", "mac", "base"),
                   help="create: the worktree's kind (base: run the command after `--` at the merge base of --sha "
                        "and the integration branch, then remove it)")
    p.add_argument("--task", help="create: the task; list: only its worktrees")
    p.add_argument("--sha", help="create: the head a rev/ver/mut/mac worktree is detached at; base: the head whose "
                                 "merge base it checks out")
    p.add_argument("--name", help="create: the name (default <kind>-<nnnn>, then -2, -3, …)")
    p.add_argument("--seat", help="create: the seat it serves (default from the kind)")
    p.add_argument("--tag", help="create: a tag for the hooks (default main; mut, mac for those kinds)")
    p.add_argument("--print", dest="print_path", action="store_true", help="exec: print the path of its bin/ccp, run nothing")
    p.set_defaults(fn=cmd_wt, command=[])
    p = sub.add_parser("auth", help="auth probes (SPEC §30)").add_subparsers(dest="cmd", required=True)
    p.add_parser("check", help="run plane.json auth_check.probes; exit 1 when one fails").set_defaults(fn=cmd_auth)
    p = sub.add_parser("adr", help="ADRs (SPEC §6.4): new | status | decide | supersede | check | index | list | migrate")
    p.add_argument("action", choices=("new", "status", "decide", "supersede", "check", "index", "list", "migrate"))
    p.add_argument("args", nargs="*", help="new: TITLE; status: N STATUS; decide: N Dn STATE; supersede: OLD NEW")
    p.add_argument("--note", help="status, decide: a note (status: kept in the ADR's `notes`, dated)")
    p.add_argument("--by", help="decide: the ADR (decision) that retired or replaced it; supersede: the new ADR's decision")
    p.add_argument("--decisions", help="supersede: only these decisions of OLD (D2,D4); OLD keeps its status")
    p.add_argument("--archive", action="store_true", help="supersede: move OLD into adr.dir/archive (git mv)")
    p.add_argument("--markers", action="store_true", help="migrate: rewrite decisions to `### Dn. Title`")
    p.add_argument("--dry-run", action="store_true", help="migrate: write nothing, say what would change")
    p.add_argument("--stdout", action="store_true", help="index: print instead of writing")
    p.add_argument("--json", action="store_true", help="list: JSON")
    p.add_argument("--dir", help="list: the ADR directory (default: plane.json adr.dir, else docs/adr)")
    p.set_defaults(fn=cmd_adr)

    p = sub.add_parser("architect", help="the architect seat: passes, shapes and their triage (needs QUEUE_ROOT)")
    p.add_argument("action", choices=("due", "run", "triage", "status"))
    p.add_argument("review_id", nargs="?", help="triage: the report id (ar-… or sh-…)")
    p.add_argument("--mode", choices=("pass", "shape"), default="pass")
    p.add_argument("--lens", help="comma-separated lenses (structure, docs, tests, process); default all")
    p.add_argument("--adr", help="shape: the ADR to shape")
    p.add_argument("--scope", help="due, run: the runner's scope, for the review-point trigger "
                                   "(default: work.json's, while a runner is running)")
    p.add_argument("--force", action="store_true", help="run a pass even if not due (on demand)")
    p.add_argument("--detach", action="store_true",
                   help="start the pass in its own session and return once it is running")
    p.add_argument("--actor")
    p.add_argument("--review-id", dest="rid", help=argparse.SUPPRESS)
    p.add_argument("--backfill", nargs=2, metavar=("ID", "SHA"),
                   help="triage: record the integration-branch sha for a finalised triage whose commit_sha is pending")
    p.add_argument("--apply", metavar="ID",
                   help="triage: validate and finalise a triage file already committed by hand, then rebuild INDEX.yaml")
    p.set_defaults(fn=cmd_architect)

    p = sub.add_parser("verify", help="the verifier's record and the runner's merge gate (SPEC §15.3; needs QUEUE_ROOT)")
    p.add_argument("action", choices=("record", "merge-ok", "check"))
    p.add_argument("target", help="record: the verdict JSON file (- for stdin); merge-ok: the PR number; "
                                  "check: the task id")
    p.add_argument("--task", help="merge-ok: the task whose record approves this PR (default: pr-<PR>)")
    p.add_argument("--head", help="check: the PR head the runner would merge")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("health", help="delivery measurements; note and record add to them (SPEC §27.1)")
    p.add_argument("action", nargs="?", choices=("show", "note", "record"), default="show")
    p.add_argument("--since", help="show: only tasks merged on or after this date (YYYY-MM-DD)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--text", help="note: the friction line, as the worker wrote it")
    p.add_argument("--task", help="note, record: the task id")
    p.add_argument("--by", help="note: the worker (implementer, reviewer, verifier)")
    p.add_argument("--metric", action="append", help="record: name=value (repeatable)")
    p.set_defaults(fn=cmd_health)

    return ap


def binding_file(cfg: config.Config) -> Path | None:
    """SPEC §8.3, §9.2: this product's binding, `<bindings>/<project_id>.yaml`, and only when its
    product_root is this checkout or its main checkout. A scratch clone or a fork that names a live
    project's id gets nothing."""
    from ccp.prompt import main_checkout  # noqa: PLC0415
    from ccp.queue import lib  # noqa: PLC0415
    if not config.PROJECT_ID_RE.match(cfg.project_id):
        return None
    b = lib.bindings_dir() / f"{cfg.project_id}.yaml"
    if not b.is_file():
        return None
    root = _scalar(b.read_text(), "product_root")
    if not root or Path(root).expanduser().resolve() not in (cfg.root.resolve(), main_checkout(cfg).resolve()):
        return None
    return b


def _scalar(text: str, key: str) -> str | None:
    import re  # noqa: PLC0415
    m = re.search(rf"^{key}:\s*([^#\n]+)", text, re.M)
    return m.group(1).strip().strip("'\"") if m else None


def binding_queue_root(cfg: config.Config) -> str | None:
    """SPEC §9.2: the project's queue, from this product's binding (`binding_file`)."""
    b = binding_file(cfg)
    q = _scalar(b.read_text(), "queue_root") if b else None
    return str(Path(q).expanduser()) if q and Path(q).expanduser().is_dir() else None


def checkout_warning() -> str | None:
    """SPEC §29.2: products run `main` as published. Warn when the checkout `ccp` runs from has local
    changes, is off `main`, or is behind `origin/main`. `CCP_DEV=1` (development, tests) silences it."""
    if envvar("CCP_DEV") == "1":
        return None
    import subprocess  # noqa: PLC0415
    from ccp.queue import PLANE  # noqa: PLC0415

    def g(*args: str) -> str:
        r = subprocess.run(["git", "--no-optional-locks", "-C", str(PLANE), *args], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""
    if not (PLANE / ".git").exists():
        return None  # an installed copy: not a checkout
    why = []
    if g("status", "--porcelain", "--untracked-files=no"):
        why.append("it has local changes")
    branch = g("rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        # Detached exactly at origin/main (a cloud clone, §29.4) is running main.
        branch = "main" if g("rev-parse", "HEAD") == g("rev-parse", "origin/main") else ""
    if branch != "main":
        why.append(f"it is on {branch or 'a detached HEAD'}, not main")
    behind = g("rev-list", "--count", "HEAD..origin/main")
    if behind.isdigit() and int(behind):
        why.append(f"it is {behind} commit(s) behind origin/main")
    return f"ccp: running from {PLANE}, but {'; '.join(why)} (SPEC §29)" if why else None


def _allowance(cfg: config.Config, a: argparse.Namespace):
    from ccp import usage  # noqa: PLC0415
    from ccp.queue import root  # noqa: PLC0415
    q = root()
    if (a.armed or a.fire) and a.action != "session-wake":
        raise QueueError("--armed and --fire are for session-wake", 2)
    if a.action == "status":
        a.board_dirty = a.sample  # a fresh sample is new state; the board's own build never samples
        return usage.status(cfg, q, a.sample)
    if a.action == "session-wake":
        if a.armed and a.fire or (a.armed or a.fire) and a.sample:
            raise QueueError("session-wake: give one of --sample, --armed, --fire", 2)
        a.board_dirty = a.sample or a.armed or a.fire  # §28: a sample, a wake recorded, tasks un-parked
        if not (a.armed or a.fire):
            return usage.session_wake(cfg, q, a.sample)
        return usage.session_armed(cfg, q) if a.armed else usage.session_fire(cfg, q)
    if a.to is None:
        raise QueueError("give --to <percent>", 2)
    return usage.continue_(cfg, q, a.to, a.reason or "")


def cmd_board(cfg: config.Config, a: argparse.Namespace) -> int:
    from ccp import board  # noqa: PLC0415
    from ccp.queue import root  # noqa: PLC0415
    if a.action in ("install", "uninstall", "timer"):
        body = board.launchd(cfg, {"timer": "status"}.get(a.action, a.action))
        print(json.dumps(body, indent=2))
        return 0 if body.get("ok") else 1
    try:
        q = root()
    except QueueError as e:
        print(f"ccp board: {e}", file=sys.stderr)
        return e.code
    if a.action == "build" and a.drain:
        return board.drain(cfg, q)
    if a.action == "task":
        if not a.task_id:
            print("ccp board task: give the task id (or its NNNN)", file=sys.stderr)
            return 2
        try:
            print(board.task_text(cfg, q, a.task_id))
        except QueueError as e:
            print(f"ccp board task: {e}", file=sys.stderr)
            return e.code
        return 0
    b = board.build(cfg, q)
    if a.action == "status":
        print(board.status_text(b))
        return 1 if b["blockers"] else 0
    paths = board.write(q, b)
    if not a.quiet:
        div = b["health"]["divergence"]
        if div:
            print(f"warning: {len(div)} queue file(s), gate(s) or question(s) diverge from the task log; "
                  "`ccp tasks sync` settles the queue files (`ccp board status` lists them all)", file=sys.stderr)
            for x in div[:5]:
                print(f"warning:   {x}", file=sys.stderr)
        print(json.dumps({"ok": True, **paths, "blockers": len(b["blockers"])}, indent=2))
    return 0


def cmd_usage(cfg: config.Config, a: argparse.Namespace) -> int:
    from ccp import usage  # noqa: PLC0415
    from ccp.queue import root  # noqa: PLC0415
    try:
        q = root()
        from ccp.queue import task_meta  # noqa: PLC0415
        tid = str(task_meta(cfg, a.task)["task_id"]) if a.task else None
    except QueueError as e:
        print(f"ccp usage: {e}", file=sys.stderr)
        return e.code
    report = usage.fold(q, tid, (cfg.telemetry or {}).get("design_seat"))
    report.pop("recent", None)  # the board's live-seat rows, not a usage figure
    report.pop("timeline", None)  # the board's drill-down intervals, likewise
    from ccp import suite  # noqa: PLC0415
    suite.attach(q, report, tid)
    if a.json:
        print(json.dumps(report, indent=2))
    else:
        print(usage.table(report))
        if lines := suite.table(report):
            print(lines)
    return 0


def cmd_where(cfg: config.Config, _a: argparse.Namespace) -> int:
    """SPEC §9.2: the project, its binding (§8.3, through the one resolver), the queue, the plane
    checkout and the `ccp` path."""
    from ccp.queue import CCP_BIN, PLANE, lib  # noqa: PLC0415
    q = os.environ.get("QUEUE_ROOT")
    b = lib.binding_path(Path(q)) if q else binding_file(cfg)
    print(json.dumps({"project_id": cfg.project_id, "product_root": str(cfg.root),
                      "binding": str(b) if b else None, "queue_root": q,
                      "plane": str(PLANE), "ccp": str(CCP_BIN)}))
    return 0


# §28: the commands that change delivery state, as their words: (group, cmd, action, direction).
# A command matches when one of these is a prefix of its words. A command that only sometimes
# writes sets `a.board_dirty` instead (tasks next --allow-overdue, tasks prefer with a task or --clear, tasks hold likewise, allowance status --sample,
# allowance session-wake with --sample, --armed or --fire,
# tasks sync when it changed something and was not --dry-run, runs gc likewise).
REFRESHES = {("tasks", "claim"), ("tasks", "release"), ("tasks", "drop"), ("tasks", "phase"), ("tasks", "wait"), ("tasks", "resume"), ("tasks", "close"),
             ("prompt",), ("report",), ("verify", "record"), ("plane", "propose"), ("plane", "triage"),
             ("allowance", "continue"), ("architect", "run"), ("architect", "triage"),
             ("agent", "start"), ("agent", "stop"),
             ("health", "note"), ("health", "record")}


def refresh_board(cfg: config.Config, a: argparse.Namespace, code: int) -> None:
    """After a state change succeeds, the board rebuilds in the background (board.refresh)."""
    try:
        words = tuple(w for w in (a.group, *(getattr(a, k, None) for k in ("cmd", "action", "direction"))) if w)
        listed = any(words[:i] in REFRESHES for i in range(1, len(words) + 1))
        # §25.4: a session park (exit 6) wrote the task's wait, so the board follows it too
        if (code == 0 or code == 6 and listed) and (listed or getattr(a, "board_dirty", False)):
            from ccp import board  # noqa: PLC0415
            board.refresh(cfg)
    except Exception:  # noqa: BLE001  (never the command's problem)
        pass


def _words(raw: list[str]) -> list[str]:
    """The command words, past the global `--root P` / `--root=P`. A prefix of it (`--ro P`) is
    skipped too: the parser refuses it (no abbreviations), and the command after `--` still runs."""
    out, skip = [], False
    for w in raw:
        name = w.split("=", 1)[0]
        if skip:
            skip = False
        elif len(name) > 2 and "--root".startswith(name):
            skip = "=" not in w
        else:
            out.append(w)
    return out


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw[:1] == ["otel"]:  # §24.2: the receiver serves every project; it needs no product checkout
        from ccp import otel  # noqa: PLC0415
        return otel.main(raw[1:])
    words = raw[2:] if raw[:1] == ["--root"] else [w for w in raw if not w.startswith("--root=")]
    if words[:1] == ["usage"] and "--system" in words:  # §24: usage outside every project, no product needed
        from ccp import usage  # noqa: PLC0415
        return usage.system_main(words[1:])
    command, passthru = None, []
    if "--" in raw and _words(raw[:raw.index("--")])[:2] == ["suite", "run"]:
        command, raw = raw[raw.index("--") + 1:], raw[:raw.index("--")]  # §14.1: the command, verbatim
    elif "--" in raw and _words(raw[:raw.index("--")])[:2] in (["wt", "exec"], ["wt", "create"]):
        passthru, raw = raw[raw.index("--") + 1:], raw[:raw.index("--")]  # §12.1: its ccp's arguments, or the
        # command a base worktree runs, verbatim
    if command:
        try:
            a = build_parser().parse_args(raw)
        except SystemExit:  # argparse said what is wrong; the tests still run (§14.1)
            from ccp import suite  # noqa: PLC0415
            return suite.unparsed(command)
    else:
        a = build_parser().parse_args(raw)
    warn = checkout_warning()
    if warn:
        print(f"warning: {warn}", file=sys.stderr)
    if a.group == "init":  # it writes plane.json, so it runs before one loads (§8.3)
        from ccp import init  # noqa: PLC0415
        return init.main(a.root, a)
    if a.group == "suite" and a.cmd == "run":  # it runs even where plane.json does not load
        from ccp import suite  # noqa: PLC0415
        return suite.main_run(a, command)
    if a.group == "wt" and a.action == "exec":  # it runs even where this ccp cannot load the checkout's plane.json
        return cmd_wt_exec(a, passthru)
    if a.group == "wt":
        a.command = passthru
    try:
        cfg = config.load(config.find_root(a.root))
    except config.ConfigError as e:
        print(f"ccp: {e}", file=sys.stderr)
        return 2
    if not os.environ.get("QUEUE_ROOT") and envvar("CCP_NO_BINDING_QUEUE") != "1" \
            and (q := binding_queue_root(cfg)):
        os.environ["QUEUE_ROOT"] = q
    code = a.fn(cfg, a)
    refresh_board(cfg, a, code)
    return code
