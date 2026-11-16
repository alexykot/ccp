---
task_id: 0102-init-and-docs-check-fixes
title: init's deny rules, --adopt on nested rules, origin parsing, and the package-doc check are fixed
status: pending
kind: fix
depends_on: []
spec_refs: ["S4", "S12"]
review_point: R6
paths: ["ccp/init.py", "ccp/rules.py", "ccp/pkgdocs.py", "ccp/docrules.py", "ccp/wt.py", "tests/test_init*.py", "tests/test_rules.py", "tests/test_starter_rules.py", "tests/test_pkgdocs_config.py", "tests/test_doc_rules.py", "tests/test_wt.py"]
created: 2026-11-16
updated: 2026-11-16
---

# Task: 0102-init-and-docs-check-fixes

## Intent

Adopting a product and checking its docs do what they say:
- The permission template denies a forced push wherever its flag is placed.
- `ccp init --adopt` converges on a rule that is nested under another rule.
- A malformed origin URL is reported, not a traceback.
- A package doc that exists is always checked.

## Context (not checked)

- Four accepted plane proposals (operator, 2026-11-16: all approved).
- The deny rules (`ccp/init.py`, `DENY`) are prefix matches, so `git push origin main --force` is not
  denied.
- When `--adopt` meets a rule written as a sub-bullet of another rule, it reports the parent adopted
  but leaves it unchecked. Reruns never converge. The check line can also land inside a fenced block,
  and `--adopt` rewrites CRLF line endings to LF.
- `origin_host` raises `ValueError` on a malformed bracketed URL such as `https://[::1`.
- Since document-only directories are exempt by default, a package doc that already exists in an
  unlisted document-only directory is no longer checked.
- The `_same_head` hint (`ccp/wt.py`) suggests `--name`, which `--baseline` refuses.

## Scope

- **In:**
  - `DENY` gains the forced-push forms with the flag after the remote and after the branch
    (`git push * --force`, `git push * --force-with-lease`, `git push * -f`), in whatever pattern
    form Claude Code's permission rules accept. A test pins that each spelling is denied.
  - `--adopt`: an item ends at the next line that matches the rule pattern, at any indent. The file is
    re-parsed before writing, so a rerun changes nothing. A check line never lands inside a fenced
    block. CRLF line endings are kept.
  - `origin_host` returns `None` (no host) on a URL it cannot parse, and init warns, naming the URL.
  - Package docs: a package doc that exists is checked wherever it is. Only the requirement to have
    one is exempt in document-only directories.
  - The `_same_head` hint suggests what `--baseline` accepts.
- **Out:**
  - Any change to which commands the template allows.

## dod_checks

- id: `check-01`
  story: As a product owner, a forced push is denied however it is spelt.
  setup: a throwaway product after `ccp init`.
  steps:
    1. Read the written deny list, and match `git push origin main --force`, `git push --force origin
       main`, `git push origin -f main` and `git push origin main --force-with-lease` against it with
       Claude Code's prefix-and-wildcard rule.
  expect: each one matches a deny rule.
  dry run: n/a.
- id: `check-02`
  story: As an adopter, `--adopt` converges.
  setup: a rules doc with a rule nested as a sub-bullet of another rule, a fenced block right after a
    rule, and CRLF line endings.
  steps:
    1. Run `ccp init --adopt` twice.
  expect: the first run marks each adopted rule's own item. The second run changes nothing (the file
    is byte-identical). No check line is inside the fence, and the line endings are still CRLF.
  dry run: n/a.
- id: `check-03`
  story: As an adopter, a malformed origin URL is no traceback.
  setup: a throwaway product whose origin is `https://[::1`.
  steps:
    1. Run `ccp init`.
  expect: no traceback. It warns about the origin and carries on as for a product with no GitHub
    origin.
  dry run: n/a.
- id: `check-04`
  story: As a product owner, an existing package doc is checked.
  setup: a product with an unlisted document-only directory holding a package doc that breaks a doc
    rule, and another such directory with no package doc.
  steps:
    1. Run `ccp docs check`.
  expect: the broken doc is reported. The directory without a doc is not.
  dry run: n/a.
- id: `check-05`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
