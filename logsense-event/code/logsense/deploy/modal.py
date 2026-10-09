"""Modal deployment helper for ``logsense modal``.

Deploys the canonical LogSense integration service into the *caller's own*
Modal account. No HAIEC credentials, secrets, or workspace are required or
referenced; the deployment owns its own app, volume, secrets, and URL.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess  # nosec B404  # fixed-argv interpreter invocations only, no shell
import sys
from pathlib import Path

MODAL_PACKAGE_SPEC = "modal>=0.67.28"


def modal_installed() -> bool:
    try:
        return importlib.util.find_spec("modal") is not None
    except (ImportError, ValueError):
        return False


def modal_authenticated() -> bool:
    """Cheap local check: env token pair or an existing ~/.modal.toml profile."""
    if os.getenv("MODAL_TOKEN_ID") and os.getenv("MODAL_TOKEN_SECRET"):
        return True
    return (Path.home() / ".modal.toml").is_file()


def modal_status() -> str:
    if not modal_installed():
        return "not installed"
    return "installed, authenticated" if modal_authenticated() else "installed, not authenticated"


def install_modal() -> int:
    """Install the Modal package using the current interpreter's pip."""
    return subprocess.call([sys.executable, "-m", "pip", "install", MODAL_PACKAGE_SPEC])  # nosec B603  # fixed argv, no shell


def run_modal_auth() -> int:
    """Run the supported Modal authentication flow (browser-based token setup)."""
    return subprocess.call([sys.executable, "-m", "modal", "setup"])  # nosec B603  # fixed argv, no shell


def deploy() -> int:
    """Deploy the canonical LogSense service to the caller's Modal account."""
    if not modal_installed():
        print(
            "Modal is not installed. Install it first:\n"
            '  pip install "logsense[modal]"\n'
            "or run 'logsense setup' for a guided install."
        )
        return 2
    if not modal_authenticated():
        print(
            "Modal is not authenticated. Run:\n"
            f"  {sys.executable} -m modal setup\n"
            "This opens a browser and stores a token in ~/.modal.toml — "
            "your own account, not anyone else's."
        )
        return 2
    # Module-mode deploy: modal resolves the packaged logsense.deploy.modal_app
    # module and auto-includes the local 'logsense' package in the image.
    return subprocess.call(  # nosec B603  # fixed argv, no shell
        [sys.executable, "-m", "modal", "deploy", "-m", "logsense.deploy.modal_app"]
    )
