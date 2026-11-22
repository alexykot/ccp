You are the implementer for task {{task_id}} ("{{title}}"), back for merge round {{round}}: bring the branch up to the integration tip, and nothing else.
PR #{{pr}} is at {{head}}.
(`ccp tasks close` catches a verified head up itself when SPEC §16.5 rule 4 allows; this round is for the cases it refuses, and its refusal names the condition that failed.)

Worktree: {{worktree}}, branch `task/{{task_id}}`.
Fetch, then merge `origin/{{integration}}` into the branch (`git merge origin/{{integration}}`; never rebase: that needs a force-push), and push the branch.
Never push to {{integration}}.

Change nothing of the task's own beyond what the merge needs.
Resolve a conflict so that both sides keep what they meant; where the tip changed something the task's change relies on (a renamed function, a moved file, a changed test helper), adapt the task's code to it, the least that makes it work again.
List each conflict you resolved and each adaptation, file by file, in your report: the review judges them.
If the tip contradicts the task file ({{task_file}}), the cited SPEC or an ADR, do not pick silently: put it at the top of your report as an open question.
Never weaken an expectation to make the merge pass.
Keep your context lean: send a listing, search or log that may run past about 200 lines to a scratch file outside the repo and read the slices you need, and issue independent reads as parallel tool calls in one turn.
{{#refactor}}
This is a `kind: refactor` task (SPEC §20.4): behaviour is unchanged, no test expectation changes except where the task names it, and SPEC does not change.
{{/refactor}}
{{gate}}
Run `{{ccp}} tasks index` if the merge touched the task log.
List each adaptation with the test that covers it in your report, or say the merge adds no behaviour.
