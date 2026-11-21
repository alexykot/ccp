---
task_id: 0206-package-doc-is-not-its-own-source
title: A package doc listed in claude_md_dirs does not count its own lines as source
status: done
kind: feature
depends_on: []
spec_refs: ["S21"]
review_point: R14
paths: ["ccp/pkgdocs.py", "docs/delivery/plane.json", "tests/test_pkgdocs_config.py"]
adopt: "none"
created: 2026-11-20
updated: 2026-11-21
---

# Task: 0206-package-doc-is-not-its-own-source

## Intent

§21.3 says a package doc is no longer than half its directory's source lines. For a directory listed
in `package_docs.claude_md_dirs`, the doc is `CLAUDE.md`, and the check counts that file's own lines
as source. Listing a small directory then fails the size check against itself, and every larger
listed directory's check is looser than the rule says. After this task, a directory's own package
doc never counts as its source, whatever its name. The plane's own `scripts/git-hooks/CLAUDE.md`,
which stopped being judged when the plane took the `.claude.md` constant, is listed and judged
again.

## Context (not checked)

Measured at `58cf1d0`.

- `ccp/pkgdocs.py` `source_dirs` has `def source(f)`, which excludes only `pd["doc_name"]`, and
  `_source_lines` does the same (`git grep -n 'f.name != pd\["doc_name"\]' ccp/pkgdocs.py` at
  `58cf1d0`: two lines). A listed directory's doc is `CLAUDE.md` (`doc_for`), a `.md` source file by
  default, so it counts toward its own directory's source.
- Found in task 0190's review, a MINOR finding recorded in its notes. Dropping `package_docs.doc_name`
  stopped `scripts/git-hooks/CLAUDE.md` being judged, because `.claude.md` applies and the directory
  is not listed. Listing it fails the size check: the directory's only source-suffixed file is that
  `CLAUDE.md` (8 lines, `wc -l scripts/git-hooks/CLAUDE.md` at `58cf1d0`), since `pre-commit` and
  `pre-commit.template` carry no source suffix.
- The directories already listed (`claude_md_dirs` in `docs/delivery/plane.json`) stay within
  the rule once their own doc is left out. Probe at `58cf1d0`: each doc is far under half of the
  directory's other `.py`, `.json`, `.md` and `.sql` lines (`git ls-files` per directory, summed
  with `wc -l`: the smallest is `ccp/doclang`, a 15-line doc against 265 lines of source).
- §21.3's rule text already says "half its directory's source lines" and does not count the doc, so
  the SPEC needs no change (`grep -n 'half its directory' docs/spec/03-quality.md` at `58cf1d0`:
  one line).
- `tests/test_pkgdocs_config.py` holds the `claude_md_dirs` tests.
- A managed product that lists `claude_md_dirs` may find its integration branch stale after the
  release, since a directory's doc no longer counts as its source: `scripts/release.sh` prints
  what went stale (§29.3), and the lead is told.

## Scope

- **In:** `ccp/pkgdocs.py`, `docs/delivery/plane.json`, `tests/test_pkgdocs_config.py`.
- **`ccp/pkgdocs.py`:** `source(f)` and `_source_lines` leave out the directory's own package doc,
  the file `doc_for(cfg, f.parent)` names (`CLAUDE.md` for a listed directory, else `doc_name`).
  A `CLAUDE.md` in a directory that is not listed is still a `.md` source file, as today.
  - A listed directory whose only tracked file is its `CLAUDE.md` is still judged: it is found
    through the `elif f.name in (pd["doc_name"], "CLAUDE.md")` branch, and `judged` keeps it because
    it is listed.
  - With no source lines left, the size check is skipped, as it is today for `src == 0`. The title,
    plan-heading, dead-path and delivery-id rules still apply.
- **`docs/delivery/plane.json`:** `package_docs.claude_md_dirs` gains `"scripts/git-hooks"`, in
  sorted place.
- **Tests** in `tests/test_pkgdocs_config.py`:
  - a listed directory holding a 10-line `CLAUDE.md` and a 10-line `.py` file fails the size check
    ("10 lines against 10 of source"), where today it counts 20 and passes;
  - a listed directory holding only a `CLAUDE.md` with a dead backticked path fails on that path
    and not on size;
  - an unlisted directory with only a `CLAUDE.md` is still not judged.
- **Out:** the size ratio, the other rules, and `.claude.md` directories, which already leave out
  their own doc.

## dod_checks

- id: `pd-01`
  story: As the plane, its git-hooks package doc is judged again and passes.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -n 'scripts/git-hooks' docs/delivery/plane.json`.
    2. Run `ccp --root . docs check; echo rc=$?`.
  expect: step 1 shows the entry in `claude_md_dirs`; step 2 prints `docs: clean` and `rc=0`.
  dry run (`58cf1d0`): step 1 prints nothing; step 2 prints `docs: clean`.

- id: `pd-02`
  story: As a product, a listed directory's doc is measured against its other files.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_pkgdocs_config 2>&1 | tail -20`.
  expect: exit 0, with the three Scope tests listed `ok`.
  dry run (`58cf1d0`): 11 tests, OK; the new tests do not exist yet.

- id: `pd-03`
  story: As a plane developer, the size test bites.
  setup: a copy of the PR head (`git worktree add --detach <tmp> HEAD`) in which `_source_lines`
    excludes only `doc_name` again.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_pkgdocs_config`.
  expect: at least one failure, naming the 10-against-10 test.
  dry run: n/a — the test is new.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

- `ccp/pkgdocs.py`: one helper, `_is_doc(cfg, f)`, true for the product's `doc_name` or the name `doc_for`
  gives the file's directory (`CLAUDE.md` in a listed one). `source_dirs`' `source(f)` and `_source_lines`
  both use it. `doc_name` stays excluded everywhere, as before (a `.claude.md` in a listed directory is
  not counted either); an unlisted directory's `CLAUDE.md` is still a `.md` source file.
- `docs/delivery/plane.json`: `scripts/git-hooks` added to `claude_md_dirs`, in sorted place.
- Premises re-run at `aaa81b2`: two `f.name != pd["doc_name"]` sites, the 8-line doc, one
  `half its directory` line in the SPEC: as the task states.
- `ccp` on PATH runs the run checkout, so before release `ccp --root . docs check` shows the old
  failure (`8 lines against 8 of source`); `bin/ccp` of the worktree prints `docs: clean`.
- Fix round 1 (review MINOR): the one test holding all three Scope cases is now three, so `unittest -v`
  lists each. A small `check_listed` helper in the test module builds the product, once from files and once
  from a checkout, and yields the errors. No code change.

## Verification notes
- 2026-11-21 — verifier, PR #244 head `f303fb7` (squash `942df9f`): APPROVE. Passed: pd-01, pd-02, pd-03, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp wt exec ver-0206 -- --root . docs check` exit 0. Record: verification/0206-package-doc-is-not-its-own-source.json.

