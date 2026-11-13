#!/usr/bin/env bash
# team.sh — SPEC §2 Claude team: the runner teammate's lifecycle and the gate ledger.
#
# Lead (design seat):
#   team.sh runner spawn [--scope ID,ID] [--review-point R<n>]   record + print the fixed spawn (Agent tool);
#       --review-point without --scope: the point's open tagged tasks (SPEC §22); a runner still live
#       (not rotated) is stopped first: its shutdown comes before the spawn (SPEC §16.5)
#   team.sh runner spawn --dry-run [...]                     the same refusals; print the actions and the readiness
#                                                            checks, writing nothing (SPEC §16.5)
#   team.sh runner prompt --scope ID,ID                      print the fixed spawn prompt only
#   team.sh runner bind --name NAME                          the name the Agent result gave the runner
#                                                            (`runner-2` after a rotation): hook and prompts follow it
#   team.sh runner scope [--add ID,ID] [--remove ID,ID]       widen/narrow a running runner's scope;
#                                                            prints the message to send it
#   team.sh runner rotate [--reason TEXT] [--force]          record a rotation, then spawn again; refused
#                                                            while worker runs are open (§16.5)
#   team.sh runner stop [--drain] [--reason TEXT]            stop now, or let the runner drain
#   team.sh runner status                                    work.json, open gates, open questions
# Several runners (SPEC §16.5; plane.json parallel.max_in_flight above 1):
#   team.sh runner spawn --count N [--scope ...]              record N slots (runner-1 …) and print a spawn each
#   team.sh runner spawn --slot SLOT                          respawn one slot (after a rotation or a restart)
#   team.sh runner bind --name NAME --as SLOT                 the name the Agent result gave that slot
#   team.sh runner rotate|stop --slot SLOT [--drain]          one runner; stop with no slot: all of them
#   team.sh gate decide <id> --decision approved|refused --resolution TEXT --authority TEXT [--by ...]
#   team.sh gate ask-operator <id>                               the design seat takes it to the operator
# Runner:
#   team.sh gate open --task-id ID --class CLASS --brief TEXT [--ask CMD] [--standing REF]
#   team.sh gate status <id>        exit 0 approved, 3 open / waiting on the operator, 4 refused
#   team.sh gate list [--open]
#
# Prints one JSON object; `actions` lists what the seat must still do itself (spawn, message).
# Env: QUEUE_ROOT (required), PROJECT_YAML (default: the binding naming QUEUE_ROOT, SPEC §8.3). No secrets.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$HERE/observability/team.py" "$@"
