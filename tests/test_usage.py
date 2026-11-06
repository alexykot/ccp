"""SPEC §24.4, §25.1, docs/design/telemetry.md: the telemetry receiver, the attribution fold, the allowance gate."""
from __future__ import annotations

import io
import json
import os
import threading
import tempfile
import unittest
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, otel, usage
from tests.helpers import Product

PLANE = Path(__file__).resolve().parents[1]


def kv(**a):
    out = []
    for k, v in a.items():
        k = k.replace("__", ".")
        if isinstance(v, bool) or v is None:
            continue
        val = {"intValue": str(v)} if isinstance(v, int) else {"doubleValue": v} if isinstance(v, float) else {"stringValue": v}
        out.append({"key": k, "value": val})
    return out


def logs(project, *records):
    return {"resourceLogs": [{"resource": {"attributes": kv(ccp__project_id=project, service__name="claude-code")},
                              "scopeLogs": [{"logRecords": [{"timeUnixNano": str(r.pop("t")), "attributes": kv(**r)}
                                                            for r in records]}]}]}


def spans(project, *records):
    return {"resourceSpans": [{"resource": {"attributes": kv(ccp__project_id=project)},
                               "scopeSpans": [{"spans": [{"name": "claude_code.llm_request",
                                                          "startTimeUnixNano": str(r.pop("t")),
                                                          "attributes": kv(**r)} for r in records]}]}]}


T0 = 1_800_000_000 * 10**9  # 2027-01-15


def req(rid, t, model="claude-opus-5-5", effort="high", source="agent:custom", out=100, **more):
    return {"t": T0 + t * 10**9, "event__name": "api_request", "request_id": rid, "model": model, "effort": effort,
            "query_source": source, "input_tokens": 2, "output_tokens": out, "cache_read_tokens": 1000,
            "cache_creation_tokens": 10, "cost_usd": 0.01, "session__id": "s1", **more}


