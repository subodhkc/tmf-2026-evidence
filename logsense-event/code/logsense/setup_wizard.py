"""``logsense setup`` — first-run guided configuration.

Event-first ordering: pick the AI investigator, confirm the workspace, then
optional advanced/cloud deployment. Deterministic local analysis never
requires this wizard; the recommended competition experience uses OpenAI or
Claude to investigate deterministic LogSense output.

Secret handling rules:
- an entered key is treated as a secret: never printed, never logged, never
  written to case data, reports, exports, or the Git checkout;
- session-only by default; persistence requires explicit opt-in and lands in
  ``~/.logsense/secrets.env`` (owner-only permissions where supported).
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

from logsense.ai.provider import (
    PROVIDER_ANTHROPIC,
    PROVIDER_LABELS,
    PROVIDER_NAMES,
    PROVIDER_OPENAI,
    provider_key_env,
    provider_model_env,
)
from logsense.deploy import modal as modal_helper
from logsense.user_config import (
    default_workspace_root,
    load_secrets_into_environ,
    provider_key_source,
    resolve_ai_provider,
    resolve_workspace_root,
    save_ai_provider,
    save_secret,
    save_user_config,
    secrets_path,
)


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default
    return answer or default


def _ask_yes_no(prompt: str, default: bool = False) -> bool:
    marker = "Y/n" if default else "y/N"
    answer = _ask(f"{prompt} [{marker}]", "")
    if not answer:
        return default
    return answer.lower().startswith("y")


def _step_ai_investigator() -> None:
    print("\n1. AI investigator\n")
    print("   AI helps you investigate and explain the deterministic LogSense")
    print("   evidence. The deterministic engine remains the source of forensic truth.\n")
    print("   Choose your AI investigator:")
    for index, name in enumerate(PROVIDER_NAMES, start=1):
        configured = provider_key_source(name)
        marker = f" (key configured: {configured})" if configured else ""
        print(f"     {index}. {PROVIDER_LABELS[name]}{marker}")
    print("     3. Skip for now\n")

    current = resolve_ai_provider()
    default_choice = str(PROVIDER_NAMES.index(current) + 1)
    choice = _ask("   Provider", default_choice)
    if choice in {"", "3", "skip", "none"}:
        print("   Skipped. Deterministic analysis works without AI; rerun")
        print("   'logsense setup' anytime to connect OpenAI or Claude.")
        return
    provider = PROVIDER_NAMES[0]
    if choice in PROVIDER_NAMES:
        provider = choice
    elif choice in PROVIDER_LABELS.values() or choice.lower() in ("claude", "openai"):
        provider = PROVIDER_ANTHROPIC if "claude" in choice.lower() else PROVIDER_OPENAI
    elif choice.isdigit() and 1 <= int(choice) <= len(PROVIDER_NAMES):
        provider = PROVIDER_NAMES[int(choice) - 1]

    label = PROVIDER_LABELS[provider]
    key_env = provider_key_env(provider)
    model_env = provider_model_env(provider)
    save_ai_provider(provider)
    print(f"\n   AI investigator: {label}")

    if provider_key_source(provider):
        print(f"   {label} key already configured — nothing to enter.")
        model = os.getenv(model_env)
        if model:
            print(f"   Model: {model} ({model_env})")
        return

    if provider == PROVIDER_OPENAI:
        print("   Get a key at https://platform.openai.com/api-keys")
    else:
        print("   Get a key at https://console.anthropic.com/")
    try:
        key = getpass.getpass(f"   {label} API key (input hidden, Enter to skip): ").strip()
    except EOFError:
        key = ""
    if not key:
        print(f"   Skipped. Set {key_env} later or rerun 'logsense setup'.")
        return
    os.environ[key_env] = key  # session only unless persisted below
    model = _ask("   Model (blank = provider default)", "")
    if model:
        os.environ[model_env] = model
    if _ask_yes_no("   Remember this key on this device?", default=False):
        save_secret(key_env, key)
        save_secret("LOGSENSE_AI_PROVIDER", provider)
        if model:
            save_secret(model_env, model)
        print(f"   Stored in {secrets_path()} — outside the repo and outside the workspace.")
        print("   It is loaded into the environment when LogSense launches.")
    else:
        print("   Using the key for this session only.")
    print(f"   {label}: configured. The key is never written to cases, reports, or exports.")


def _step_workspace() -> Path:
    print("\n2. LogSense workspace\n")
    current = resolve_workspace_root()
    default = default_workspace_root()
    print("   Cases and committed evidence live outside the repository.")
    print(f"   Default:  {default}")
    if current != default:
        print(f"   Current:  {current} (from LOGSENSE_WORKSPACE or user config)")
    choice = _ask("   Workspace path", str(current))
    workspace = Path(choice).expanduser()
    workspace.mkdir(parents=True, exist_ok=True)
    if workspace != default:
        save_user_config({"workspace": str(workspace)})
        print("   Saved to user config. LOGSENSE_WORKSPACE still overrides it.")
    else:
        save_user_config({"workspace": None})
    print(f"   Workspace: {workspace}")
    return workspace


def _step_modal() -> None:
    print("\n3. Advanced / Cloud Options (optional)\n")
    print("   Modal deployment — run LogSense in your own Modal account.")
    print("   Local operation is recommended for the competition; Modal is only")
    print("   useful if you specifically want hosted cloud execution.")
    print("   (Team-hosted alternative: set LOGSENSE_HOSTED_URL to a URL supplied")
    print("    by your team.)")
    if not _ask_yes_no("\n   Configure Modal deployment now?", default=False):
        print("   Skipped. Run 'logsense modal deploy' anytime.")
        return
    if not modal_helper.modal_installed():
        if not _ask_yes_no("   Modal is not installed. Install it now?", default=True):
            print("   Skipped Modal install.")
            return
        if modal_helper.install_modal() != 0:
            print('   Modal install failed. Try:  pip install "logsense[modal]"')
            return
    if not modal_helper.modal_authenticated():
        print("\n   Modal needs to authenticate with *your* account.")
        if not _ask_yes_no("   Run 'modal setup' now (opens a browser)?", default=True):
            print("   Skipped authentication. Run 'python -m modal setup' later.")
            return
        if modal_helper.run_modal_auth() != 0 or not modal_helper.modal_authenticated():
            print("   Authentication did not complete; rerun 'logsense modal deploy' later.")
            return
    print("\n   Deploying the canonical LogSense service to your Modal account...")
    code = modal_helper.deploy()
    if code == 0:
        print("   Deployment finished. Your Modal dashboard shows the app URL.")
    else:
        print(f"   Deployment exited with code {code}. See output above.")


def run_setup() -> int:
    print("Welcome to LogSense\n")
    print("TM Forum Competition Setup\n")
    print("This short setup configures your AI investigator and workspace.")
    print("Deterministic local analysis works even if you skip every step.")
    if not sys.stdin.isatty():
        print(
            "\nNon-interactive session detected — nothing was changed.\n"
            "Equivalent manual configuration:\n"
            "  AI        : set LOGSENSE_AI_PROVIDER=openai|anthropic plus\n"
            "              OPENAI_API_KEY or ANTHROPIC_API_KEY\n"
            "              (models: LOGSENSE_OPENAI_MODEL / LOGSENSE_ANTHROPIC_MODEL)\n"
            f"  workspace : set LOGSENSE_WORKSPACE (default {default_workspace_root()})\n"
            "  Modal     : pip install \"logsense[modal]\", then 'modal setup',\n"
            "              then 'logsense modal deploy'\n"
            "  verify    : logsense doctor"
        )
        return 0

    load_secrets_into_environ()
    _step_ai_investigator()
    _step_workspace()
    _step_modal()

    print("\n4. Finish\n")
    print("   Next steps:")
    print("     logsense            launch the workbench UI (Start Here page)")
    print("     logsense demo       unpack the bundled sample evidence")
    print("     logsense doctor     verify your environment")
    return 0
