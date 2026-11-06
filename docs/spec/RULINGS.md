# Rulings

Rules found obsolete or contradictory during the SPEC restructure (ADR-0033 D4). The operator ruled
on every row on 2026-11-06 ("I approve all as recommended"). The parts apply the rulings, ADR-0034
records them, and a ruling that needs code names its plane task.

| Old § | The rule as it reads | Why it looks obsolete or contradictory | Proposed | Operator ruling |
|---|---|---|---|---|
| §20.1.5 | Remote blindness: a down mesh network must not mean "no status"; seats email a one-screen digest on a blocker or on request, with an optional copy to a personal path | The mesh network and the email path went with the old hosting; the board and the operator's own session are how status is read now | retire | retire — operator, 2026-11-06 |
| §22.5 | The spec-maintainer protocol doc is the product's copy, and the ask script fails closed when it is missing | The headless maintainer was deleted; the lead reads the plugin skill or the product's copy | retire | retire — operator, 2026-11-06 |
| §26.13 | The old architecture-review and docs-audit commands stay as aliases until every bound project has moved | Every bound project has moved to the architect seat | retire the aliases (code task) | retire the aliases; code: task 0010 — operator, 2026-11-06 |
| §29.6 | A product that still has a `delivery-state` branch retires it by hand; `cpl` never reads or deletes it | No product has that branch any more; the rule only describes a removed mechanism | retire (keep "the queue is the only runtime state" as a rule) | retire; keep "the queue is the only runtime state" — operator, 2026-11-06 |

## From Part III

| Old § | The rule as it reads | Why it looks obsolete or contradictory | Proposed | Operator ruling |
|---|---|---|---|---|
| §26.5 vs §26.16 | §26.5: `next` blocks when a report has waited for triage "for more than `triage_grace_tasks` merges"; §26.16 (the implementation): it blocks once that many merges "have followed the report", i.e. at least | The two texts disagree by one merge; the code does "at least", and §19.6 states "at least" | keep "at least" (as built) | keep "at least", as built — operator, 2026-11-06 |
| §23.6, §24.6 | The Watchdog shows the last review's status and lists a review stuck in triage for more than 24h as a line in its digest | The Watchdog seat was removed with the old hosting; a stuck triage now blocks `cpl tasks next` (§19.6) and shows on the board | retire (left out of §19.9 and §21.8) | retire — operator, 2026-11-06 |
| §23.5 vs §26.7 | §23.5: triage may add known-intentional notes to the product's `LOCAL.md`; §26.7: the house rules' *Known intentional* section replaces that section | The later rule supersedes the earlier; §19.8 states the later one | keep §26.7's rule | keep §26.7's rule — operator, 2026-11-06 |
| §26.15 | Open knob: whether `shape` runs automatically when an ADR is accepted, rather than through the owner's `cpl tasks check` failure | An undecided design question, not a product setting; nothing implements the automatic run | decide, or drop the question (today: the owner starts it) | drop the question: the owner starts `shape` — operator, 2026-11-06 |

## From Part II

