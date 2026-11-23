---
task_id: 0312-every-atomic-write-takes-a-unique-temporary-name-and-removes-it-when-the-write-fails
title: Every atomic write goes through one helper that takes a unique temporary name beside the file and removes it when the write fails, so two concurrent writers of one file both succeed
status: pending
kind: feature
depends_on: []
spec_refs: ["S16", "S23", "S31"]
review_point: R31
paths: ["scripts/observability/lib.py", "scripts/observability/CLAUDE.md", "ccp/board.py", "ccp/calibrate.py", "ccp/forecast.py", "ccp/init.py", "ccp/suite.py", "ccp/upgrade.py", "ccp/verify.py", "tests/test_atomic_write.py"]
clashes_with: []
adopt: "none"
created: 2026-11-23
updated: 2026-11-23
---

# Task: 0312-every-atomic-write-takes-a-unique-temporary-name-and-removes-it-when-the-write-fails

## Intent

Two runners that claim at the same moment both get their claim. Today each claim's auth probe writes
`QUEUE_ROOT/auth/status.json` through `write_json`, whose temporary file has a fixed name, so one writer's
`os.replace` can find the temporary file already moved by the other and the claim dies with a
`FileNotFoundError` traceback. When this is done every atomic write in `ccp` and the observability scripts
goes through one helper whose temporary file has a name no other writer uses, in the same directory as the
file, and a write that fails leaves no temporary file behind.

## Context (not checked)

The lead's priority item (a friction seen when two runners claimed at once). Measured at `b09de675`
(origin/main) unless a line says otherwise.

- **The race.** `scripts/observability/lib.py` `"def write_json"` writes
  `tmp = path.with_suffix(path.suffix + ".tmp")`, then `tmp.replace(path)`. `ccp/queue.py`'s `write_json` calls it,
  and `ccp/wt.py` writes `q / "auth" / "status.json"` through it
  (`git grep -n 'auth" / "status.json' -- ccp` at `b09de675`: 1 line). A probe at `b09de675`, run from the checkout root,
  `python3 -B -c 'import sys,pathlib,tempfile; from concurrent.futures import ThreadPoolExecutor as T; sys.path.insert(0,"scripts/observability"); import lib; p=pathlib.Path(tempfile.mkdtemp())/"status.json"; x=T(2); fs=[x.submit(lib.write_json,p,{"i":i}) for i in range(600)]; x.shutdown(); print(sum(f.exception() is not None for f in fs), sorted(q.name for q in p.parent.iterdir()))'`,
  printed `127 ['status.json']`, then `120` and `137` on two more runs: that many of the writes raised
  `FileNotFoundError`.
- **The leftover.** A probe at `b09de675`,
  `python3 -B -c 'import sys,pathlib,tempfile; from concurrent.futures import ThreadPoolExecutor as T; sys.path.insert(0,"scripts/observability"); import lib; d=pathlib.Path(tempfile.mkdtemp()); (d/"t.json"/"sub").mkdir(parents=True); f=T(1).submit(lib.write_json,d/"t.json",{"a":1}); print(type(f.exception()).__name__, sorted(q.name for q in d.iterdir()))'`,
  printed `IsADirectoryError ['t.json', 't.json.tmp']`: a write whose replace fails leaves its temporary file.
