# doclang — language packs for the package-doc checks

`ccp docs check` runs a language-neutral core (`ccp/pkgdocs.py`) plus the pack a product selects with
its top-level `language` (SPEC §8.1, §21.4); `none` turns both off. A pack declares its source suffixes, the directory names it
exempts, and its per-file checks; `__init__.py` holds the registry. `python.py` is the first pack:
module docstrings through `ast`, and, opt-in, no backticked call bullets in a docstring. A new
language is a new module registered in `__init__.py`.

A pack also owns what the plane knows about its language's tests (house rule E18): the line that
carries a test count (`count_re`), the `summary` patterns that read failures, skips and a failing
test's section, the `test_glob` of a test module, the reader `affected` of the modules a change
touches, the counter `suite_size`, the `test_command` that runs named modules or one test, and the
`unbuilt_re` lines that say the code did not build or import; plane.json may override them (`ccp mutate`
runs `mutate.command` and reads `mutate.unbuilt_re` when set). `for_tests(cfg)` is
the one lookup `ccp suite` and `ccp mutate` use; core code stays language-neutral (E18). All of them follow `language`; with none set
(the grace release) they are the Python pack's, as before the key was required.
