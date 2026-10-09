"""User-local LogSense configuration.

Canonical resolution order for the workspace root:

1. explicit argument (API/service callers)
2. ``LOGSENSE_WORKSPACE`` environment variable
3. ``~/.logsense/config.json`` ``workspace`` key (written by ``logsense setup``)
4. ``~/.logsense/workspace`` default

Optional provider secrets entered during ``logsense setup`` may be persisted —
only with explicit opt-in — to ``~/.logsense/secrets.env``. That file lives
outside the Git checkout and outside the evidence workspace, is permission-
restricted where the platform supports it, and is never included in case data,
forensic reports, or exports.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_ENV_WORKSPACE = "LOGSENSE_WORKSPACE"
_CONFIG_KEYS = ("workspace", "ai_provider")


def user_config_dir() -> Path:
    """User-local LogSense configuration directory (outside the workspace)."""
    override = os.getenv("LOGSENSE_CONFIG_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".logsense"


def default_workspace_root() -> Path:
    return user_config_dir() / "workspace"


def config_path() -> Path:
    return user_config_dir() / "config.json"


def secrets_path() -> Path:
    return user_config_dir() / "secrets.env"


def load_user_config() -> dict[str, Any]:
    path = config_path()
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in _CONFIG_KEYS if key in value}


def save_user_config(updates: Mapping[str, Any]) -> Path:
    config = load_user_config()
    for key in _CONFIG_KEYS:
        if key in updates:
            value = updates[key]
            if value in (None, ""):
                config.pop(key, None)
            else:
                config[key] = str(value)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def resolve_workspace_root(explicit: Path | str | None = None) -> Path:
    """Resolve the canonical workspace root without changing semantics."""
    if explicit is not None and str(explicit).strip():
        return Path(explicit).expanduser()
    configured = os.getenv(_ENV_WORKSPACE)
    if configured and configured.strip():
        return Path(configured).expanduser()
    persisted = load_user_config().get("workspace")
    if persisted:
        return Path(str(persisted)).expanduser()
    return default_workspace_root()


def _restrict_permissions(path: Path) -> None:
    """Best-effort owner-only permissions; no-op where unsupported."""
    with contextlib.suppress(OSError):
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def read_secrets_file(path: Path | None = None) -> dict[str, str]:
    """Parse a minimal KEY=VALUE env file. Never logs or returns comments."""
    target = path or secrets_path()
    if not target.is_file():
        return {}
    values: dict[str, str] = {}
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        key = key.strip()
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
            raw = raw[1:-1]
        if key:
            values[key] = raw
    return values


def load_secrets_into_environ(path: Path | None = None) -> None:
    """Load user-local secrets into the process environment.

    Existing environment variables always win; secrets set by the operator in
    the shell are never overridden by the persisted file.
    """
    for key, value in read_secrets_file(path).items():
        os.environ.setdefault(key, value)


def save_secret(name: str, value: str, *, path: Path | None = None) -> Path:
    """Persist one secret to the user-local secrets file (opt-in only)."""
    if not name or "=" in name or "\n" in name:
        raise ValueError("invalid secret name")
    if "\n" in value or "\r" in value:
        raise ValueError("secret value must be a single line")
    target = path or secrets_path()
    existing = read_secrets_file(target)
    existing[name] = value
    target.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{key}={existing[key]}\n" for key in sorted(existing))
    target.write_text(body, encoding="utf-8")
    _restrict_permissions(target)
    return target


def openai_key_source() -> str | None:
    """Report where an OpenAI key is configured, without revealing it."""
    return provider_key_source("openai")


def anthropic_key_source() -> str | None:
    """Report where an Anthropic key is configured, without revealing it."""
    return provider_key_source("anthropic")


def provider_key_source(provider: str) -> str | None:
    """Report where one provider's key is configured, without revealing it."""
    from logsense.ai.provider import provider_key_env

    env_name = provider_key_env(provider)
    if os.getenv(env_name):
        return "environment"
    if read_secrets_file().get(env_name):
        return "user secrets file"
    return None


def resolve_ai_provider() -> str:
    """Resolve the active investigator provider ID.

    Order: ``LOGSENSE_AI_PROVIDER`` → persisted ``ai_provider`` config → the
    provider whose key is configured → ``openai``.
    """
    from logsense.ai.provider import PROVIDER_ANTHROPIC, PROVIDER_OPENAI, normalize_provider_name

    explicit = os.getenv("LOGSENSE_AI_PROVIDER") or load_user_config().get("ai_provider")
    if explicit:
        return normalize_provider_name(str(explicit))
    if openai_key_source():
        return PROVIDER_OPENAI
    if anthropic_key_source():
        return PROVIDER_ANTHROPIC
    return PROVIDER_OPENAI


def save_ai_provider(provider: str) -> Path:
    """Persist the chosen AI provider to user config (never a secret)."""
    from logsense.ai.provider import normalize_provider_name

    return save_user_config({"ai_provider": normalize_provider_name(provider)})
