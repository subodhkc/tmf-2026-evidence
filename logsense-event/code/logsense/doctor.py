"""``logsense doctor`` — lightweight environment diagnostics.

Reports configuration state only. It must never print API keys, tokens, or
evidence content.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str = ""


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("logsense")
    except Exception:
        import logsense

        return getattr(logsense, "__version__", "unknown")


def _modal_authenticated() -> str:
    if os.getenv("MODAL_TOKEN_ID") and os.getenv("MODAL_TOKEN_SECRET"):
        return "configured from environment"
    if (Path.home() / ".modal.toml").is_file():
        return "configured (~/.modal.toml)"
    return "not configured"


def gather_checks() -> list[DoctorCheck]:
    from logsense.user_config import (
        anthropic_key_source,
        openai_key_source,
        resolve_ai_provider,
        resolve_workspace_root,
    )

    checks: list[DoctorCheck] = []

    py = platform.python_version()
    supported = sys.version_info >= (3, 10)
    checks.append(DoctorCheck("Python", "OK" if supported else "FAIL", py))

    checks.append(DoctorCheck("Package", "OK", _package_version()))

    workspace = resolve_workspace_root()
    try:
        workspace.mkdir(parents=True, exist_ok=True)
        workspace_ok = os.access(workspace, os.W_OK)
    except OSError:
        workspace_ok = False
    checks.append(DoctorCheck("Workspace", "OK" if workspace_ok else "FAIL", str(workspace)))

    checks.append(
        DoctorCheck(
            "UI (Streamlit)",
            "OK" if _module_available("streamlit") else "not installed",
            "" if _module_available("streamlit") else 'pip install "logsense[ui]"',
        )
    )

    api_ready = _module_available("fastapi") and _module_available("uvicorn")
    checks.append(
        DoctorCheck(
            "API",
            "OK" if api_ready else "not installed",
            "" if api_ready else 'pip install "logsense[api]"',
        )
    )

    checks.append(
        DoctorCheck(
            "MCP",
            "OK" if _module_available("mcp") else "not installed",
            "" if _module_available("mcp") else 'pip install "logsense[mcp]"',
        )
    )

    checks.append(DoctorCheck("AI provider", "OK", resolve_ai_provider()))

    openai_source = openai_key_source()
    agents_ok = _module_available("agents")
    checks.append(
        DoctorCheck(
            "OpenAI (Ask LogSense)",
            f"key {openai_source}" if openai_source else "not configured",
            "provider installed" if agents_ok else 'pip install "logsense[investigator]"',
        )
    )

    anthropic_source = anthropic_key_source()
    anthropic_ok = _module_available("anthropic")
    checks.append(
        DoctorCheck(
            "Claude (Ask LogSense)",
            f"key {anthropic_source}" if anthropic_source else "not configured",
            "provider installed" if anthropic_ok else 'pip install "logsense[investigator]"',
        )
    )

    if _module_available("modal"):
        checks.append(DoctorCheck("Modal", "installed", _modal_authenticated()))
    else:
        checks.append(DoctorCheck("Modal", "not installed", 'pip install "logsense[modal]"'))

    return checks


def render(checks: list[DoctorCheck]) -> str:
    width = max(len(check.name) for check in checks)
    lines = ["LogSense Doctor", ""]
    for check in checks:
        line = f"{check.name:<{width}}  {check.status}"
        if check.detail:
            line += f"  ({check.detail})"
        lines.append(line)
    return "\n".join(lines)


def run() -> int:
    checks = gather_checks()
    print(render(checks))
    return 0 if all(check.status != "FAIL" for check in checks) else 1
