# doclang — language packs for the package-doc checks

`ccp docs check` runs a language-neutral core (`ccp/pkgdocs.py`) plus the pack a product selects with
`package_docs.language` (SPEC §21.5). A pack declares its source suffixes, the directory names it
exempts, and its per-file checks; `__init__.py` holds the registry. `python.py` is the first pack:
module docstrings through `ast`, and, opt-in, no backticked call bullets in a docstring. A new
language is a new module registered in `__init__.py`.

A pack also owns what the plane knows about its language's tests (house rule E18): the line that
carries a test count (`count_re`), the `summary` patterns that read failures, skips and a failing
test's section, the `test_glob` of a test module, the reader `affected` of the modules a change
touches, the counter `suite_size` and the `test_command` that runs named modules. `for_tests(cfg)` is
the one lookup `ccp suite` and `ccp mutate` use; core code names no language and no test runner, and
`language-pack` in plane.json's `docs.checks` keeps it so. Today the reader, counter and command follow
`package_docs.language` and the output patterns are the Python pack's for every product.
