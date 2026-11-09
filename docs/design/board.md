# The board: implementation notes

Non-normative notes behind SPEC §10. The rules are in `docs/spec/04-observability.md`.

## Source ages

`work.json` and `runs/*.json` are written only at phase changes, so while a runner runs they are stale past 30 minutes only when no open run shows it is live: an open run's telemetry request (`ccp usage`'s `recent`) or `runs/_suites.jsonl` row (started or ended) within the 30 minutes shows them as `live (telemetry 9s ago, <run>)` instead, and so does a suite of an open run still running (started within 60 minutes, no end yet); past 60 minutes with no end it no longer counts.

## 28.21 Step 3 implementation notes: the board (2026-10-21, non-normative)

- `ccp board build` (`ccp/board.py`) writes `board/board.json`, `board/index.html` and
  `board/history/<date>.json`. `ccp board status` prints the summary and exits 1 on a blocker:
  a task waiting, a gate or question open, a stale source while the runner runs, or the allowance
  at its checkpoint. `ccp board install|uninstall|timer` manage a per-project launchd timer
  (`<prefix>.control-plane.board.<project_id>`, the prefix from `CCP_LAUNCHD_PREFIX`, default `dev.ccp`; every `board.refresh_minutes`) that runs
  `ccp --root <product> board build --quiet` from the run checkout.
- **The model** folds the queue (work.json, open runs, waits, gates, questions, proposals),
  `ccp usage`'s fold (now also tokens per day per seat), `ccp health`'s spans and
  rounds for the last 60 merged tasks, the allowance and its checkpoint, the source ages, the
  queue's script drift and the queue against the task log.
- **The page** (`ccp/board_page.html`) is self-contained: no external scripts or stylesheets. The
  board is embedded, because a page opened from disk cannot fetch the file beside it, and the
  page reloads every minute. It uses the validated categorical palette (five seats in fixed slot
  order, plus a gray for unattributed), in light and dark. The light-mode contrast warning is met
  by a table beside each chart. Every chart has hover tooltips. The wall-time chart caps its
  scale at the 90th percentile (or three times the median) and marks a clipped bar with its value.
  Views: blockers and advice; tiles (allowance against the checkpoint, tokens over 7 days,
  coverage, tasks merged, rounds, tokens per task); Now; tokens by seat; tokens per day by seat;
  wall time per task with the per-task table; runs with usage and their pin check; plane health.
- **Seats** (`ccp/seats.py`). A table in the Now area, and one `seat` line
  each in `ccp board status`, for every live seat: its team, the seat, status and since, the model
  and effort §2 pins, the model and effort observed, a check, and the last activity.
  - **Seats.** The design seat; the runner (the binding's `runner` block); each
    open worker run (pending, running or stopped) with its phase; each architect pass or docs audit
    recorded as `running` (read only: the board never reaps one); and any other telemetry seat with
    requests in the last 30 minutes, shown as not pinned.
  - **Pinned.** A run's record (what `ccp prompt` read from its definition), else the definition in
    effect (`runs.definition`: the product's `.claude/agents` copy while it has one, else the
    plugin's); the runner's agent type's definition; `telemetry.design_seat`, shown as advisory
    (§24); the headless `--model` and `--effort` (`HEADLESS_MODEL`).
  - **Observed.** `ccp usage`'s fold keeps each run's and seat's latest requests (`recent`). Of a
    seat's requests in the 30 minutes up to its latest, the model with the most tokens (so a helper
    call on a small model does not hide the main loop), with the effort of its latest request on
    that model. `ccp usage --json` leaves `recent` out. A headless pass reads the seat its
    `ccp.seat` tag names (`architect-<mode>`, `docs-audit`, §24). Without a request the row says "no telemetry yet". A worker's model must equal its pin; the design seat's is compared with any
    `[...]` suffix (`[1m]`) stripped on both sides.
  - **Headless sessions are not the lead's.** A session the plane launched (its rows tagged with a
    seat, or its id in `headless-usage.jsonl`) is set aside on the design-seat and runner rows,
    whichever bucket a row of it landed in, and the row says how many. Nothing is assumed from
    `query_source` for a placed row.
  - **`headless-untagged`.** A call with no seat tag, no headless session match and no session
    cwd to place it by, made with `query_source: sdk` (a `claude -p` launched before the §24
    tag), is the fold's `headless-untagged` seat, not `design-seat` (`usage._main_seat`; `how`
    counts it as `untagged`). So Tokens by seat, the design-seat advice and this table agree. A call
    with a cwd is still placed by it, whatever its `query_source`. In the table it is no row and no
    running pass adopts it: the design seat's row notes how many were set aside.
  - **Not rows:** `other-sessions`, which aggregates every session outside the seats (§24). A
    tagged seat the plane pins nothing for (a triage or spec-maintainer resume, which keeps its
    session's settings, §2.1) shows "not pinned by the plane", with that note.
  - **Check.** A difference is flagged: `MISMATCH` for a pinned seat, `ADVICE` for the design seat.
    It is a diagnostic, not a blocker, and `ccp board status` keeps its exit code.
  - **Last activity** is the latest attributed request, else the seat's last ledger event (the
    `design-seat` or `task-runner` actor), else the run record's latest time.
  - **Stale.** A row with no activity for 2 hours is flagged `quiet <n> h`. A running pass whose
    lock is gone or stale, past the reaper's grace, is flagged `lock gone`: the same read-only check
    as `architect._reap`, which the board never runs.
  - The Now panel's design-seat line, which only listed models and efforts ever seen, is replaced
    by the table.
