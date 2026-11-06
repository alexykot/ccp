# How to write a task: this repo's rules

The plane's canonical task format and its generic writing rules are the control-plane plugin's
`writing-tasks` skill (plane SPEC §5.1). Read it first; this file only adds what is specific to
this product. Where a rule here is stricter, it wins.

## This repo's rules

- **Name no managed product.** A task, its checks and its notes are written generically: no product
  names, ids, paths, figures or rulings. The repo is published; the leak check (E3) enforces it.
- **A check runs in the fenced suite.** A `dod_checks` command uses temp products and temp queues
  (`tests/helpers.py`), never a live queue, a product repo, GitHub or launchd.
- **A SPEC change cites its rule and the operator's approval** (SPEC §31). The task carries the
  CURRENT → PROPOSED text.

