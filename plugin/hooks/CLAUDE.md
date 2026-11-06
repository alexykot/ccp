# hooks — the plugin's Claude Code hooks (SPEC §9.1)

`hooks.json` wires them. Each stays fast and always exits 0 unless it means to keep a teammate working.

- `orientation.sh` (SessionStart): in a project with a `docs/delivery/plane.json`, hands the session the
  role-neutral orientation; in the plane's own repo, one line pointing at CLAUDE.md instead; anywhere
  else, nothing.
- `run-binding.sh` (SubagentStart/Stop): binds a worker's run through `ccp agent`; it does nothing when
  no binding maps the session to a product, and writes its errors to the queue's unbound log.
- `runner-idle.sh` (TeammateIdle): keeps the runner teammate working while its scope has ready tasks
  (§18.2); it does nothing when there is no queue or no runner has run there (no work.json).
