#!/usr/bin/env bash
# run-checkout.sh — SPEC §29.2: the clean checkout of `main` that products and the Mac's seats run.
#
#   run-checkout.sh install   clone this repo's origin there (if missing) and point `ccp` on PATH at it
#   run-checkout.sh update    fetch, then fast-forward to origin/main; refuses when it is dirty or off main.
#                             Then checks each bound product's integration branch against the new rules
#                             (SPEC §29.3) and prints what went stale; it writes nothing to a product.
#   run-checkout.sh status    branch, local changes, commits behind origin/main, where `ccp` points
#   run-checkout.sh label     the telemetry receiver's launchd label
#
# Env: CCP_RUN_CHECKOUT (default: control-plane-run beside this repo),
#      CCP_BIN_LINK (default ~/.local/bin/ccp: the symlink on PATH that `install` points at the checkout),
#      CCP_BINDINGS_DIR (default: the run checkout's projects/: the bindings `update` checks).
# Nobody develops in the run checkout: only `update` moves it, after a merge to main.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
MAIN="$(git -C "$HERE" worktree list --porcelain 2>/dev/null | awk 'NR==1 {print $2}')"   # the clone's main worktree
RUN="${CCP_RUN_CHECKOUT:-$(dirname "${MAIN:-$HERE}")/control-plane-run}"
# Local, unversioned data the run checkout keeps (gitignored): bindings until the backend holds them.
# An update must never lose them.
LOCAL_DIRS=(projects)
# The telemetry receiver's launchd label: <prefix>.control-plane.otel, the prefix normalised exactly as
# ccp's launchd_prefix() (ccp/queue.py): CCP_LAUNCHD_PREFIX trimmed of spaces, then of leading and
# trailing dots, and dev.ccp unless it is dotted letters, digits and dashes. CCP_OTEL_LABEL overrides
# the label whole (the test suite points it nowhere).
launchd_prefix() {
  local p="${CCP_LAUNCHD_PREFIX:-}"
  [ -n "$p" ] || p=dev.ccp
  p="$(printf '%s' "$p" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//; s/^\.+//; s/\.+$//')"
  [[ "$p" =~ ^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*$ ]] || p=dev.ccp
  printf '%s' "$p"
}
OTEL_LABEL="${CCP_OTEL_LABEL:-$(launchd_prefix).control-plane.otel}"
LINK="${CCP_BIN_LINK:-$HOME/.local/bin/ccp}"
die() { echo "run-checkout: $*" >&2; exit "${2:-1}"; }
g() { git -C "$RUN" "$@"; }

clean_on_main() {
  [ -d "$RUN/.git" ] || die "no run checkout at $RUN: run-checkout.sh install" 2
  [ "$(g rev-parse --abbrev-ref HEAD)" = main ] || die "$RUN is on $(g rev-parse --abbrev-ref HEAD), not main: it only ever tracks main"
  [ -z "$(g status --porcelain --untracked-files=no)" ] || die "$RUN has local changes: nobody edits the run checkout (SPEC §29.2)"
}

# A top-level scalar of a binding (projects/<id>.yaml): comment and quotes dropped.
scalar() {
  sed -n -E "s/^$2:[[:space:]]*([^#]*).*/\1/p" "$1" | head -n 1 | sed -E "s/[[:space:]]+\$//; s/^['\"]//; s/['\"]\$//"
}

