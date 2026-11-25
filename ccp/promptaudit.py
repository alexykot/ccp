"""A prompt audit written (SPEC §23.8): the one function every seat that launches or sends a prompt calls,
`ccp prompt`, the architect, the estimator and the team host's runner spawn and scope audits. It runs
`scripts/observability/write-prompt-audit.sh`, the writer, and returns the audit's `prompt_ref`."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from ccp.config import Config
from ccp.queue import OBS, QueueError

WRITER = OBS / "write-prompt-audit.sh"


def write(q: Path, cfg: Config | None, *, task_id: str, phase: str, argv: list[str],
          prompt: str | None = None, prompt_file: Path | str | None = None, **fields: str | None) -> str:
    """The audit's `prompt_ref`, the writer's last stdout line, under the queue `q`. The prompt is `prompt`, sent on
    stdin, or the file `prompt_file`; `argv` is what the seat launched or sent. Each `fields` entry that is not None
    is the writer's option of that name (`project_id` is `--project-id`). `--keep-body` goes when `cfg` is given and
    its `prompts.keep_body` is set. A writer that fails raises `QueueError("write-prompt-audit failed: <stderr>")`."""
    if (prompt is None) == (prompt_file is None):
        raise ValueError("write takes the prompt or a prompt file, one of them")
    cmd = ["bash", str(WRITER), "--task-id", task_id, "--phase", phase,
           "--prompt-file", "-" if prompt_file is None else str(prompt_file), "--argv", json.dumps(argv)]
    for name, value in fields.items():
        if value is not None:
            cmd += [f"--{name.replace('_', '-')}", str(value)]
    if cfg is not None and (cfg.prompts or {}).get("keep_body"):  # §23.8
        cmd.append("--keep-body")
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": str(q)})
    if r.returncode != 0:
        raise QueueError(f"write-prompt-audit failed: {r.stderr.strip()}", 1)
    out = r.stdout.strip().splitlines()
    return out[-1].strip() if out else ""
