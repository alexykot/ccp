# Standing definition of done

Applies to **every** task. Never restate any of this in a task's `dod_checks`: those carry only what
is extra for that task. Items 1–6 are the plane's (plane SPEC §5, §15); the product adds its own
below.

1. **`ccp docs check` is clean**, which includes `ccp tasks check`.
2. **New behaviour is in the SPEC, cited by its rule.** The SPEC text comes from the task (its
   CURRENT → PROPOSED edit) or a recorded ruling; an implementer writes none of its own.
3. **The implementer appends implementation notes to the task file and changes nothing else in it**,
   except a lead ruling or amendment on its claimed task: the runner passes it verbatim in the
   implementer's prompt, and the implementer writes it into the `Context (not checked)` section
   (plane SPEC §10.5). Status and verification notes are written at close, from the verifier's
   record (`ccp tasks close`).
4. **Committed by path and pushed.** Never `git add -A`.
5. **The product's gate is green on the PR head**, run by the verifier and recorded in its verdict
   (plane SPEC §15.3). The gate command is named below.
6. **Nothing that spends allowance or money beyond small development checks runs without the
   operator's word.**

## This product's standing items

<!-- The gate command (item 5), and the product's own items: where a new command is documented,
     storage rules, how agent calls are made, docs the change must keep current. -->

7. …
