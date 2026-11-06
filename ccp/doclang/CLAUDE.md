# doclang — language packs for the package-doc checks

`ccp docs check` runs a language-neutral core (`ccp/pkgdocs.py`) plus the pack a product selects with
`package_docs.language` (SPEC §21.5). A pack declares its source suffixes, the directory names it
exempts, and its per-file checks; `__init__.py` holds the registry. `python.py` is the first pack:
module docstrings through `ast`, and, opt-in, no backticked call bullets in a docstring. A new
language is a new module registered in `__init__.py`.
