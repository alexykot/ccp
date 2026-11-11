# git-hooks — hooks for clones of the plane

`pre-commit` refuses a commit on `main`: main moves only by merged pull requests. Installed per
clone by `scripts/install-git-hooks.sh` (`core.hooksPath`). It then runs `pre-commit.template`.

`pre-commit.template` is the plane's commit hook template for any product checkout (SPEC §10.5):
with `QUEUE_ROOT` set and `ccp` on PATH, it refuses a commit on the integration branch that changes a
leased task's file (`ccp tasks check --lease --staged`). A product copies it into its hooks.
