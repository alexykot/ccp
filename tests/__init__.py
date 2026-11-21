"""Tests never read a live binding's queue (SPEC §9) and are not a product's run checkout (§29.2)."""
import os

os.environ["CCP_DEV"] = "1"
os.environ["CCP_NO_BINDING_QUEUE"] = "1"
# §28.3: no test starts a detached board build; the refresh tests mock the spawn and lift this.
os.environ["CCP_NO_BOARD_REFRESH"] = "1"
# §24: no test reads Claude Code's real transcripts or user settings, writes the real system
# telemetry sink, or plists a real run checkout; the tests that need them name temp dirs.
os.environ["CCP_CLAUDE_PROJECTS_DIR"] = "/nonexistent/claude-projects-guard"
os.environ["CCP_TELEMETRY_DIR"] = "/nonexistent/control-plane-telemetry-guard"
os.environ["CCP_USER_SETTINGS"] = "/nonexistent/claude-user-settings-guard.json"
os.environ["CCP_RUN_CHECKOUT"] = "/nonexistent/control-plane-run-guard"
os.environ["CCP_OTEL_LABEL"] = "ccp.test.no-such-receiver"  # run-checkout.sh never signals the live one
os.environ["CCP_BINDINGS_DIR"] = "/nonexistent/control-plane-bindings-guard"
# §25.1: the allowance reader's cache is shared by every product on the machine; a test's stub
# command, rewritten between two claims, would be reused or backed off from by the next. So every
# test reads unshared (each call runs its command, no cache); the shared reader's tests unset this.
os.environ["CCP_ALLOWANCE_UNSHARED"] = "1"
# §15.2, §15.5: no test calls the real gh (GitHub); the tests that read a PR name a stand-in.
os.environ["CCP_GH_BIN"] = "/nonexistent/gh-guard"
# §14: a seat's exported queue and binding never reach a test; the tests that need one set their own.
for _k in ("QUEUE_ROOT", "PROJECT_YAML"):
    os.environ.pop(_k, None)
# §24: `ccp otel status` warns on these in the shell; a developer's own settings must not reach the tests.
for _k in ("OTEL_LOG_USER_PROMPTS", "OTEL_LOG_TOOL_DETAILS"):
    os.environ.pop(_k, None)
# §14.1: the plane's own suite may run under `ccp suite run`; its tests' runs are not nested in it.
os.environ.pop("CCP_SUITE_ID", None)
# §12.1, §29.2: a suite run through `ccp wt exec` hands its children the child marker; no test inherits it.
os.environ.pop("CCP_WT_EXEC", None)
# §14.1 summary mode: a run with no queue logs to a temp file; the tests' go to one directory, removed at exit.
import atexit  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402

os.environ["CCP_SUITE_LOG_DIR"] = tempfile.mkdtemp(prefix="ccp-test-suite-logs-")
atexit.register(shutil.rmtree, os.environ["CCP_SUITE_LOG_DIR"], True)
# §29.3: `ccp sandbox create` makes its sandboxes only below this root, removed at exit.
os.environ["CCP_SANDBOX_ROOT"] = tempfile.mkdtemp(prefix="ccp-test-sandboxes-")
atexit.register(shutil.rmtree, os.environ["CCP_SANDBOX_ROOT"], True)
# §26.3 phase B: no test starts a detached estimator batch (or a real `claude -p`); the trigger
# tests mock the spawn and lift this.
os.environ["CCP_NO_ESTIMATOR_SPAWN"] = "1"
os.environ["CCP_ESTIMATOR_CLAUDE_BIN"] = "/nonexistent/claude-estimator-guard"