| Old § | The rule as it reads | Why it looks obsolete or contradictory | Proposed | Operator ruling |
|---|---|---|---|---|
| §20.1.4 | Scheduled seats write a heartbeat on every wake and are stale past max(25 min, 2.5 × their cron interval), raising the `stale_seat` blocker and an escalation | No seat is scheduled under the agent team: every seat is event-only (§25.8), so the rule never fires; kept in §18.3 as reading "applies to no seat" | retire the stale rule and the `stale_seat` blocker (code task); keep heartbeats | retire the stale rule and `stale_seat`; keep heartbeats; code: task 0011 — operator, 2026-11-06 |
| §12.1 | `verify_stale` is a snapshot blocker when a submitted or verifying task has no verdict and no verifier progress for 30 minutes | §25.8 says `verify_stale` is gone (the verifier is the runner's subagent and reports by message and file), yet the snapshot still computes it; kept in §18.3 | retire `verify_stale` and `cadence.verify_stale_minutes` (code task), or keep it as a board diagnostic only | retire `verify_stale` and `cadence.verify_stale_minutes`; code: task 0011 — operator, 2026-11-06 |
| §28.26 | The self-check lists and exploration hygiene were introduced as trials, each to be judged over a product's next ten tasks and reverted if fix rounds or MINOR counts rise | The judging windows ran on a product's tasks, outside the plane; the SPEC still frames them as trials; kept in §13.5 as standing rules | keep both as standing rules and drop the trial framing | keep both as standing rules, no trial framing — operator, 2026-11-06 |
| §27.1 | The CI template's database service is `pgvector/pgvector:pg16` and `STORE_TEST_PATTERN` defaults to `store\|pgvector`, with `EXPECT_STORE_TESTS=1` | Product-shaped defaults in a generic template (ADR-0001: neutral defaults); kept in §15.7 | template ships no database service and an empty pattern, `EXPECT_STORE_TESTS=0` by default (template change) | neutral template defaults; code: task 0014 — operator, 2026-11-06 |
| §25.3.1 | (earlier wording, no longer in the SPEC) A minor finding that could cost a later cycle is fixed before the merge | Today's SPEC only records unfixed minors in the verifier's record; the rule appears only in an earlier draft and the roadmap | restore: a minor that could cost a later cycle is fixed before merge? | restore: a minor that could cost a later cycle is fixed before merge — operator, 2026-11-06 |
| §28.2 | Run binding takes the oldest pending run of that agent type "in that session" | The code (and the §28.17 note) binds the oldest pending run of the type whatever the session; §11.1 follows the code | confirm "whatever the session" | confirm "whatever the session" — operator, 2026-11-06 |
| §21.3.2 | Run before an answer exists, `process` "reprints the lead message once and then says to skip ahead" | The code sends the lead message once only to a question without `lead_messaged_at` (raised before that field, or by the removed routes) and otherwise says to skip ahead; §17.3 follows the code | confirm the code's rule | confirm the code's rule — operator, 2026-11-06 |

## From Part I

| Old § | The rule as it reads | Why it looks obsolete or contradictory | Proposed | Operator ruling |
|---|---|---|---|---|
| §14 item 9 | Tailscale / mesh policy for a machine joining the tailnet is an operator gate | The mesh network served the removed external-bot hosting; no seat joins a tailnet now | retire the gate | retire the gate — operator, 2026-11-06 |
| §3 non-goals | "Tailscale install (documented; do later)" and "Builder bot operating slices" are listed as non-goals | Both name things that no longer exist (the mesh network, the builder bot); as non-goals they say nothing | drop both | drop both — operator, 2026-11-06 |
| §28.11.1 vs §24.4 | §28.11.1: `ids.spec.prefix` is reserved and no check reads SPEC refs yet; §24.4: the opt-in citation rule reads SPEC refs with that prefix | The two old sections contradict each other; the code follows §24.4, and new §7.2 states it that way | confirm §7.2 (the citation rule reads `ids.spec.prefix`) | confirm §7.2 — operator, 2026-11-06 |

## From Part V

Kept in `docs/spec/05-operations.md` as they read; listed here for a ruling.

| Old § | The rule as it reads | Why it looks obsolete or contradictory | Proposed | Operator ruling |
|---|---|---|---|---|
| §29.4 (→ §29.2) | `cpl` is installed from the run checkout with `pipx install -e` | `scripts/run-checkout.sh install` links `cpl` on PATH to the run checkout's `bin/cpl`; nothing uses pipx | state the link instead | state the link — operator, 2026-11-06 |
| §29.4 (→ §29.1) | A product may pin a plane commit with `plane.json` `plane.pin`, and `cpl` warns while a pin is in force | No code reads `plane.pin` or warns about a pin | retire, or build it (a task) | retire `plane.pin`: products run `main` — operator, 2026-11-06 |
| §28.10 (→ §31.4) | A proposal untriaged for 7 days is flagged | Not built (ADR-0018 D8 is `not_built`) | keep as a not-built rule, or retire | keep as a not-built rule; code: task 0015 — operator, 2026-11-06 |
| §11 (→ §30.3) | On misuse or low API credit during CLI work, email the operator without secrets | The email path went with the old hosting; operator contact now goes through the lead | replace "email" with a gate to the lead | a gate to the lead, without secrets — operator, 2026-11-06 |
| §11 (→ §30.1) | The auth checks report whether the Claude login is valid and whether ambient API keys are present | The plane runs only the probes a product declares; it checks neither itself (ADR-0026 D4) | say a product's probes should cover both | a product's probes cover both — operator, 2026-11-06 |

## From Part IV

| Old § | The rule as it reads | Why it looks obsolete or contradictory | Proposed | Operator ruling |
|---|---|---|---|---|
| §20 | Quota wake-after-reset: the watchdog wakes the runner once `planned_resume_at` / `resets_at` is past, or after 2 hours with no timestamp | The watchdog seat is gone; the session wake (now §25.4) resumes parked tasks, and a credit-quota park has no other owner | retire the watchdog clause; decide whether a non-session quota park needs an owner | retire the watchdog clause; a credit quota park is re-checked by the lead at its next session (§18.4) — operator, 2026-11-06 |
| §20.1.3 | `now.json` and `STATUS.md` are replaced by the board and "no longer written" (§28.14) | `scripts/observability/rebuild-now.sh` still writes `now.json` (and `STATUS.md`), and the status scripts read it | retire `now.json`/`STATUS.md` and their scripts, or keep them as the board's machine-free fallback and say so | retire `now.json`/`STATUS.md` and their scripts; the board is the status; code: task 0012 — operator, 2026-11-06 |
| §20.1.8 | The watchdog writes seat heartbeats, auth events and the snapshot, escalates from blockers and wakes the verifier on `verify_stale` | The watchdog seat is gone. Heartbeats do have owners (`cpl tasks claim` and `close` write them) and auth events come from the claim's probes; the snapshot rebuild and the `verify_stale` wake have none, and old §25.8 says `verify_stale` is gone under the team | retire the watchdog row; retire `verify_stale` (or name an owner) | retire the watchdog row; retire `verify_stale` (task 0011) — operator, 2026-11-06 |
| §20.2 | The prompt audit keeps the full prompt text (`prompt_body`), "required for alpha", all retained until the operator says prune | The alpha framing has no end date; full prompt bodies in the queue sit oddly with "numbers and ids only" elsewhere | keep as is, or make full bodies opt-in (default off) with retention by age | full prompt bodies opt-in, off by default, retention by age; code: task 0013 — operator, 2026-11-06 |
| §20.6 | Knobs: watchdog tick `*/30` around the clock, verifier has no schedule, runner idle wake 30 minutes, a second watchdog only if the first is stale, STATUS.md generated beside `now.json` | All describe the removed bot seats or the replaced snapshot | retire them (Part IV keeps seat staleness, verify stale and prompt retention) | retire — operator, 2026-11-06 |
| §20.6, §25.8 | Knob "verify stale 30 minutes (`cadence.verify_stale_minutes`)"; snapshot blocker `verify_stale` | Old §25.8 says `verify_stale` is gone under the team, yet the knob and the blocker kind remain in the snapshot code | retire the knob and the blocker (left out of Part IV's knobs) | retire the knob and the blocker; code: task 0011 — operator, 2026-11-06 |
| §20.1.5 | `status` exits non-zero "if any open blocker or stale seat" | The board's status (old §28.21) exits non-zero on a task waiting, a gate or question open, a stale source while a runner runs, or the allowance at its checkpoint; stale seats no longer count | keep the board's list (Part IV states it, matching the code) | keep the board's list — operator, 2026-11-06 |
| §28.7, §28.19 | Clarifications promoted from implementation notes to rules: the checkpoint command's refusals (no reason, a `--to` that does not raise, no sample with a reset), an unknown reading is a `warning:` that gates nothing | Stated in non-normative notes and the code, not in the old rule text | promote to rule? (Part IV states them as the code does) | promote to rule — operator, 2026-11-06 |
| §28.22 | "The deepest root wins" when several bindings hold a session's cwd | Stated only in non-normative notes and the code | promote to rule? (Part IV states it as the code does) | promote to rule — operator, 2026-11-06 |

<!-- spec-refs: historical -->