- **Every site.** `git grep -nE 'tmp = .*\.tmp' -- ccp scripts bin plugin` at `b09de675`: 9 lines.
  - A fixed name, so two writers of one file race: `scripts/observability/lib.py` (`write_json`),
    `ccp/calibrate.py` (`"def model"`, the calibration cache), `ccp/init.py` (`"def _record_consent"`, the machine
    file), `ccp/upgrade.py` (`"def _record"`, plane.json's upgrade records), and `ccp/verify.py` twice
    (`"def write_record"` and `"def record_catch_up"`, the verification record).
  - The process id only, so two threads of one process race: `ccp/board.py` (`"def _atomic"`), `ccp/forecast.py`
    (`"def cached_fit"`, whose name `.tmp<pid>` does not even end `.tmp`), and `ccp/suite.py` (`"def take_lane"`, the
    exclusive lane's holder record).
  - Already unique: `git grep -n mkstemp -- ccp scripts bin plugin` at `b09de675`: 4 lines
    (`scripts/gate_parallel.py` once, `scripts/sync-product-docs.sh` three times). They stay: they are out of this task.
- **Why not `tempfile.mkstemp`.** It creates the file with mode `0600`, and the replace keeps that mode, so plane.json
  (written by `upgrade`) and the machine file would lose their group and other read bits. The helper creates the
  temporary file with `open(..., "x")`, the process's umask applying as it does today.
- **A killed writer.** A process killed mid-write (SIGKILL, a power cut) leaves its hidden `.<name>.<pid>.<hex>.tmp`
  beside the file, as it leaves `<name>.tmp` today; §31.3 skips it. A sweep of old temporary files is Out: it is rare,
  harmless (nothing reads the name), and a sweep would need an age rule of its own.
- **No SPEC change.** `git grep -nE '\.tmp|temporary file' -- docs/spec` at `b09de675`: 1 line,
  `docs/spec/05-operations.md` (§31.3: "an atomic write's `*.tmp`" is not listed as a leftover). The new names end
  `.tmp`, so `queue.leftover_entries` and `queue.script_findings` still skip them, and a reader that globs `*.json`
  never sees one.
- **Clashes.** A script over the pending tasks' `paths` at `b09de675` (each pending task file's `paths` matched,
  globs too, against this task's) found: 0191 (`scripts/observability/lib.py`, `ccp/init.py`, `ccp/upgrade.py`: the
  grace release's old key places), 0296 and 0303 (`lib.py`: the config loader; the actor check before a write), 0306
  (`ccp/verify.py`: `head_errors`, `main`'s record action, `merge_ok`), 0310 (`lib.py` one comment line, and
  `ccp/suite.py` `ended_summary`) and 0311 (`ccp/suite.py`: the staged part lane). None changes a temporary name, a
  replace or the functions this task names (`git grep -nE 'write_json|_atomic|\.tmp|os\.replace|write_record|record_catch_up|take_lane|cached_fit|_record_consent' -- <those task files>`
  at `b09de675`: one hit, 0303's line on `heartbeat.sh` calling `write_json` after its actor check, which leaves
  `write_json` as it is). So `clashes_with` is empty.

### Rulings for the build (the lead's)

- **The helper.** `scripts/observability/lib.py` gains `def write_atomic(path: Path, text: str) -> None`. It sets
  `tmp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")` (same directory, hidden, ending
  `.tmp`), writes `text` through `open(tmp, "x", encoding="utf-8", newline="")`, then `os.replace(tmp, path)`. If
  anything raises from the open to the replace (`BaseException`), it runs `tmp.unlink(missing_ok=True)` and re-raises.
  It takes text only: upgrade's `write_bytes(new.encode("utf-8"))` is the same bytes as `new` written this way
  (`newline=""` translates nothing), so no bytes path is added. It does not create the directory: each caller does that,
  as today.
- **The callers.** `lib.write_json` keeps its `mkdir` and calls `write_atomic(path, json.dumps(obj, indent=2) + "\n")`.
  Each of the eight other sites above writes through `lib.write_atomic` with the text it writes today (upgrade's
  `new`, not its UTF-8 bytes), through `from ccp.queue import lib` where the module has no `lib` yet (`forecast` imports
  it inside `cached_fit`, as it imports `ccp.queue` lazily today). `board._atomic` goes, its callers calling
  `lib.write_atomic`. A site that swallows `OSError` today (calibrate, forecast) still does. No other behaviour changes.
- **The package doc.** `scripts/observability/CLAUDE.md`'s first sentence's list gains "the one atomic write
  (`write_atomic`: a unique temporary name beside the file, removed when the write fails)".
- **The tests**, in `tests/test_atomic_write.py` (new), loading `lib` as `ccp.queue` does:
  - `test_two_concurrent_writers_of_one_file_both_succeed`: two threads, at least 300 writes each through `lib.write_json` to one
    path, then two `python3 -B -c` subprocesses doing the same: no write raises, the file holds JSON one of them wrote,
    and the directory holds only that file.
  - `test_a_failed_write_leaves_no_temporary_file`: `write_atomic` to a path that is a non-empty directory raises
    `OSError`, and the parent directory's entries are as before.
  - `test_each_temporary_name_is_its_own_beside_the_file`: with `os.replace` patched to record its source, two
    writes of one path give two different names, each in `path.parent`, starting with `.` and ending `.tmp`.

## Scope

- **In:** `scripts/observability/lib.py` (`write_atomic` added, `write_json`), `scripts/observability/CLAUDE.md`,
  `ccp/board.py` (`_atomic` removed, its callers), `ccp/calibrate.py` (`model`), `ccp/forecast.py` (`cached_fit`),
  `ccp/init.py` (`_record_consent`), `ccp/suite.py` (`take_lane`), `ccp/upgrade.py` (`_record`), `ccp/verify.py`
  (`write_record`, `record_catch_up`), `tests/test_atomic_write.py` (new).
- No SPEC change (measured in Context).
- **Out:** the `mkstemp` writers; appends (`append_jsonl`, the ledger); shell scripts; what each file holds; a sweep of
  the temporary files a killed writer leaves (Context).

## dod_checks

- id: `code-01`
  story: As a runner claiming beside another runner, my auth probe's write of a shared file succeeds while the other writes it too.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat), at its root.
  steps:
    1. Run `python3 -B -c 'import sys,pathlib,tempfile; from concurrent.futures import ThreadPoolExecutor as T; sys.path.insert(0,"scripts/observability"); import lib; p=pathlib.Path(tempfile.mkdtemp())/"status.json"; x=T(2); fs=[x.submit(lib.write_json,p,{"i":i}) for i in range(600)]; x.shutdown(); print(sum(f.exception() is not None for f in fs), sorted(q.name for q in p.parent.iterdir()))'` three times.
  expect: each run prints `0 ['status.json']`.
  dry run (`b09de675`): printed `127 ['status.json']`, `120 ['status.json']`, `137 ['status.json']`.
- id: `code-02`
  story: As an operator, a write that fails leaves no temporary file in the queue or the repo.
  setup: A checkout of the PR head, in your own worktree, at its root.
  steps:
    1. Run `python3 -B -c 'import sys,pathlib,tempfile; from concurrent.futures import ThreadPoolExecutor as T; sys.path.insert(0,"scripts/observability"); import lib; d=pathlib.Path(tempfile.mkdtemp()); (d/"t.json"/"sub").mkdir(parents=True); f=T(1).submit(lib.write_json,d/"t.json",{"a":1}); print(type(f.exception()).__name__, sorted(q.name for q in d.iterdir()))'`.
  expect: prints `IsADirectoryError ['t.json']`.
  dry run (`b09de675`): printed `IsADirectoryError ['t.json', 't.json.tmp']`.
- id: `code-03`
  story: As a plane developer, no writer keeps a temporary name of its own: every atomic write goes through the one helper.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `git grep -nE 'tmp = .*\.tmp' -- ccp scripts bin plugin`.
    2. Run `git grep -lw write_atomic -- ccp 'scripts/*.py'`.
  expect: step 1 prints exactly one line, in `scripts/observability/lib.py`, inside `write_atomic`; step 2 lists `ccp/board.py`, `ccp/calibrate.py`, `ccp/forecast.py`, `ccp/init.py`, `ccp/suite.py`, `ccp/upgrade.py`, `ccp/verify.py` and `scripts/observability/lib.py`, and no other file.
  dry run (`b09de675`): step 1 printed 9 lines (the sites the Context lists); step 2 printed nothing (exit 1).
- id: `test-01`
  story: As a plane developer, the tests hold both concurrent writers succeeding and a failed write cleaning up, and they bite.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat), with your open run.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_atomic_write`.
    2. Run `grep -e both_succeed -e leaves_no_temporary_file -e its_own_beside_the_file -e '^OK' <the log step 1 names>`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_atomic_write --mutant-file <file>`, the file's mutant making `write_atomic`'s temporary name `path.with_name(path.name + ".tmp")`.
    4. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_atomic_write --mutant-file <file>`, the file's mutant deleting the unlink of the temporary file.
  expect: step 1 exits 0; step 2 lists `test_two_concurrent_writers_of_one_file_both_succeed`, `test_a_failed_write_leaves_no_temporary_file` and `test_each_temporary_name_is_its_own_beside_the_file`, each `ok`, then `OK`; steps 3 and 4 each print the mutant `killed`.
  dry run: n/a — the module and `write_atomic` are new.

## Implementation notes

## Verification notes