class Receiver(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        d = Path(self._d.name)
        self.q = d / "queue"
        self.q.mkdir()
        (d / "projects").mkdir()
        (d / "projects/demo.yaml").write_text(f"project_id: demo\nqueue_root: {self.q}\n")
        self.sys = d / "telemetry"
        self.patch = mock.patch.dict(os.environ, {"CCP_BINDINGS_DIR": str(d / "projects"),
                                                  "CCP_TELEMETRY_DIR": str(self.sys),
                                                  "CCP_CLAUDE_PROJECTS_DIR": str(d / "claude-projects")})
        self.patch.start()
        self.sink = otel.Sink()
        self.srv = otel.http.server.ThreadingHTTPServer(("127.0.0.1", 0), otel.handler(self.sink))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.patch.stop()
        self._d.cleanup()

    def post(self, path, body):
        r = urllib.request.Request(self.url + path, data=json.dumps(body).encode(), method="POST",
                                   headers={"Content-Type": "application/json"})
        return urllib.request.urlopen(r).status

    def test_keeps_numbers_and_ids_only_and_routes_by_project(self):
        secret_prompt = req("r1", 1, prompt="the user's words")
        self.assertEqual(self.post("/v1/logs", logs("demo", secret_prompt, {"t": T0, "event__name": "user_prompt"})), 200)
        self.assertEqual(self.post("/v1/traces", spans("demo", {"t": T0, "request_id": "r1", "agent_id": "a1"})), 200)
        self.assertEqual(self.post("/v1/logs", logs("nobody", req("r2", 2))), 200)
        self.assertEqual(self.post("/v1/metrics", {"resourceMetrics": []}), 200)
        rows = [json.loads(x) for x in (self.q / "board/usage-requests.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["request_id"], rows[0]["output_tokens"], rows[0]["model"]), ("r1", 100, "claude-opus-5-5"))
        self.assertNotIn("prompt", json.dumps(rows))
        span = json.loads((self.q / "board/usage-spans.jsonl").read_text())
        self.assertEqual((span["request_id"], span["agent_id"]), ("r1", "a1"))
        # §24: a record for no known project is kept in the system sink, not dropped.
        self.assertEqual(self.sink.dropped, 0)
        self.assertEqual(self.sink.unresolved, 1)
        (sysfile,) = self.sys.glob("usage-requests-*.jsonl")
        row = json.loads(sysfile.read_text())
        self.assertEqual((row["request_id"], row["project_id_unbound"], row["cwd"]), ("r2", "nobody", None))

    def test_a_project_bound_later_is_found(self):
        self.post("/v1/logs", logs("late", req("r1", 1)))
        q2 = Path(self._d.name) / "late-queue"
        q2.mkdir()
        (Path(self._d.name) / "projects/late.yaml").write_text(f"project_id: late\nqueue_root: {q2}\n")
        self.post("/v1/logs", logs("late", req("r2", 2)))
        self.assertTrue((q2 / "board/usage-requests.jsonl").is_file())

    def test_refuses_what_it_cannot_keep_and_reports_status(self):
        import urllib.error
        for headers, data, code in (({"Content-Type": "application/x-protobuf"}, b"\x0a\x01", 415),
                                    ({"Content-Type": "application/json"}, b"not json", 400)):
            r = urllib.request.Request(self.url + "/v1/logs", data=data, method="POST", headers=headers)
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(r)
            self.assertEqual(cm.exception.code, code)
        with urllib.request.urlopen(self.url + "/status") as resp:
            st = json.loads(resp.read())
        self.assertEqual(st["refused"], 2)

    def test_a_chunked_body_is_read(self):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1])
        body = json.dumps(logs("demo", req("rc", 1))).encode()
        c.putrequest("POST", "/v1/logs")
        c.putheader("Content-Type", "application/json")
        c.putheader("Transfer-Encoding", "chunked")
        c.endheaders()
        c.send(hex(len(body))[2:].encode() + b"\r\n" + body + b"\r\n0\r\n\r\n")
        self.assertEqual(c.getresponse().status, 200)
        c.close()
        self.assertIn('"rc"', (self.q / "board/usage-requests.jsonl").read_text())

    def test_numbers_sent_as_strings_are_numbers(self):
        rec = req("r9", 1)
        rec["cost_usd"] = "0.25"
        self.post("/v1/logs", logs("demo", rec))
        row = json.loads((self.q / "board/usage-requests.jsonl").read_text().splitlines()[-1])
        self.assertEqual(row["cost_usd"], 0.25)


class Fold(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.q = Path(self._d.name)
        (self.q / "project.yaml").write_text("project_id: demo\nrunner:\n  name: runner\n")
        (self.q / "board").mkdir()
        self.mkrun("0001-a/implement", "implementer", "claude-opus-5-5", "high", agent="a1", start=0, stop=100)
        self.mkrun("0001-a/review", "reviewer", "claude-sonnet-5-5", "high", agent=None, start=200, stop=300)

    def tearDown(self):
        self._d.cleanup()

    def mkrun(self, rid, seat, model, effort, agent, start, stop):
        from datetime import datetime, timezone
        f = lambda s: datetime.fromtimestamp(T0 / 1e9 + s, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        task, phase = rid.split("/")
        p = self.q / "runs" / task / f"{phase}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"run_id": rid, "task_id": task, "phase": phase, "seat": seat, "agent_type": f"delivery-{seat}",
                                 "expected_model": model, "expected_effort": effort, "agent_id": agent,
                                 "opened_at": f(start), "started_at": f(start), "stopped_at": f(stop)}))

    def write(self, name, rows):
        with (self.q / "board" / name).open("a") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

    def rows(self, *rs):
        out = []
        for r in rs:
            r = dict(r)
            t = r.pop("t")
            out.append({k.replace("__", "_"): v for k, v in r.items()} | {"at": otel._iso(t)})
        return out

    def test_the_join(self):
        self.write("usage-requests.jsonl", self.rows(
            req("w1", 10), req("w2", 20, effort="medium"),                           # the implementer (span), one effort off
            req("t1", 30, model="claude-sonnet-5-5", out=50),                        # the runner teammate
            req("l1", 40, model="claude-fable-5-1", source="repl_main_thread", out=5),  # the lead
            req("x1", 250, model="claude-sonnet-5-5"),                               # no span: window → review
            req("x2", 999)))                                                         # no span, no open run
        self.write("usage-spans.jsonl", [{"request_id": "w1", "agent_id": "a1"}, {"request_id": "w2", "agent_id": "a1"},
                                         {"request_id": "t1", "agent_id": "runner@session-abc"}, {"request_id": "l1"}])
        r = usage.fold(self.q)
        impl = next(x for x in r["runs"] if x["run_id"] == "0001-a/implement")
        self.assertEqual((impl["usage"]["requests"], impl["usage"]["output_tokens"]), (2, 200))
        self.assertEqual(impl["flags"], ["effort high, medium, pinned high"])
        review = next(x for x in r["runs"] if x["run_id"] == "0001-a/review")
        self.assertEqual(review["usage"]["requests"], 1)
        self.assertEqual(r["seats"]["runner"]["output_tokens"], 50)
        self.assertEqual(r["seats"]["design-seat"]["output_tokens"], 5)
        self.assertEqual(r["unattributed"]["requests"], 1)
        self.assertEqual(r["how"], {"headless": 0, "untagged": 0, "span": 2, "teammate": 1, "lead": 1, "session": 0, "window": 1,
                                    "nospan": 0, "none": 1})
        self.assertLess(r["coverage"], 1)
        self.assertTrue(r["traces"])
        self.assertIn("coverage", usage.table(r))

    def test_a_runner_a_rotation_renamed_is_still_the_runner(self):
        """§10.2: `runner-2`, bound after a rotation, and the runner before it are one seat."""
        (self.q / "observability").mkdir(exist_ok=True)
        (self.q / "observability" / "events.jsonl").write_text(json.dumps(
            {"type": "runner", "op": "bound", "payload": {"name": "runner-2", "previous": "runner"}}) + "\n")
        self.write("usage-requests.jsonl", self.rows(req("t1", 30, out=50), req("t2", 31, out=7), req("p1", 32, out=1)))
        self.write("usage-spans.jsonl", [{"request_id": "t1", "agent_id": "runner@session-abc"},
                                         {"request_id": "t2", "agent_id": "runner-2@session-abc"},
                                         {"request_id": "p1", "agent_id": "probe@session-abc"}])
        with (self.q / "observability" / "events.jsonl").open("a") as fh:  # lines a reader must step over
            fh.write('{"type": "runner", broken\n' + json.dumps({"type": "runner", "op": "set", "payload": {}}) + "\n")
        (self.q / "work.json").write_text("{not json")  # a broken work.json falls back to the binding
        r = usage.fold(self.q)
        self.assertEqual(r["seats"]["runner"]["output_tokens"], 57)
        self.assertEqual(r["seats"]["teammate:probe"]["output_tokens"], 1)

    def test_every_runner_slots_worktree_is_the_runner_seat(self):
        """§16.7: with several runners, each slot's own checkout (`<runner.worktree>-<slot>`) is the runner seat."""
        root = Path(self._d.name) / "prod"
        (root / ".ccp-runtime").mkdir(parents=True)
        (self.q / "project.yaml").write_text(f"project_id: demo\nproduct_root: {root}\nrunner:\n  name: runner\n"
                                             f"  worktree: {root}/.ccp-runtime/runner\n")
        (self.q / "work.json").write_text(json.dumps({"runners": {"runner-1": {}, "runner-2": {"worktree": "x2"}}}))  # relative
        main = dict(source="repl_main_thread")
        self.write("usage-requests.jsonl", self.rows(
            req("a", 1, session__id="s1", cwd=f"{root}/.ccp-runtime/runner-runner-1", out=5, **main),
            req("b", 2, session__id="s2", cwd=f"{root}/x2", out=6, **main)))
        self.write("usage-spans.jsonl", [{"request_id": "a"}, {"request_id": "b"}])
        r = usage.fold(self.q)
        self.assertEqual(r["seats"]["runner"]["output_tokens"], 11)

    def test_with_traces_a_main_call_without_a_span_is_not_counted_as_the_lead(self):
        self.write("usage-requests.jsonl", self.rows(req("w1", 10), req("l1", 20, source="repl_main_thread")))
        self.write("usage-spans.jsonl", [{"request_id": "w1", "agent_id": "a1"}])
        r = usage.fold(self.q)
        self.assertEqual(r["how"]["nospan"], 1)
        self.assertNotIn("design-seat", r["seats"])
        self.assertLess(r["coverage"], 1)

    def test_duplicates_count_once_and_bad_numbers_do_not_crash(self):
        dup = req("w1", 10)
        self.write("usage-requests.jsonl", self.rows(dup, dict(dup), req("w2", 11, out="n/a"), req("w3", 12, out=float("inf"))))
        self.write("usage-spans.jsonl", [{"request_id": "w1", "agent_id": "a1"}, {"request_id": "w2", "agent_id": "a1"},
                                         {"request_id": "w3", "agent_id": "a1"}])
        impl = next(x for x in usage.fold(self.q)["runs"] if x["run_id"] == "0001-a/implement")
        self.assertEqual((impl["usage"]["requests"], impl["usage"]["output_tokens"]), (3, 100))

    def test_a_run_never_started_catches_nothing(self):
        p = self.q / "runs/0001-a/review.json"
        rec = json.loads(p.read_text())
        rec["started_at"] = None
        p.write_text(json.dumps(rec))
        self.write("usage-requests.jsonl", self.rows(req("x1", 250, model="claude-sonnet-5-5")))
        r = usage.fold(self.q)
        self.assertEqual(r["how"]["none"], 1)

    def test_task_totals(self):
        self.write("usage-requests.jsonl", self.rows(req("w1", 10)))
        self.write("usage-spans.jsonl", [{"request_id": "w1", "agent_id": "a1"}])
        r = usage.fold(self.q, "0001-a")
        self.assertEqual(r["task_total"]["output_tokens"], 100)

    def test_headless_usage_never_raises(self):
        (self.q / "board").rmdir() if not any((self.q / "board").iterdir()) else None
        (self.q / "board").write_text("a file, not a dir") if not (self.q / "board").exists() else None
        usage.record_headless(self.q, "architect-pass", "ar-x", {"modelUsage": {"m": {"outputTokens": 1}}})

    def test_headless_usage_is_kept(self):
        usage.record_headless(self.q, "architect-pass", "ar-1", {"modelUsage": {"claude-opus-5-5": {
            "inputTokens": 5, "outputTokens": 9, "cacheReadInputTokens": 1, "cacheCreationInputTokens": 2, "costUSD": 0.3}},
            "total_cost_usd": 0.3, "num_turns": 4})
        h = usage.fold(self.q)["headless"]
        self.assertEqual((h[0]["review_id"], h[0]["models"]["claude-opus-5-5"]["outputTokens"]), ("ar-1", 9))


    def test_seats_by_headless_tag_and_session_cwd(self):
        """§24: headless sessions (and their subagents) are their kind's seat; calls without an agent_id go by
        their session's cwd: the product root is the design seat, the runner's checkout the runner, else other-sessions."""
        root = Path(self._d.name) / "prod"
        (root / ".ccp-runtime/runner").mkdir(parents=True)
        (root / "scratch-wt").mkdir()
        (self.q / "project.yaml").write_text(f"project_id: demo\nproduct_root: {root}\nrunner:\n  name: runner\n"
                                             f"  worktree: {root}/.ccp-runtime/runner   # detached\n")
        usage.record_headless(self.q, "architect-pass", "ar-1", {"session_id": "hs-0001"})
        main = dict(source="repl_main_thread")
        self.write("usage-requests.jsonl", self.rows(
            req("h1", 1, session__id="hs-0001", cwd=str(root), **main),            # the headless pass itself
            req("h2", 2, session__id="hs-0001", cwd=str(root)),                    # its subagent
            req("d1", 3, session__id="docs-0001", cwd=str(root), seat="docs-audit", **main),  # tagged by ccp.seat
            req("r1", 4, session__id="run-0001", cwd=f"{root}/.ccp-runtime/runner", model="claude-sonnet-5-5", out=7, **main),
            req("w1", 10, session__id="run-0001", cwd=f"{root}/.ccp-runtime/runner"),  # a worker inside the runner
            req("s1", 5, session__id="adhoc-001", cwd=f"{root}/scratch-wt", model="claude-haiku-5-5", out=11, **main),
            req("l1", 6, session__id="lead-0001", cwd=str(root), model="claude-opus-5-5", effort="xhigh", out=3, **main)))
        self.write("usage-spans.jsonl", [{"request_id": "h1"}, {"request_id": "h2", "agent_id": "a-sub"},
                                         {"request_id": "d1"}, {"request_id": "r1"}, {"request_id": "w1", "agent_id": "a1"},
                                         {"request_id": "s1"}, {"request_id": "l1"}])
        r = usage.fold(self.q, design_seat={"model": "claude-opus-5-5", "effort": "xhigh"})
        self.assertEqual(r["seats"]["architect-pass"]["requests"], 2)
        self.assertEqual(r["seats"]["docs-audit"]["requests"], 1)
        self.assertEqual(r["seats"]["runner"]["output_tokens"], 7)
        self.assertEqual(r["seats"]["other-sessions"]["output_tokens"], 11)
        self.assertEqual(list(r["other_sessions"]), [f"{root}/scratch-wt"])
        self.assertEqual((r["seats"]["design-seat"]["requests"], r["seats"]["design-seat"]["output_tokens"]), (1, 3))
        impl = next(x for x in r["runs"] if x["run_id"] == "0001-a/implement")
        self.assertEqual(impl["usage"]["requests"], 1)
        self.assertEqual(r["unattributed"]["requests"], 0)
        self.assertEqual(r["coverage"], 1.0)
        self.assertEqual(r["advice"], [], "only design-seat rows are compared with the expected lead")
        self.assertEqual((r["how"]["headless"], r["how"]["session"], r["how"]["lead"]), (3, 2, 1))

    def test_a_lead_on_another_model_or_effort_is_advised(self):
        self.write("usage-requests.jsonl", self.rows(req("l1", 40, model="claude-sonnet-5-5", effort="high",
                                                        source="repl_main_thread")))
        r = usage.fold(self.q, design_seat={"model": "claude-opus-5-5", "effort": "xhigh"})
        self.assertEqual(len(r["advice"]), 2)
        self.write("usage-requests.jsonl", self.rows(req("l2", 41, model="claude-opus-5-5[1m]", effort="xhigh",
                                                        source="repl_main_thread")))
        r = usage.fold(self.q, design_seat={"model": "claude-opus-5-5", "effort": "xhigh"})
        self.assertEqual(r["advice"], [])  # one call on the expected pair is enough: helper calls are not advice


