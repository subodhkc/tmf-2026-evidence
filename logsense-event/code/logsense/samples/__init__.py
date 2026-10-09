"""Packaged demonstration evidence.

The sample set is the synthetic Golden fixture ``GFB-001`` ("healthy
authorized tilt change"), shipped inside the wheel so a new user can run a
real deterministic analysis immediately after install.
"""

from __future__ import annotations

import shutil
from importlib.resources import files
from pathlib import Path

SAMPLE_ID = "gfb-001"
SAMPLE_TITLE = "GFB-001 — healthy authorized tilt change (synthetic Golden fixture)"
SAMPLE_FILES = (
    "baseline_policy.yaml",
    "baseline_agent_trace.jsonl",
    "baseline_api.csv",
    "baseline_state.csv",
    "candidate_agent_trace.jsonl",
    "candidate_state.csv",
)


class SampleUnavailable(RuntimeError):
    """Raised when packaged sample evidence is missing from the install."""


def sample_dir() -> Path:
    """Return the packaged sample directory, or raise if it is not shipped."""
    root = Path(str(files("logsense") / "samples" / SAMPLE_ID))
    if not root.is_dir():
        raise SampleUnavailable(
            "packaged sample evidence is missing; reinstall LogSense or supply your own evidence files"
        )
    return root


def copy_sample_to(destination_root: Path | str) -> Path:
    """Copy the packaged sample into ``destination_root`` and return its path."""
    target = Path(destination_root).expanduser() / SAMPLE_ID
    source = sample_dir()
    target.mkdir(parents=True, exist_ok=True)
    for name in SAMPLE_FILES:
        shutil.copyfile(source / name, target / name)
    return target
