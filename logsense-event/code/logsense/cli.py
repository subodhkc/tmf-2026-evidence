"""``logsense`` — the one command a teammate needs.

Bare ``logsense`` launches the forensic workbench UI. Subcommands cover
first-run setup, diagnostics, local deterministic analysis, the canonical
API/MCP surfaces, and bring-your-own-account Modal deployment.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import logsense
from logsense.user_config import load_secrets_into_environ, resolve_workspace_root

if TYPE_CHECKING:
    from logsense.analysis.spine import ArtifactEvidence

_EPILOG = """\
Getting started:
  logsense setup     first-run configuration (workspace, optional OpenAI, optional Modal)
  logsense           launch the forensic workbench UI
  logsense demo      unpack bundled sample evidence
  logsense doctor    check your environment
"""


def _version() -> str:
    try:
        from importlib.metadata import version

        return version("logsense")
    except Exception:
        return logsense.__version__


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _artifact_for_file(path: Path, ingested_at: str) -> ArtifactEvidence:
    from logsense.analysis.spine import ArtifactEvidence

    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    media_type, _ = mimetypes.guess_type(path.name)
    return ArtifactEvidence(
        artifact_id=f"artifact:{digest[:24]}",
        path=path.name,
        content=content,
        ingested_at=ingested_at,
        media_type=media_type,
        currentness="UNKNOWN",
    )


def _cmd_ui(args: argparse.Namespace) -> int:
    from logsense.launcher import launch_ui

    return launch_ui(host=args.host, port=args.port, headless=args.headless)


def _cmd_setup(_args: argparse.Namespace) -> int:
    from logsense.setup_wizard import run_setup

    return run_setup()


def _cmd_api(_args: argparse.Namespace) -> int:
    try:
        from logsense.integrations.api import run
    except ImportError:
        print(
            "API dependencies are not installed.\n"
            'Install them with:  pip install "logsense[api]"   (or "logsense[team]")',
            file=sys.stderr,
        )
        return 2
    run()
    return 0


def _cmd_mcp(_args: argparse.Namespace) -> int:
    try:
        from logsense.integrations.mcp import MCPUnavailable, run
    except ImportError:
        print(
            "MCP dependencies are not installed.\n"
            'Install them with:  pip install "logsense[mcp]"   (or "logsense[team]")',
            file=sys.stderr,
        )
        return 2
    try:
        run()
    except MCPUnavailable as exc:
        print(f"{exc}", file=sys.stderr)
        return 2
    return 0


def _cmd_modal(args: argparse.Namespace) -> int:
    from logsense.deploy import modal as modal_helper

    if args.modal_command == "status":
        print(f"Modal: {modal_helper.modal_status()}")
        return 0
    if args.modal_command == "auth":
        if not modal_helper.modal_installed():
            print('Modal is not installed. Run: pip install "logsense[modal]"')
            return 2
        return modal_helper.run_modal_auth()
    return modal_helper.deploy()


def _cmd_analyze(args: argparse.Namespace) -> int:
    from logsense.integrations.service import IntegrationService

    paths = [Path(item).expanduser() for item in args.files]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        print(f"Evidence files not found: {missing}", file=sys.stderr)
        return 2
    created_at = args.created_at or _utc_now()
    artifacts = [_artifact_for_file(path, created_at) for path in paths]
    case_id = args.case
    evidence_set_id = args.evidence_set or f"{case_id}:evidence"
    if args.run:
        analysis_run_id = args.run
    else:
        seed = "".join(sorted(artifact.artifact_id for artifact in artifacts))
        analysis_run_id = f"run:{hashlib.sha256(seed.encode()).hexdigest()[:16]}"
    roles = [role for role in (args.expected_role or []) if role]
    service = IntegrationService()
    try:
        result: dict[str, Any] = service.analyze(
            {
                "caseId": case_id,
                "evidenceSetId": evidence_set_id,
                "analysisRunId": analysis_run_id,
                "createdAt": created_at,
                "expectedSourceRoles": roles,
                "artifacts": [
                    {
                        "artifactId": artifact.artifact_id,
                        "path": artifact.path,
                        "contentBase64": base64.b64encode(artifact.content).decode("ascii"),
                        "ingestedAt": artifact.ingested_at,
                        "mediaType": artifact.media_type,
                        "currentness": artifact.currentness,
                        "completenessState": artifact.completeness_state,
                    }
                    for artifact in artifacts
                ],
            }
        )
    except Exception as exc:
        print(f"Analysis failed: {exc}", file=sys.stderr)
        return 1
    return _emit_json(result, args.out)


def _cmd_report(args: argparse.Namespace) -> int:
    from logsense.integrations.service import IntegrationService

    path = Path(args.analysis).expanduser()
    if not path.is_file():
        print(f"Analysis JSON not found: {path}", file=sys.stderr)
        return 2
    try:
        analysis = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid analysis JSON: {exc}", file=sys.stderr)
        return 2
    report = IntegrationService().build_report(analysis, rendered_at=args.rendered_at)
    return _emit_json(report, args.out)


def _emit_json(value: Any, out: str | None) -> int:
    text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if out:
        Path(out).expanduser().write_text(text, encoding="utf-8")
        print(f"Wrote {out}")
    else:
        sys.stdout.write(text)
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    from logsense.samples import SAMPLE_ID, SAMPLE_TITLE, copy_sample_to

    destination_root = (
        Path(args.dest).expanduser() if args.dest else resolve_workspace_root() / "samples"
    )
    try:
        target = copy_sample_to(destination_root)
    except Exception as exc:
        print(f"Demo evidence unavailable: {exc}", file=sys.stderr)
        return 2
    files = " ".join(f'"{target / name}"' for name in sorted(p.name for p in target.iterdir()))
    print(f"Sample evidence: {SAMPLE_TITLE}")
    print(f"Copied to: {target}\n")
    print("Try it:")
    print(f"  logsense analyze --case {SAMPLE_ID} {files} --out analysis.json")
    print("  logsense report analysis.json --out report.json")
    print("  logsense   # then load analysis.json / report.json in the workbench sidebar")
    print("\nOr in the workbench: create a case, open GATHER, and upload the files above.")
    return 0


def _cmd_doctor(_args: argparse.Namespace) -> int:
    from logsense.doctor import run

    return run()


def _cmd_version(_args: argparse.Namespace) -> int:
    print(f"LogSense {_version()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logsense",
        description="LogSense — offline-first deterministic forensic investigation workbench.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"LogSense {_version()}")
    sub = parser.add_subparsers(dest="command")

    for name in ("ui", "start"):
        ui = sub.add_parser(name, help="launch the forensic workbench UI")
        ui.add_argument("--host", default=None, help="bind address (default: Streamlit default)")
        ui.add_argument("--port", type=int, default=None, help="port (default: Streamlit default)")
        ui.add_argument("--headless", action="store_true", help="do not open a browser")
        ui.set_defaults(func=_cmd_ui)

    sub.add_parser("setup", help="guided first-run setup").set_defaults(func=_cmd_setup)
    sub.add_parser("api", help="run the canonical local API").set_defaults(func=_cmd_api)
    sub.add_parser("mcp", help="run the canonical MCP server").set_defaults(func=_cmd_mcp)

    modal = sub.add_parser("modal", help="Modal cloud deployment helpers")
    modal.add_argument(
        "modal_command",
        nargs="?",
        default="deploy",
        choices=("deploy", "status", "auth"),
        help="deploy (default) | status | auth",
    )
    modal.set_defaults(func=_cmd_modal)

    analyze = sub.add_parser("analyze", help="deterministically analyze evidence files")
    analyze.add_argument("files", nargs="+", help="evidence files (csv/json/jsonl/yaml/log/…)")
    analyze.add_argument("--case", required=True, help="case ID the analysis belongs to")
    analyze.add_argument(
        "--evidence-set", default=None, help="evidence set ID (default: <case>:evidence)"
    )
    analyze.add_argument(
        "--run", default=None, help="analysis run ID (default: derived from evidence digests)"
    )
    analyze.add_argument(
        "--created-at", default=None, help="ISO-8601 creation timestamp (default: now)"
    )
    analyze.add_argument(
        "--expected-role",
        action="append",
        dest="expected_role",
        help="expected source role; repeatable",
    )
    analyze.add_argument("--out", default=None, help="write analysis JSON here instead of stdout")
    analyze.set_defaults(func=_cmd_analyze)

    report = sub.add_parser("report", help="build the deterministic report from analysis JSON")
    report.add_argument("analysis", help="path to analysis JSON produced by 'logsense analyze'")
    report.add_argument("--rendered-at", default=None, help="ISO-8601 render timestamp (optional)")
    report.add_argument("--out", default=None, help="write report JSON here instead of stdout")
    report.set_defaults(func=_cmd_report)

    demo = sub.add_parser("demo", help="unpack bundled sample evidence")
    demo.add_argument(
        "--dest", default=None, help="destination directory (default: <workspace>/samples)"
    )
    demo.set_defaults(func=_cmd_demo)

    sub.add_parser("doctor", help="diagnose the local environment").set_defaults(func=_cmd_doctor)
    sub.add_parser("version", help="print the LogSense version").set_defaults(func=_cmd_version)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_secrets_into_environ()
    parser = build_parser()
    args = parser.parse_args(argv)
    func: Callable[[argparse.Namespace], int] | None = getattr(args, "func", None)
    if func is None:
        # Bare `logsense` launches the workbench UI.
        args = parser.parse_args(["ui"])
        func = args.func
        return func(args)
    return func(args)


if __name__ == "__main__":
    sys.exit(main())