# SPEC §29.3: after a release, run the new `ccp docs check`, `ccp tasks check` and (with an `adr` block)
# `ccp adr check` on each bound product's integration branch: origin/<branch> as the product last
# fetched it, else its local <branch>. They run in a shared clone in a temp dir, so nothing is written
# to the product. A branch without docs/delivery/plane.json (not adopted) is not checked. A stale
# product is reported, never fixed, and never fails the update.
check_products() {
  local bdir="${CCP_BINDINGS_DIR:-$RUN/projects}" ccp="$RUN/bin/ccp" b pid root branch sha ref tmp c out rc stale=0
  [ -d "$bdir" ] || return 0
  if [ ! -x "$ccp" ]; then echo "run-checkout: no $ccp; bound products not checked" >&2; return 0; fi
  for b in "$bdir"/*.yaml; do
    [ -f "$b" ] || continue
    pid="$(scalar "$b" project_id)"; pid="${pid:-$(basename "$b" .yaml)}"
    root="$(scalar "$b" product_root)"; root="${root/#\~/$HOME}"
    branch="$(scalar "$b" integration_branch)"; branch="${branch:-main}"
    if [ -z "$root" ] || ! git --no-optional-locks -C "$root" rev-parse --git-dir >/dev/null 2>&1; then
      echo "run-checkout: product $pid: not checked: no git repository at product_root ${root:-(unset)}"; continue
    fi
    sha=""
    for ref in "refs/remotes/origin/$branch" "refs/heads/$branch"; do
      sha="$(git --no-optional-locks -C "$root" rev-parse -q --verify "$ref^{commit}" 2>/dev/null)" && break
      sha=""
    done
    if [ -z "$sha" ]; then echo "run-checkout: product $pid: not checked: no branch $branch"; continue; fi
    tmp="$(mktemp -d)"
    if ! git clone -q --shared --no-checkout "$root" "$tmp/p" >/dev/null 2>&1 \
        || ! git -C "$tmp/p" checkout -q --detach "$sha" >/dev/null 2>&1; then
      rm -rf "$tmp"; echo "run-checkout: product $pid: not checked: cannot check out $branch ${sha:0:7}"; continue
    fi
    if [ ! -f "$tmp/p/docs/delivery/plane.json" ]; then
      rm -rf "$tmp"; echo "run-checkout: product $pid: not checked: $branch has no docs/delivery/plane.json (not adopted)"; continue
    fi
    local checks=("docs check" "tasks check") failed="" report=""
    if python3 -c 'import json,sys; sys.exit(0 if isinstance(json.load(open(sys.argv[1])).get("adr"), dict) else 1)' \
        "$tmp/p/docs/delivery/plane.json" 2>/dev/null; then
      checks+=("adr check")
    fi
    for c in "${checks[@]}"; do
      rc=0
      # shellcheck disable=SC2086  # $c is two words: the command group and `check`
      out="$(cd "$tmp/p" && env -u QUEUE_ROOT -u CCP_ROOT -u PROJECT_YAML CCP_NO_BINDING_QUEUE=1 \
        "$ccp" --root "$tmp/p" $c 2>&1)" || rc=$?
      if [ "$rc" -ne 0 ]; then
        failed="${failed:+$failed, }ccp $c"
        # sed reads all of it: `head` would close the pipe early and kill this script under pipefail.
        report+="$(printf '%s\n' "$out" | sed -n '1,20s/^/    /p')"$'\n'
      fi
    done
    rm -rf "$tmp"
    if [ -z "$failed" ]; then
      echo "run-checkout: product $pid ($branch ${sha:0:7}): clean"
    else
      stale=$((stale + 1))
      echo "run-checkout: product $pid ($branch ${sha:0:7}): STALE: $failed failed"
      printf '%s' "$report"
    fi
  done
  if [ "$stale" -gt 0 ]; then
    echo "run-checkout: $stale product(s) went stale with this release: tell each one's lead; the plane change's pull request names its migrate or regenerate command (SPEC §29.3)"
  fi
}

case "${1:-}" in
  install)
    if [ ! -d "$RUN/.git" ]; then
      url="$(git -C "$HERE" remote get-url origin)"
      git clone -q --branch main "$url" "$RUN"
    fi
    clean_on_main
    if [ -e "$LINK" ] && [ ! -L "$LINK" ]; then
      die "$LINK exists and is not a symlink: move it aside, then install again"
    fi
    mkdir -p "$(dirname "$LINK")"
    ln -sfn "$RUN/bin/ccp" "$LINK"
    echo "run-checkout: $RUN at $(g rev-parse --short HEAD); $LINK -> $RUN/bin/ccp"
    ;;
  update)
    clean_on_main
    g fetch -q origin
    keep="$(mktemp -d)"
    trap 'rm -rf "$keep"' EXIT
    for d in "${LOCAL_DIRS[@]}"; do
      if [ -d "$RUN/$d" ]; then cp -Rp "$RUN/$d" "$keep/"; fi
    done
    g merge -q --ff-only origin/main || die "origin/main does not fast-forward from $(g rev-parse --short HEAD)"
    for d in "${LOCAL_DIRS[@]}"; do   # a merge that untracks a local dir deletes it: put back what it removed
      if [ -d "$keep/$d" ]; then
        mkdir -p "$RUN/$d"
        cp -Rpn "$keep/$d/." "$RUN/$d/" || true   # -n keeps a file the merge left; BSD cp then exits 1
      fi
    done
    # Every kept file must be back before the copy is dropped: else keep it and say where.
    missing="$(cd "$keep" && find . -type f -o -type l | while read -r f; do [ -e "$RUN/$f" ] || [ -L "$RUN/$f" ] || echo "$f"; done)"
    if [ -n "$missing" ]; then
      trap - EXIT
      die "could not restore local files (kept in $keep): $missing"
    fi
    echo "run-checkout: $RUN at $(g rev-parse --short HEAD)"
    # The telemetry receiver (SPEC §24.2) keeps the code it started with: restart it when it runs.
    if launchctl print "gui/$(id -u)/$OTEL_LABEL" >/dev/null 2>&1; then
      # SIGTERM, not `kickstart -k`: the receiver flushes the rows it is holding for unresolved
      # sessions on SIGTERM, and KeepAlive starts it again with the new code.
      if launchctl kill TERM "gui/$(id -u)/$OTEL_LABEL" 2>/dev/null; then
        echo "run-checkout: restarted the telemetry receiver ($OTEL_LABEL)"
      else   # loaded but not running: the update itself succeeded, so this is a warning, not a failure
        echo "run-checkout: the telemetry receiver is loaded but not running; restart it from a normal terminal" >&2
      fi
    fi
    check_products
    ;;
  status)
    [ -d "$RUN/.git" ] || { echo "run-checkout: none at $RUN"; exit 1; }
    branch="$(g rev-parse --abbrev-ref HEAD)"
    dirty="$( [ -n "$(g status --porcelain --untracked-files=no)" ] && echo yes || echo no )"
    behind="$(g rev-list --count HEAD..origin/main 2>/dev/null || echo '?')"
    target="$(readlink "$LINK" 2>/dev/null || echo none)"
    python3 -c 'import json,sys; k=("run_checkout","branch","head","local_changes","behind_origin_main","ccp_link","ccp_link_target"); print(json.dumps(dict(zip(k, sys.argv[1:]))))' \
      "$RUN" "$branch" "$(g rev-parse --short HEAD)" "$dirty" "$behind" "$LINK" "$target"
    [ "$branch" = main ] && [ "$dirty" = no ] && [ "$behind" = 0 ] && [ "$target" = "$RUN/bin/ccp" ]
    ;;
  label)   # the receiver's launchd label, as `update` uses it
    echo "$OTEL_LABEL"
    ;;
  *) sed -n '2,13p' "$0"; exit 2 ;;
esac
