# tests — the plane's suite

Run it with `python3 -m unittest discover -s tests -t .`. Afterwards `git branch --list 'state/*'`
must print nothing.

**The suite is fenced** (`__init__.py`): no live queue, no real plane or product repo, no GitHub, no
launchd. Every test builds its product in a temp directory (`helpers.py`'s `Product`), points
`QUEUE_ROOT` at a temp queue, and stubs headless Claude calls. A test never asserts on prose, help
text or prompt wording beyond the token it checks. `test_self_hosting.py` runs the plane's own
checks against this repo, read-only.
