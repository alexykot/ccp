"""ccp — the control plane's product tool (SPEC §8, §19).

Runs in a product checkout and enforces what the plane asks of every product: the durable task
log (`ccp tasks`), package-doc coverage and house rules (`ccp docs check`), the architect seat
(`ccp architect`, with `ccp docs audit` as its alias) and delivery measurements (`ccp health`).
Stdlib only, like the rest of the plane. Per-product settings come from the product-owned
`docs/delivery/plane.json` (`config.py`).
"""
