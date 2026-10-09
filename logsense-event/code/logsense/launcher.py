"""Launch the packaged LogSense workbench UI.

Resolves the Streamlit app that ships inside the ``logsense`` wheel so the
``logsense`` / ``logsense ui`` command works outside the Git checkout.
"""

from __future__ import annotations

import importlib.util
import subprocess  # nosec B404  # fixed-argv interpreter invocation only, no shell
import sys
from importlib.resources import files
from pathlib import Path


class UIUnavailable(RuntimeError):
    """Raised when the packaged workbench cannot be launched."""


def streamlit_installed() -> bool:
    return importlib.util.find_spec("streamlit") is not None


def ui_app_path() -> Path:
    app = Path(str(files("logsense.ui") / "app.py"))
    if not app.is_file():
        raise UIUnavailable(
            "the LogSense workbench is missing from this installation; reinstall the 'logsense' package"
        )
    return app


def launch_ui(
    *,
    host: str | None = None,
    port: int | None = None,
    headless: bool = False,
) -> int:
    """Run the canonical Streamlit workbench. Returns the process exit code."""
    if not streamlit_installed():
        print(
            "LogSense UI dependencies are not installed.\n"
            'Install them with:  pip install "logsense[ui]"   (or "logsense[team]")\n'
            "Then run:           logsense ui",
            file=sys.stderr,
        )
        return 2
    app = ui_app_path()
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.headless",
        "true" if headless else "false",
    ]
    if host:
        command += ["--server.address", host]
    if port:
        command += ["--server.port", str(port)]
    print(f"Starting LogSense workbench: {' '.join(command[3:])}")
    return subprocess.call(command)  # nosec B603  # argv list built from sys.executable + streamlit flags, no shell
