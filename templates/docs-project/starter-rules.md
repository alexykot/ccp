<!--
  Control-plane starter house rules (plane SPEC §20.5): generic rules about how agent-maintained
  code and docs stay correct, each with its purpose and its check. Optional: a product adopts,
  declines or overrides each one.

  - Adopt: `ccp init --starter-rules` writes this file to docs/ENGINEERING.md and, in the plane.json
    it writes, `docs.starter_rules` and the `package_docs` settings the `docs` checks need. By hand:
    copy the rules you keep and set `docs.starter_rules` to {} in plane.json.
  - Decline: delete the rule here and name it, with the reason, in plane.json
    `docs.starter_rules.declined` ({"<starter name>": "<reason>"}); `ccp docs check` then does not
    run its check.
  - Override: tune its check's settings in plane.json (globs, targets, patterns) or reword it here;
    to replace its check, decline it and write your own rule in its place.

  Keep each rule's `starter:` line: it names the rule in the starter set. Number your own rules after
  these, in the format of the house-rules template (ENGINEERING.md): `check: pass` (the architect
  judges it), `docs` (a rule `ccp docs check` runs, named by its plane.json key), `budget` or
  `command`. Delete this comment once the file is yours.
-->
# Engineering rules

The house rules of this product. Every implementer reads them before starting a task; every rule
says why it exists and how it is checked.

## Single sources

- **E1** One owner for every count or list. A count, a registry or an enumeration lives in one
  place; every doc that mentions it names that owner instead of restating the number or the members.
  Purpose: a copied count goes stale silently the first time the list changes.
  starter: one-owner
  check: pass — the architect's structure (duplication) and docs lenses
- **E2** One home per fact. A default, a path, a format or a rule is stated in one document or
  module; everything else links to it or derives from it.
  Purpose: two homes disagree after the first edit, and a reader cannot tell which one is current.
  starter: one-home
  check: pass — the architect's structure lens (duplication)

## Tests

- **E3** Tests check behaviour, never quoted text: no assertion on prose, help text, prompt text or
  messages beyond the token the behaviour depends on.
  Purpose: a test that pins wording fails on every rewrite and proves nothing about the code.
  starter: behaviour-tests
  check: pass — the architect's tests lens
- **E4** Tests are deterministic: a test fixes the clock, the git HEAD and the repository it reads,
  and never depends on machine load (no sleeps racing real time, no timing thresholds).
  Purpose: a flaky test teaches every seat to rerun a failure instead of reading it.
  starter: deterministic-tests
  check: pass — the architect's tests lens

## Docs

- **E5** Docs are current-only: a current doc states what is true now, with no history, no dates and
  no delivery ids. History lives in Git and in files carrying the git attribute named by
  `package_docs.rules.history_attr` (set in `.gitattributes`); the absence checks skip them, and
  `ccp docs history-paths` lists them for the product's own absence checks.
  Purpose: a doc that mixes past and present makes every reader work out which parts still hold.
  starter: current-docs
  check: docs — package_docs.rules.no_ids, package_docs.rules.history_attr
- **E6** Package docs are maps: each source directory's doc says what exists there and where to
  look, never what a task did; modules carry their docstrings.
  Purpose: a session finds its way by the map; a log of past changes only adds reading.
  starter: package-maps
  check: docs — package_docs
- **E7** Every reference resolves: a SPEC ref names a heading the SPEC has, a link to a doc heading
  names one that exists, and a path a package doc names exists.
  Purpose: a dangling reference sends the reader nowhere and hides that the target moved.
  starter: refs-resolve
  check: docs — package_docs.rules.citations

## Known intentional

Deliberate oddities, so that passes don't raise them again. No ids: these are not rules.