- **Rebuilt on each change**, which makes §28.3's
  "each rebuilds after it writes" true. After a state change exits 0, `ccp` asks for a rebuild:
  - tasks claim, phase, wait, resume and close;
  - prompt, report, and verify record;
  - plane propose and triage;
  - allowance continue, and allowance status with `--sample`;
  - architect run and triage, and docs audit run and triage;
  - agent start and stop (the subagent hooks, so the board's open runs keep up);
  - health note and record;
  - tasks next when `--allow-overdue` records its friction note.

  The request marks `board/.build.dirty`. Unless a build holds `board/.build.lock` (a `flock`),
  it then starts a detached `ccp --root <product> board build --quiet --drain`. The drainer runs in
  its own session, imports this plane's `ccp` (as `architect._spawn` does), and writes its stderr
  to `board/.build.log`, which restarts past 64 KB. It builds while the mark is set, so a burst of
  commands during a build costs one more build. A failed build is recorded in `board/.build.failed`,
  which `ccp board status` shows as "last rebuild failed", until a later build writes the board.
  The command never waits for the build, prints nothing about it, and keeps its exit code when the
  spawn fails. The request is skipped without QUEUE_ROOT and when `board/` cannot be made. `CCP_NO_BOARD_REFRESH=1` turns it off (the tests set
  it). The 5-minute timer stays, for changes made outside `ccp`.
- `status.sh` and `rebuild-now.sh` are retired with the snapshot they wrote (§23.4); `ccp board status`
  is the status.
- **The queue follows the log**. The task file
  is the source of truth for status (§4), so the board treats a wait, gate or question whose task
  is `done` or `dropped` in its task file as resolved, never as a blocker. It lists it under plane
  health as queue-vs-log divergence, with the stale queue file. `ccp board build` prints one
  summary warning and at most five examples on stderr (exit unchanged); `ccp board status` lists
  every line. `ccp tasks check` stays queue-free. The board and sync look a queue file up the same
  way (`durable_statuses`: the frontmatter id, else the file name), so a line marked
  `(ccp tasks sync)` is one sync fixes.
  `ccp tasks sync [--dry-run]` repairs the queue: for each queue file whose task is `done` or
  `dropped`, it clears `waiting_on` through `set-waiting-on.sh clear <id> <status>_in_log
  --task-only` (the new flag leaves `work.json` alone unless its `task_id` is that task), clears a
  stale lease (`lease/clear`), sets the queue status to the durable one (`durable/reconcile`, then a
  `phase` transition), moves the `queue/<state>/` marker, takes the task out of `work.json` (the
  next in-flight task becomes current, with its own phase). When it wrote something (not under
  `--dry-run`), `ccp` asks for the background board refresh, as every state change does. It prints what
  it changed, or with `--dry-run` would change, as JSON, and is idempotent. **It never takes a lease
  from a task leased in a mid-flight phase:** that is a `ccp tasks close` between its push and its
  queue update, or a live runner's task the design seat dropped under it. Sync reports it under
  `skipped`, and the board marks it "close or release it"; a dropped one is settled by `ccp tasks drop`. `ccp tasks close` also writes its merge
  record when the queue already says `done`. Open gates and questions of such a task stay on the
  board as divergence until their owner closes them; sync does not decide them.

- **Quality** (step 4, 2026-10-21; §28.3 priority 4). `ccp/quality.py` adds `board.json`'s
  `quality` block, and the page shows it below plane health. It reads only what the plane already
  records and runs no product command:
  - **Architect** (`null` without an `architect` block): each pass in `architect.json`, with its
    mode, status, start, error, finding count by severity (from `reviews/<id>.json`), dispositions
    and rule-change dispositions (from `<id>.triage.json`, in §19's and §19.8's vocabulary: `task`,
    `spec`, `defer`, `needs_operator`, `duplicate`, `reject`; `applied`, `rejected`, `needs_operator`),
    and the tasks its triage created with their state in the task log. Totals count triaged passes
    only. The cadence is `ccp architect due`'s own reasons, computed with `record=False`, which now
    also skips reaping a dead pass, so a board build never writes `architect.json`. It shows tasks,
    notes and days since the last pass against `every_n_tasks`, `notes_due` and `max_days`, the
    wall-time drift against `drift_ratio`, reports awaiting triage, shapes due, and feature tasks
    since the last refactor against `refactor_every`.
  - **House rules** (`null` without the block): the rules doc's lines against `rules_max_lines`,
    its rules by `check:` kind, and its shape errors (`rules.check_doc`). It names the
    `architect.checks` ids but shows no result, because the verifier's `ccp docs check` records
    none. Each `architect.budgets` entry is measured over tracked files (`rules.budget_status`):
    files covered, the largest and its path, and how many are over. The per-task cold suite seconds,
    warm suite seconds and part-lane seconds (§27.2's series, each its own labelled bars) and
    implementer prompt size draw as bars from the task rows, which now carry `prompts` and
    `implement_prompt_chars` *(amended 2026-10-22; the operator: "Yes,
    keep them as a separate trend. Go ahead and implement as you recommended."; this replaces "The
    per-task suite seconds (the `Suite:` line)")*.
  - **Friction:** `health/notes.jsonl`, counted per day (28 days), per ISO week, per seat (`by`),
    per source, and since the last pass, with the five tasks with most notes and the ten latest
    notes (cut to 240 characters). Notes carry no tag, so the board shows no themes.
  - **Trend:** each daily snapshot `history/<date>.json` gains `quality` (friction notes, passes,
    reports awaiting triage, architect tasks open, budgets over, rules-doc lines and errors, and the
    median of the last 5 cold, warm and part-lane suite runs: `suite_cold_s`, `suite_warm_s`,
    `suite_part_s`, added 2026-10-22 under the same approval). The page draws them once two days exist.

  `ccp board status` adds the architect line (last pass, progress to the cadence, due or not), one
  line per report awaiting triage, open architect tasks, budgets over and the friction count. Every
  agent-written string (a note, a task title, a pass's error or due reason) is embedded escaped and
  rendered through the page's `esc()`, as text only.

  Each part builds on its own: one that fails (a malformed `architect.json`, an unreadable notes
  file) is `null` with its error in `quality.errors`, the page and `ccp board status` say that part
  failed, and the day's snapshot keeps that part's earlier counters. A pass record or report file
  that cannot be read is skipped and counted (`architect.unreadable`). The review-point scope is
  `ccp architect due`'s own (`work_scope`: `work.json`'s scope while the runner runs).

- **Per-task drill-down**. `ccp/drill.py` adds `board.json`'s `drill`, keyed by task id:
  one record for each of the last 30 merged tasks and each task in flight. Clicking a bar in "Wall
  time per task", a row of the per-task table, or the Now panel's task opens it in a panel. The
  panel is kept open across the page's reload through `#task=<id>`. `ccp board task <id|NNNN>`
  prints the same breakdown in the terminal. It reads, never writes, and asks for no rebuild.
  - **Per run** (`runs/<task>/<phase>[-n].json`). The window runs from the agent's start
    (`started_at`, else `opened_at`) to the later of its last stop and its report, clipped to the
    task's window. An abandoned run ends at its last stop or report, else at its abandonment, and
    shows its reason (§11.1). A run still open on a merged task
    ends at the merge and is flagged `stale_run`. A live run is measured up to its latest
    evidence: its last request's end, its last suite's end, or now while a suite is still open.
    The stretch from there to now is `live_s`, shown as "live, no telemetry since HH:MM", never as
    idle. The exception is when the receiver is shown to be fresh: a request anywhere at least
    600 s newer than the run's own evidence. Then that stretch is idle. The measured window splits
    four ways, and the parts sum to its length:
    - **model** is the union of the run's request intervals, so overlapping requests count once.
      `ccp usage`'s fold now also returns each run's intervals (`timeline`: the
      `claude_code.llm_request` span's start and end, else the request's `at` less `duration_ms`).
      `ccp usage --json` leaves `timeline` out.
    - **suite** is the union of the run's recorded `ccp suite run` intervals, less the model time:
      the tests ran with no request in flight. A suite that ran while the model worked counts as
      model, and `suite_all_s` keeps the whole union.
    - **other tools** and **idle** are the gaps with neither. The receiver keeps no tool spans
      (it folds `llm_request` spans only, §24), so gaps are told apart by length. A gap under
      `IDLE_GAP_S` (600 s) is other tools: reads, edits, git, a command not run through
      `ccp suite`. A gap of 600 s or more is idle, since no single foreground tool call runs that
      long (Claude Code's Bash timeout is at most 10 minutes).
    - A run with no attributed requests has no model, other or idle time. Its time outside suites
      is **unmeasured**, and the row says whether it predates the telemetry. For a run that started
      before telemetry first reached this queue, the stretch before that point is unmeasured too.

    Each run also lists its suite runs (count, lanes, failed and killed, each with its start,
    tests, seconds and exit), its tokens, cost, observed and pinned model and effort, its pin
    flags, and the review or verify verdict from the ledger.
  - **Per task.** The window is `ccp health`'s wall time: first recorded event to the merge, or
    to now for an open task. The task's split counts each instant once over the union of its
    runs. Where runs overlap, the first of model, suite, other tools, idle, unmeasured and live
    wins, and `overlap_s` gives how long they overlapped. So the split always sums to the wall
    time. Its time outside every run is **runner** time: launching, reading reports, merging.
    The panel also shows:
    - waits (`waiting_on` set to clear in the ledger, by what they waited on, with their detail);
    - the queue wait, from the last dependency's merge to the claim, which falls outside the wall
      time;
    - rounds, tokens, cost, the reports' `Suite:` lines, and the task's latest 20 friction notes,
      cut to 240 characters.
  - **Before run records** (tasks merged before run records existed), the record says
    "no run telemetry (before 2026-10-21)". Its phases come from the prompt-audit stamps and the
    report file times, and are approximate. Each phase shows its report's `Suite:` line, and their
    sum is shown as a lower bound on test time.
  - **The main chart** stacks each bar by the split: model, suite, other tools, idle, runner and
    unmeasured, in fixed slot order. The per-task table gains those columns, so an outlier shows
    without a click.
  - **Size.** Each run's timeline is encoded as one compact string of `<kind><start>+<seconds>`
    tokens. Same-kind neighbours are joined. Past 200 segments the run is cut into 200 equal bins,
    each labelled by the kind that fills most of it, and the run is marked `coarsened`. The totals
    always come from the exact intervals. Each run lists at most 60 suite runs.
  - Every agent-written string (a note, a wait's reason or detail, a verdict) is embedded escaped
    and rendered through `esc()`. The node render test covers the panel for every drill record.
    Each task's record is built on its own. One that fails is `{"task_id", "_error"}`, and the
    panel and `ccp board task` say so. The other tasks' records stand. Suite seconds, token counts
    and costs are read as finite numbers or not at all, and an odd `depends_on` is ignored. If the
    whole block fails, the result is `drill._error` and the page says so. The rest of the board
    still builds.
  - This is the drill-down view that §14.1's per-task suite fields were recorded for.

- **Layout (2026-10-22, non-normative).** The page grew past one scroll, so it is now a fluid,
  full-width dashboard with tabs. `board.json` is unchanged; the page only arranges it.
  - **No fixed width.** The side gutter is 16 px on a phone, 24 px from 900 px and 32 px from
    1400 px. Cards sit in an auto-filling grid with columns of at least 400 px (15vw on a wide
    screen). A 16" laptop (about 1728 CSS px) gets 4 columns, a 21:9 screen (3440 px) 6, a
    phone 1. Wide cards span 2, 3 or 4 columns, but only once that many columns exist, so a phone
    never scrolls sideways. Those spans are minimums: once the tab is laid out, `fillRows()` splits
    a row's spare columns among its own cards in proportion to their spans, so no row ends in empty
    columns. The cards keep their reading order, so the flow is plain `row`, not `dense`. Charts
    are drawn in CSS pixels: `fitCharts()` redraws each one at its container's width after layout
    and whenever that width changes (a resize, a tab switch, the drawer), so axis text stays 11 px
    and the height stays fixed. A long table (ADR register, runs, task
    board, the per-task table, the ready list) scrolls inside its card under a sticky header, so one
    card never sets the height of a whole row.
  - **Header strip, on every tab:** project, plane sha, build age, team, then the blockers. Below
    them come the plane's own blocking items (a stale source, the queue disagreeing with the task
    log, a failed rebuild) and the advice. Then the tiles and a compact **Now**: the runner, the
    current task (it opens the drill-down) with its phase and age, open workers and waits, live
    seats with any model or effort mismatch, the lead's next pick or preference, and held tasks
    when the board carries them.
  - **Tabs** (`#tab=<name>`, keys 1 to 5, the last tab remembered per browser):
    1. **Performance:** seats, tokens by seat (now with cost), tokens per day, wall time per task
       with its table and drill-down, runs with usage, suite and prompt per task, headless runs.
       Cards that later PRs add after the wall-time card land here.
    2. **Quality:** the architect tiles, passes and triage, friction notes, house rules and
       budgets, the quality trend.
    3. **Backlog:** tasks done and ADR tiles, the ADR register, burn-up, the dependency graph.
    4. **Queue:** Now in detail (workers, waits, gates, questions), the ready queue, review points,
       the task board, refactors waiting.
    5. **Plane health:** sources, attribution, script drift, open proposals, queue against the task
       log, the last rebuild failure, and the allowance with this week's checkpoint decisions.
    A tab label carries a count where it helps: seats off their pin (Performance), reports
    awaiting triage (Quality), ready tasks (Queue), plane warnings (Plane health).
  - **Drill-down:** `#tab=<name>&task=<id>`. On a screen 1600 px or wider it opens as a drawer
    over the right 40%, and the tab's cards reflow into the rest. Narrower, it is the full sheet as
    before. The 60 s reload keeps the tab, each tab's scroll position, the drill-down and its
    scroll. All five tabs are rendered into the page and hidden, not built on demand, so the node
    render tests see every section, and `safe()` still isolates each one. A plan failure shows its
    banner on both Queue and Backlog. `tests/test_board_layout.py` checks that each section sits
    in its tab, that the strip sits above the tabs, and that the hash picks the tab (a bad value
    falls back to Performance).