def transcript(projects, cwd, sid, slug=None, sub=None):
    """A Claude Code transcript as 2.1.306 writes it: header records without cwd, then records with it.
    `sub` also writes a subagent / in-process teammate transcript under the lead's session folder."""
    d = Path(projects) / (slug or str(cwd).replace("/", "-").replace(".", "-"))
    d.mkdir(parents=True, exist_ok=True)
    head = [{"type": "last-prompt", "sessionId": sid}, {"type": "mode", "sessionId": sid}]
    body = [{"type": "attachment", "cwd": str(cwd), "sessionId": sid}, {"type": "user", "cwd": str(cwd), "sessionId": sid}]
    (d / f"{sid}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in head + body))
    if sub:
        s = d / sid / "subagents"
        s.mkdir(parents=True)
        (s / f"agent-{sub}.jsonl").write_text(json.dumps({"type": "user", "cwd": str(cwd), "sessionId": sid,
                                                          "agentId": sub}) + "\n")
        (s / f"agent-{sub}.meta.json").write_text(json.dumps({"taskKind": "in_process_teammate", "name": "probe"}))
    return d / f"{sid}.jsonl"


class SessionRouting(unittest.TestCase):
    """§24: ccp.project_id first, then session → transcript cwd → product_root, else the system sink."""

    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        d = Path(os.path.realpath(self._d.name))
        self.d = d
        self.real = d / "real" / "Product"
        (self.real / ".git").mkdir(parents=True)
        (d / "link").mkdir()
        os.symlink(d / "real", d / "link" / "real")  # a home-directory symlink to a mounted volume, in small
        self.prodq, self.demoq = d / "prodq", d / "demoq"
        self.prodq.mkdir()
        self.demoq.mkdir()
        (d / "projects").mkdir()
        (d / "projects/example-product.yaml").write_text(
            f"project_id: example-product\nproduct_root: {d / 'link/real/Product'}\nqueue_root: {self.prodq}\n")
        (d / "projects/demo.yaml").write_text(f"project_id: demo\nqueue_root: {self.demoq}\n")
        self.claude = d / "claude-projects"
        self.claude.mkdir()
        self.sys = d / "telemetry"
        self.patch = mock.patch.dict(os.environ, {"CCP_BINDINGS_DIR": str(d / "projects"),
                                                  "CCP_TELEMETRY_DIR": str(self.sys),
                                                  "CCP_CLAUDE_PROJECTS_DIR": str(self.claude)})
        self.patch.start()
        self.sink = otel.Sink()
        self.srv = otel.http.server.ThreadingHTTPServer(("127.0.0.1", 0), otel.handler(self.sink))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.patch.stop()
        self._d.cleanup()

    def post(self, path, body):
        r = urllib.request.Request(self.url + path, data=json.dumps(body).encode(), method="POST",
                                   headers={"Content-Type": "application/json"})
        return urllib.request.urlopen(r).status

    def rows(self, q, name="usage-requests.jsonl"):
        p = q / "board" / name
        return [json.loads(x) for x in p.read_text().splitlines()] if p.is_file() else []

    def system_rows(self, name="usage-requests"):
        return [json.loads(x) for f in sorted(self.sys.glob(f"{name}-*.jsonl")) for x in f.read_text().splitlines()]

    def status(self):
        with urllib.request.urlopen(self.url + "/status") as resp:
            return json.loads(resp.read())

    def test_project_id_comes_first(self):
        transcript(self.claude, self.real, "sess-wi-0001")
        self.post("/v1/logs", logs("demo", req("r1", 1, session__id="sess-wi-0001")))
        self.assertEqual([r["routed_by"] for r in self.rows(self.demoq)], ["project_id"])
        self.assertEqual(self.rows(self.prodq), [])

    def test_routes_by_session_cwd_through_a_symlinked_root(self):
        # The binding names the symlinked path, the transcript the real one: realpaths are compared.
        transcript(self.claude, self.real, "sess-wi-0001")
        self.post("/v1/logs", logs(None, req("r1", 1, session__id="sess-wi-0001")))
        (row,) = self.rows(self.prodq)
        self.assertEqual((row["project_id"], row["routed_by"], row["cwd"], row["request_id"]),
                         ("example-product", "session", str(self.real), "r1"))
        # And the other way round: a transcript under the symlink, a binding on the real path.
        (self.d / "projects/example-product.yaml").write_text(
            f"project_id: example-product\nproduct_root: {self.real}\nqueue_root: {self.prodq}\n")
        self.sink._binds = None
        transcript(self.claude, self.d / "link/real/Product", "sess-ex-0002")
        self.post("/v1/logs", logs(None, req("r2", 2, session__id="sess-ex-0002")))
        self.assertEqual([r["request_id"] for r in self.rows(self.prodq)], ["r1", "r2"])

    def test_a_worktree_under_the_root_and_a_git_worktree_elsewhere_route_to_the_project(self):
        wt = self.real / ".ccp-runtime" / "impl-0233"
        wt.mkdir(parents=True)
        transcript(self.claude, wt, "sess-wt-0001")
        gitwt = self.real / ".git" / "worktrees" / "spike"
        gitwt.mkdir(parents=True)
        outside = self.d / "elsewhere" / "spike"
        outside.mkdir(parents=True)
        (outside / ".git").write_text(f"gitdir: {gitwt}\n")
        transcript(self.claude, outside / "sub", "sess-wt-0002")
        self.post("/v1/logs", logs(None, req("r1", 1, session__id="sess-wt-0001"), req("r2", 2, session__id="sess-wt-0002")))
        self.assertEqual([(r["request_id"], r["routed_by"]) for r in self.rows(self.prodq)], [("r1", "session"), ("r2", "session")])

    def test_teammates_and_subagents_route_with_their_lead(self):
        # Their telemetry carries the lead's session.id; their transcripts sit under the lead's session folder.
        transcript(self.claude, self.real, "0b3f6c1e-2d4a-4e8b-9c7d-5a1f2e3d4c5b", sub="agent-test-0001")
        sid = "0b3f6c1e-2d4a-4e8b-9c7d-5a1f2e3d4c5b"
        self.post("/v1/traces", spans(None, {"t": T0, "request_id": "r1", "agent_id": "probe@session-d7058efc",
                                             "session__id": sid},
                                      {"t": T0, "request_id": "r2", "agent_id": "a46ac22784cf2bda3", "session__id": sid}))
        self.post("/v1/logs", logs(None, req("r1", 1, session__id=sid)))
        self.assertEqual([s["agent_id"] for s in self.rows(self.prodq, "usage-spans.jsonl")],
                         ["probe@session-d7058efc", "a46ac22784cf2bda3"])
        self.assertEqual(len(self.rows(self.prodq)), 1)
        self.assertEqual(self.system_rows(), [])

    def test_a_miss_waits_and_routes_once_the_transcript_appears(self):
        self.post("/v1/logs", logs(None, req("r1", 1, session__id="sess-late-01")))
        self.assertEqual((self.system_rows(), self.status()["pending"]), ([], 1), "a miss waits; it is not written")
        transcript(self.claude, self.real, "sess-late-01")
        self.post("/v1/logs", logs(None, req("r2", 2, session__id="sess-late-01")))
        self.assertEqual(self.rows(self.prodq), [], "within the miss TTL the session is not looked up again")
        self.sink.misses["sess-late-01"] -= self.sink.miss_ttl  # the TTL passes
        self.assertEqual(self.sink.tick(), 2)  # the receiver's ticker
        self.assertEqual([r["request_id"] for r in self.rows(self.prodq)], ["r1", "r2"])
        self.post("/v1/logs", logs(None, req("r3", 3, session__id="sess-late-01")))
        self.assertEqual([r["request_id"] for r in self.rows(self.prodq)], ["r1", "r2", "r3"])
        self.assertIn("sess-late-01", self.sink.sessions)  # a hit is cached for good
        self.assertEqual((self.system_rows(), self.status()["pending"]), ([], 0))

    def test_a_session_that_never_resolves_goes_to_the_system_sink_after_the_hold(self):
        self.post("/v1/logs", logs(None, req("r1", 1, session__id="sess-never-1")))
        self.sink.tick()
        self.assertEqual(self.system_rows(), [])
        for rows in self.sink.pending.values():  # the hold passes
            rows[:] = [(t - self.sink.hold_s, *rest) for t, *rest in rows]
        self.sink.tick()
        self.assertEqual([r["request_id"] for r in self.system_rows()], ["r1"])
        # Shutdown writes whatever still waits.
        self.post("/v1/logs", logs(None, req("r2", 2, session__id="sess-never-2")))
        self.sink.tick(flush=True)
        self.assertEqual([r["request_id"] for r in self.system_rows()], ["r1", "r2"])
        self.assertEqual(self.status()["unresolved"], 2)

    def test_the_buffer_is_bounded(self):
        self.sink.max_pending = 2
        self.post("/v1/logs", logs(None, req("r1", 1, session__id="sess-old-001")))
        self.post("/v1/logs", logs(None, req("r2", 2, session__id="sess-new-001"), req("r3", 3, session__id="sess-new-002")))
        self.assertEqual([r["request_id"] for r in self.system_rows()], ["r1"])
        self.assertEqual(self.status()["pending"], 2)

    def test_everything_else_goes_to_the_system_sink_labelled(self):
        transcript(self.claude, "/home/user/notes", "sess-notes-01")
        self.post("/v1/logs", logs(None, req("r1", 1, session__id="sess-notes-01", prompt="never kept"),
                                   req("r2", 2, session__id="../../etc/passwd")))
        rows = self.system_rows()
        self.assertEqual([(r["request_id"], r["cwd"]) for r in rows], [("r1", "/home/user/notes"), ("r2", None)])
        self.assertEqual(rows[0]["session_id"], "sess-notes-01")
        self.assertNotIn("never kept", json.dumps(rows))
        st = self.status()
        self.assertEqual((st["written_by_sink"], st["unresolved"]), ({"project": 0, "system": 2}, 1))

    def test_status_counts_per_sink_and_route(self):
        transcript(self.claude, self.real, "sess-wi-0001")
        self.post("/v1/logs", logs("demo", req("r1", 1)))
        self.post("/v1/logs", logs(None, req("r2", 2, session__id="sess-wi-0001"), req("r3", 3, session__id="nosuchsession")))
        self.sink.tick(flush=True)
        st = self.status()
        self.assertEqual(st["written"], 3)
        self.assertEqual(st["written_by_sink"], {"project": 2, "system": 1})
        self.assertEqual(st["routed_by"], {"project_id": 1, "session": 1})
        self.assertEqual(st["unresolved"], 1)

    def test_a_browser_content_type_is_refused(self):
        import urllib.error
        for ct in ("text/plain;x=json", "application/json-seq", "text/json"):
            r = urllib.request.Request(self.url + "/v1/logs", data=json.dumps(logs("demo", req("r1", 1))).encode(),
                                       method="POST", headers={"Content-Type": ct})
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(r)
            self.assertEqual(cm.exception.code, 415, ct)
        r = urllib.request.Request(self.url + "/v1/logs", data=json.dumps(logs("demo", req("r1", 1))).encode(),
                                   method="POST", headers={"Content-Type": "Application/JSON; charset=utf-8"})
        self.assertEqual(urllib.request.urlopen(r).status, 200)
        self.assertEqual(len(self.rows(self.demoq)), 1)

    def test_an_unbound_project_id_is_capped(self):
        self.post("/v1/logs", logs("x" * 200, req("r1", 1)))
        self.post("/v1/logs", logs("Bad Id!", req("r2", 2)))
        self.post("/v1/logs", logs("later-project", req("r3", 3)))
        self.assertEqual([r.get("project_id_unbound") for r in self.system_rows()], [None, None, "later-project"])

    def test_the_route_cache_follows_the_bindings(self):
        other = self.d / "other"
        other.mkdir()
        transcript(self.claude, other, "sess-other-1")
        self.post("/v1/logs", logs(None, req("r1", 1, session__id="sess-other-1")))
        self.assertEqual(len(self.system_rows()), 1)
        (self.d / "projects/other.yaml").write_text(f"project_id: other\nproduct_root: {other}\nqueue_root: {self.demoq}\n")
        self.post("/v1/logs", logs(None, req("r2", 2, session__id="sess-other-1")))
        self.assertEqual(len(self.system_rows()), 2, "within the bindings TTL the cached route holds")
        self.sink._binds_at -= self.sink.bindings_ttl
        self.post("/v1/logs", logs(None, req("r3", 3, session__id="sess-other-1")))
        self.assertEqual([(r["request_id"], r["project_id"]) for r in self.rows(self.demoq)], [("r3", "other")])

    def test_project_id_rows_keep_their_session_cwd(self):
        transcript(self.claude, self.real, "sess-wi-0001")
        self.post("/v1/logs", logs("demo", req("r1", 1, session__id="sess-wi-0001")))
        (row,) = self.rows(self.demoq)
        self.assertEqual((row["session_id"], row["cwd"]), ("sess-wi-0001", str(self.real)))

    def test_old_system_day_files_are_pruned(self):
        self.sys.mkdir()
        (self.sys / "usage-requests-2001-01-01.jsonl").write_text("{}\n")
        self.post("/v1/logs", logs(None, req("r1", 1, session__id="nosuchsession")))
        self.sink.tick(flush=True)
        self.assertFalse((self.sys / "usage-requests-2001-01-01.jsonl").exists())
        self.assertEqual(len(self.system_rows()), 1)


class SystemUsage(unittest.TestCase):
    def test_by_cwd_and_day(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"CCP_TELEMETRY_DIR": d}):
            rows = [{"at": "2026-10-20T10:00:00Z", "request_id": "a", "cwd": "/home/user/notes", "model": "m1",
                     "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.5},
                    {"at": "2026-10-21T10:00:00Z", "request_id": "b", "cwd": "/home/user/notes", "model": "m2",
                     "output_tokens": 100, "cost_usd": 1.0},
                    {"at": "2026-10-21T11:00:00Z", "request_id": "b", "cwd": "/home/user/notes", "model": "m2",
                     "output_tokens": 100, "cost_usd": 1.0},  # an exporter retry: counted once
                    {"at": "2026-10-21T12:00:00Z", "request_id": "c", "cwd": None, "output_tokens": 1}]
            (Path(d) / "usage-requests-2026-10-20.jsonl").write_text(json.dumps(rows[0]) + "\n")
            (Path(d) / "usage-requests-2026-10-21.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows[1:]))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.main(["usage", "--system", "--json"]), 0)
            r = json.loads(out.getvalue())
            self.assertEqual(r["total"]["requests"], 3)
            notes = r["by_cwd"]["/home/user/notes"]
            self.assertEqual((notes["requests"], notes["output_tokens"], notes["observed_models"]), (2, 105, ["m1", "m2"]))
            self.assertIn("(unknown session)", r["by_cwd"])
            self.assertEqual(sorted(r["by_day"]), ["2026-10-20", "2026-10-21"])
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.main(["usage", "--system", "--since", "2026-10-21"]), 0)
            self.assertIn("/home/user/notes", out.getvalue())
            self.assertNotIn("2026-10-20", out.getvalue())
            with redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["usage", "--system", "--since", "yesterday"]), 2)
            out = io.StringIO()
            with redirect_stdout(out):  # a global --root does not turn it into the project fold
                self.assertEqual(cli.main(["--root", d, "usage", "--system", "--json"]), 0)
            self.assertEqual(json.loads(out.getvalue())["total"]["requests"], 3)


