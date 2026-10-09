"""Canonical LogSense Modal application (bring-your-own-account).

Deploys the same ``logsense.integrations.api`` FastAPI service that runs
locally — the deterministic evidence/intake/analysis/report surface — into the
deploying user's own Modal workspace.

Deploy with::

    logsense modal deploy        # preferred
    python -m modal deploy -m logsense.deploy.modal_app

Customization (all optional, all owned by the deploying account):

- ``LOGSENSE_MODAL_APP_NAME``  Modal app name            (default: "logsense")
- ``LOGSENSE_MODAL_VOLUME``    workspace volume name     (default: "logsense-workspace")
- ``LOGSENSE_MODAL_SECRET``    Modal secret mounted into the function (e.g. to
                               provide LOGSENSE_API_TOKEN or OPENAI_API_KEY)

The historical ``modal_*.py`` files at the repository root are legacy
experiments and are not the deployment path for the packaged application.
"""

from __future__ import annotations

import os
from typing import Any

import modal

APP_NAME = os.environ.get("LOGSENSE_MODAL_APP_NAME", "logsense")
VOLUME_NAME = os.environ.get("LOGSENSE_MODAL_VOLUME", "logsense-workspace")
SECRET_NAME = os.environ.get("LOGSENSE_MODAL_SECRET")
WORKSPACE_DIR = "/data/workspace"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        # Same minimal runtime set as the 'api' extra of the logsense package.
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",
        "pydantic>=2.5.0",
        "pydantic-settings>=2.1.0",
        "python-dateutil>=2.8.2",
        "PyYAML>=6.0.1",
        "chardet>=5.2.0",
    )
    .env({"LOGSENSE_WORKSPACE": WORKSPACE_DIR})
    # Ships the caller's installed (or checked-out) logsense package, so the
    # deployed service runs the same canonical code the user installed.
    .add_local_python_source("logsense")
)

app = modal.App(APP_NAME)

volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

secrets = [modal.Secret.from_name(SECRET_NAME)] if SECRET_NAME else []


@app.function(
    image=image,
    volumes={"/data": volume},
    secrets=secrets,
    timeout=900,
    scaledown_window=300,
)
@modal.asgi_app()
def api() -> Any:
    """Serve the canonical LogSense local integration API."""
    from logsense.integrations.api import create_app

    return create_app()


@app.function(image=image, volumes={"/data": volume}, secrets=secrets, timeout=60)
@modal.fastapi_endpoint(method="GET")
def health() -> dict[str, Any]:
    """Deployment health probe for the user's own Modal app."""
    return {
        "status": "ok",
        "app": APP_NAME,
        "service": "logsense-canonical-api",
        "truthOwner": "DETERMINISTIC_LOGSENSE_CORE",
    }
