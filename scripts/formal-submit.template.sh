#!/usr/bin/env bash
# formal-submit.template.sh <task_id>: formal-submit, the standing DoD's checklist between the review and the
# verify (SPEC §15.1), kept for products that call it. It runs the plane's own check, `ccp tasks submit`, and
# exits with its code (house rule E7: a script only wraps ccp). Needs QUEUE_ROOT and `ccp` on PATH.

set -uo pipefail

TASK_ID="${1:?usage: formal-submit.template.sh <task_id>}"
exec ccp tasks submit "$TASK_ID"