class HeadlessEnv(unittest.TestCase):
    def test_tags_project_and_seat_and_keeps_other_attributes(self):
        import sys
        sys.path.insert(0, str(PLANE / "scripts/observability"))
        import spec_maintainer as sm
        with mock.patch.dict(os.environ, {"OTEL_RESOURCE_ATTRIBUTES": "team=x,ccp.project_id=old", "ANTHROPIC_API_KEY": "k"}):
            env = sm.headless_env("demo", "docs-audit")
        self.assertEqual(env["OTEL_RESOURCE_ATTRIBUTES"], "team=x,ccp.project_id=demo,ccp.seat=docs-audit")
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        body = logs("demo", req("r1", 1))
        body["resourceLogs"][0]["resource"]["attributes"] += kv(ccp__seat="docs-audit")
        self.assertEqual(otel.fold_logs(body)[0][1]["seat"], "docs-audit")
        body["resourceLogs"][0]["resource"]["attributes"][-1]["value"] = {"stringValue": "../Not A Seat"}
        self.assertNotIn("seat", otel.fold_logs(body)[0][1])


class OtelCli(unittest.TestCase):
    def test_env_is_the_user_settings_block_and_needs_no_product(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as d, redirect_stdout(out):
            cwd = os.getcwd()
            os.chdir(d)
            try:
                self.assertEqual(cli.main(["otel", "env", "--port", "4318"]), 0)
            finally:
                os.chdir(cwd)
        env = json.loads(out.getvalue())["env"]
        self.assertNotIn("OTEL_RESOURCE_ATTRIBUTES", env)
        self.assertEqual(env["CLAUDE_CODE_ENHANCED_TELEMETRY_BETA"], "1")
        self.assertEqual(env["OTEL_EXPORTER_OTLP_ENDPOINT"], "http://127.0.0.1:4318")

    def test_env_for_a_project_splits_the_project_and_user_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "demo.yaml").write_text("project_id: demo\nproduct_root: /work/demo\n")
            with mock.patch.dict(os.environ, {"CCP_BINDINGS_DIR": d}):
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(cli.main(["otel", "env", "--project", "demo", "--port", "4318"]), 0)
                body = json.loads(out.getvalue())
                self.assertEqual(body["project"], {"path": "/work/demo/.claude/settings.json",
                                                   "env": {"OTEL_RESOURCE_ATTRIBUTES": "ccp.project_id=demo"}})
                self.assertEqual(body["user"]["env"], otel.env_block(4318))
                self.assertNotIn("OTEL_RESOURCE_ATTRIBUTES", body["user"]["env"])
                self.assertIn("(or the shell)", body["user"]["path"])
                self.assertIn("remove them from the product's settings", err.getvalue())
                for bad in ("nope", "../demo", "Demo"):
                    err = io.StringIO()
                    with redirect_stdout(io.StringIO()), redirect_stderr(err):
                        self.assertEqual(cli.main(["otel", "env", "--project", bad]), 2)
                    self.assertIn("not a bound project", err.getvalue())

    def test_status_checks_the_user_settings(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.json"
            with mock.patch.dict(os.environ, {"CCP_USER_SETTINGS": str(p)}):
                self.assertFalse(otel.user_settings_check(4318)["ok"])
                p.write_text(json.dumps({"env": {**otel.env_block(4318), "OTHER": "x"}}))
                self.assertEqual(otel.user_settings_check(4318), {"path": str(p), "ok": True, "missing": []})
                c = otel.user_settings_check(4319)
                self.assertEqual((c["ok"], c["missing"]), (False, ["OTEL_EXPORTER_OTLP_ENDPOINT"]))
                p.write_text(json.dumps({"env": {**otel.env_block(4318), "OTEL_RESOURCE_ATTRIBUTES": "ccp.project_id=x"}}))
                self.assertIn("ccp.project_id", otel.user_settings_check(4318)["warnings"][0])
                c = otel.user_settings_check(4319)  # both problems are reported
                self.assertEqual(len(c["warnings"]), 2)
                self.assertEqual(c["missing"], ["OTEL_EXPORTER_OTLP_ENDPOINT"])

    def test_status_warns_on_content_logging_keys(self):
        """§24: OTEL_LOG_USER_PROMPTS / OTEL_LOG_TOOL_DETAILS in the user settings or the shell warn, by name."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.json"
            with mock.patch.dict(os.environ, {"CCP_USER_SETTINGS": str(p)}):
                p.write_text(json.dumps({"env": {**otel.env_block(4318), "OTEL_LOG_USER_PROMPTS": "leak-a",
                                                 "OTEL_LOG_TOOL_DETAILS": ""}}))
                c = otel.user_settings_check(4318, shell={"OTEL_LOG_TOOL_DETAILS": "leak-b", "OTEL_LOG_USER_PROMPTS": " "})
                self.assertFalse(c["ok"])
                self.assertEqual(len(c["warnings"]), 2)
                self.assertIn(f"OTEL_LOG_USER_PROMPTS is set in {p}", c["warnings"][0])
                self.assertIn("OTEL_LOG_TOOL_DETAILS is set in the environment", c["warnings"][1])
                self.assertNotIn("leak", json.dumps(c))  # key names only, never values
                self.assertTrue(otel.user_settings_check(4318, shell={})["warnings"])  # the settings key alone
                p.write_text(json.dumps({"env": otel.env_block(4318)}))
                self.assertEqual(otel.user_settings_check(4318, shell={}), {"path": str(p), "ok": True, "missing": []})
                with mock.patch.dict(os.environ, {"OTEL_LOG_USER_PROMPTS": "1"}):
                    self.assertIn("the environment", otel.user_settings_check(4318)["warnings"][0])
                p.write_text(json.dumps({"env": ["not", "a", "dict"]}))
                c = otel.user_settings_check(4318, shell={"OTEL_LOG_USER_PROMPTS": "1"})
                self.assertEqual(len(c["warnings"]), 2)  # no env block, and the shell key
                p.unlink()
                c = otel.user_settings_check(4318, shell={"OTEL_LOG_USER_PROMPTS": "1"})
                self.assertEqual(len(c["warnings"]), 2)  # no env block, and the shell key

    def _launchctl(self, bootstrap_codes, loaded_after_bootout=1, state="running"):
        """A fake launchctl: `print` finds the service `loaded_after_bootout` times after bootout,
        then not until a bootstrap succeeds; each bootstrap returns the next code in `bootstrap_codes`."""
        import subprocess
        calls, live = [], {"n": loaded_after_bootout, "up": False}
        codes = list(bootstrap_codes)

        def run(cmd, **_kw):
            self.assertEqual(cmd[0], "launchctl")
            calls.append(cmd[1])
            if cmd[1] == "print":
                if live["up"] or live["n"] > 0:
                    live["n"] -= 0 if live["up"] else 1
                    return subprocess.CompletedProcess(cmd, 0, f"\tstate = {state}\n", "")
                return subprocess.CompletedProcess(cmd, 113, "", "Could not find service")
            if cmd[1] == "bootstrap":
                code = codes.pop(0)
                live["up"] = code == 0
                return subprocess.CompletedProcess(cmd, code, "", "" if code == 0 else
                                                   f"Bootstrap failed: {code}: " + ("Input/output error" if code == 5 else "Operation already in progress"))
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return run, calls

    def test_install_waits_for_bootout_and_retries_a_bootstrap_eio(self):
        from ccp import queue as q
        run, calls = self._launchctl([5, 0], loaded_after_bootout=2)
        sleeps = []
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(otel, "_plist_path", return_value=Path(d) / "otel.plist"), \
                mock.patch.object(q.subprocess, "run", side_effect=run), \
                mock.patch.object(q.time, "sleep", side_effect=sleeps.append):
            body = otel.launchd("install", 4318)
        self.assertTrue(body["ok"], body)
        self.assertEqual((body["bootstrap_attempts"], body["state"]), (2, "running"))
        self.assertNotIn("error", body)
        # bootout, then print until gone (2 found, 1 gone), then bootstrap twice, then the check.
        self.assertEqual(calls[:6], ["bootout", "print", "print", "print", "bootstrap", "bootstrap"])
        self.assertEqual(sleeps[:3], [0.5, 0.5, 1])

    def test_install_reports_a_bootstrap_that_keeps_failing(self):
        from ccp import queue as q
        run, calls = self._launchctl([5, 5, 5, 5])
        sleeps = []
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(otel, "_plist_path", return_value=Path(d) / "otel.plist"), \
                mock.patch.object(q.subprocess, "run", side_effect=run), \
                mock.patch.object(q.time, "sleep", side_effect=sleeps.append):
            body = otel.launchd("install", 4318)
        self.assertFalse(body["ok"])
        self.assertEqual(body["bootstrap_attempts"], 4)
        self.assertIn("Input/output error", body["error"])
        self.assertEqual([s for s in sleeps if s != 0.5], [1, 2, 4])
        # Another error is not retried; a loaded but stopped receiver is reported.
        run, calls = self._launchctl([37])
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(otel, "_plist_path", return_value=Path(d) / "otel.plist"), \
                mock.patch.object(q.subprocess, "run", side_effect=run), \
                mock.patch.object(q.time, "sleep"):
            body = otel.launchd("install", 4318)
        self.assertEqual((body["ok"], body["bootstrap_attempts"]), (False, 1))
        run, calls = self._launchctl([0], state="not running")
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(otel, "_plist_path", return_value=Path(d) / "otel.plist"), \
                mock.patch.object(q.subprocess, "run", side_effect=run), \
                mock.patch.object(q.time, "sleep"):
            body = otel.launchd("install", 4318)
        self.assertFalse(body["ok"])
        self.assertIn("not running", body["error"])

    def test_board_install_shares_the_retry_and_needs_only_loaded(self):
        from ccp import board, queue as q
        run, calls = self._launchctl([5, 0], state="not running")  # StartInterval: idle between builds
        p = Product()
        try:
            with tempfile.TemporaryDirectory() as d, mock.patch("pathlib.Path.home", return_value=Path(d)), \
                    mock.patch.object(q.subprocess, "run", side_effect=run), mock.patch.object(q.time, "sleep"):
                body = board.launchd(p.cfg, "install")
                self.assertTrue(Path(body["plist"]).is_relative_to(d))
        finally:
            p.cleanup()
        self.assertTrue(body["ok"], body)
        self.assertEqual(body["bootstrap_attempts"], 2)

    def test_launchd_runs_the_run_checkout(self):
        from ccp import board
        from ccp.queue import PLANE as Q
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "bin").mkdir()
            (Path(d) / "bin/ccp").write_text("#!/bin/sh\n")
            with mock.patch.dict(os.environ, {"CCP_RUN_CHECKOUT": d}):
                self.assertIn(f"<string>{d}/bin/ccp</string><string>otel</string>", otel._plist(4318))
                p = Product()
                try:
                    self.assertIn(f"<string>{d}/bin/ccp</string><string>--root</string>", board._plist(p.cfg, 5)[1])
                finally:
                    p.cleanup()
        # No run checkout (a cloud clone): this checkout's own.
        self.assertIn(f"<string>{Q}/bin/ccp</string>", otel._plist(4318))
        from ccp.queue import run_ccp_warning
        self.assertIn("has no bin/ccp", run_ccp_warning())  # the fence names a run checkout that is not there

    def test_a_product_telemetry_block_is_not_required_and_is_flagged_as_ignored(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "prod"
            (root / ".claude").mkdir(parents=True)
            yml = Path(d) / "demo.yaml"
            yml.write_text(f"project_id: demo\nproduct_root: {root}\n")
            sync = ["bash", str(PLANE / "scripts/sync-product-docs.sh"), "demo", "--project-yaml", str(yml), "--check"]
            (root / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {"ccp@ccp": True}}))
            clean = subprocess.run(sync, capture_output=True, text=True)
            self.assertNotIn("telemetry", clean.stdout + clean.stderr)
            (root / ".claude/settings.json").write_text(json.dumps({
                "enabledPlugins": {"ccp@ccp": True},
                "env": {"CLAUDE_CODE_ENABLE_TELEMETRY": "1", "OTEL_RESOURCE_ATTRIBUTES": "ccp.project_id=demo", "X": "1"}}))
            r = subprocess.run(sync, capture_output=True, text=True)
            self.assertEqual(r.returncode, clean.returncode, r.stdout + r.stderr)
            self.assertIn("note: .claude/settings.json: env CLAUDE_CODE_ENABLE_TELEMETRY "
                          "is ignored by Claude Code", r.stdout)
            self.assertIn("OTEL_RESOURCE_ATTRIBUTES with ccp.project_id is the supported project key", r.stdout)
            self.assertNotIn("DRIFT .claude/settings.json", r.stdout)
            # The project id attribute alone is the supported project key: no note.
            (root / ".claude/settings.json").write_text(json.dumps({
                "enabledPlugins": {"ccp@ccp": True},
                "env": {"OTEL_RESOURCE_ATTRIBUTES": "ccp.project_id=demo"}}))
            r = subprocess.run(sync, capture_output=True, text=True)
            self.assertNotIn("ignored by Claude Code", r.stdout)
            self.assertEqual(otel.product_block_keys({"env": {"OTEL_RESOURCE_ATTRIBUTES": "x", "OTEL_LOGS_EXPORTER": "otlp"}}),
                             ["OTEL_LOGS_EXPORTER"])
