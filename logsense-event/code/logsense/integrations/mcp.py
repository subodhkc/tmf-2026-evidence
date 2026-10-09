from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, Protocol, cast

from logsense.integrations.service import IntegrationRequestError, IntegrationService


class MCPUnavailable(RuntimeError):
    """Raised when the optional MCP SDK is not installed."""


class MCPServerLike(Protocol):
    def tool(self, *args: Any, **kwargs: Any) -> Any: ...

    def run(self, transport: str = "stdio", **kwargs: Any) -> None: ...


class MCPToolDispatcher:
    """Provider-neutral MCP tool dispatcher over the canonical service facade."""

    TOOL_NAMES = (
        "logsense_capabilities",
        "logsense_create_case",
        "logsense_list_cases",
        "logsense_import_evidence",
        "logsense_analyze",
        "logsense_get_snapshot",
        "logsense_get_findings",
        "logsense_prepare_verification",
        "logsense_finalize_verification",
        "logsense_build_report",
        "logsense_export_report_json",
        "logsense_investigator_tool",
    )

    def __init__(self, service: IntegrationService | None = None) -> None:
        self.service = service or IntegrationService()

    def invoke(self, tool_name: str, arguments: Mapping[str, Any] | None = None) -> Any:
        args = dict(arguments or {})
        if tool_name == "logsense_capabilities":
            return self.service.capabilities()
        if tool_name == "logsense_create_case":
            return self.service.create_case(
                case_id=str(args.get("caseId") or ""),
                title=str(args["title"]) if args.get("title") is not None else None,
                created_at=str(args["createdAt"]) if args.get("createdAt") is not None else None,
            )
        if tool_name == "logsense_list_cases":
            return self.service.list_cases()
        if tool_name == "logsense_import_evidence":
            return self.service.import_evidence(args)
        if tool_name == "logsense_analyze":
            return self.service.analyze(args)
        if tool_name == "logsense_get_snapshot":
            analysis = args.get("analysis")
            if not isinstance(analysis, Mapping):
                raise IntegrationRequestError("analysis must be an object")
            return self.service.get_snapshot(analysis)
        if tool_name == "logsense_get_findings":
            analysis = args.get("analysis")
            if not isinstance(analysis, Mapping):
                raise IntegrationRequestError("analysis must be an object")
            return self.service.get_findings(analysis)
        if tool_name == "logsense_prepare_verification":
            return self.service.prepare_verification(args)
        if tool_name == "logsense_finalize_verification":
            return self.service.finalize_verification(args)
        if tool_name == "logsense_build_report":
            analysis = args.get("analysis")
            if not isinstance(analysis, Mapping):
                raise IntegrationRequestError("analysis must be an object")
            rendered_at = args.get("renderedAt")
            return self.service.build_report(
                analysis,
                rendered_at=str(rendered_at) if rendered_at is not None else None,
            )
        if tool_name == "logsense_export_report_json":
            analysis = args.get("analysis")
            if not isinstance(analysis, Mapping):
                raise IntegrationRequestError("analysis must be an object")
            return self.service.export_report_json(analysis)
        if tool_name == "logsense_investigator_tool":
            analysis = args.get("analysis")
            report = args.get("report")
            tool_arguments = args.get("arguments")
            for name, value in (
                ("analysis", analysis),
                ("report", report),
                ("arguments", tool_arguments),
            ):
                if value is not None and not isinstance(value, Mapping):
                    raise IntegrationRequestError(f"{name} must be an object")
            return self.service.invoke_investigator_tool(
                tool_name=str(args.get("toolName") or ""),
                arguments=tool_arguments,
                analysis=analysis,
                report=report,
            )
        raise IntegrationRequestError(f"unknown MCP tool: {tool_name}")


def create_mcp_server(*, service: IntegrationService | None = None) -> MCPServerLike:
    """Create the optional MCP v2 server without making MCP a core dependency."""
    try:
        from mcp.server import MCPServer
    except ImportError as exc:  # pragma: no cover - exercised by installation boundary
        raise MCPUnavailable("install LogSense with the 'mcp' extra to run the MCP server") from exc

    dispatcher = MCPToolDispatcher(service)
    server = MCPServer(
        "LogSense Forensic Integration",
        description=(
            "Read-first MCP surface over deterministic LogSense forensic application services. "
            "Transport output cannot establish or directly mutate canonical forensic truth."
        ),
        version="1.0.0",
    )

    @server.tool(name="logsense_capabilities")
    def capabilities() -> dict[str, Any]:
        """Return the LogSense integration capability and semantic-boundary manifest."""
        result: dict[str, Any] = dispatcher.invoke("logsense_capabilities")
        return result

    @server.tool(name="logsense_create_case")
    def create_case(
        case_id: str, title: str | None = None, created_at: str | None = None
    ) -> dict[str, Any]:
        """Create a local case workspace. This is orchestration, not forensic truth mutation."""
        result: dict[str, Any] = dispatcher.invoke(
            "logsense_create_case",
            {"caseId": case_id, "title": title, "createdAt": created_at},
        )
        return result

    @server.tool(name="logsense_list_cases")
    def list_cases() -> list[dict[str, Any]]:
        """List local LogSense cases."""
        result: list[dict[str, Any]] = dispatcher.invoke("logsense_list_cases")
        return result

    @server.tool(name="logsense_import_evidence")
    def import_evidence(request: dict[str, Any]) -> dict[str, Any]:
        """Import immutable local evidence through the canonical preview/commit intake pipeline."""
        result: dict[str, Any] = dispatcher.invoke("logsense_import_evidence", request)
        return result

    @server.tool(name="logsense_analyze")
    def analyze(request: dict[str, Any]) -> dict[str, Any]:
        """Run the canonical deterministic analysis spine on an artifact request envelope."""
        result: dict[str, Any] = dispatcher.invoke("logsense_analyze", request)
        return result

    @server.tool(name="logsense_get_snapshot")
    def get_snapshot(analysis: dict[str, Any]) -> dict[str, Any]:
        """Read the immutable investigation snapshot from an existing analysis result."""
        result: dict[str, Any] = dispatcher.invoke("logsense_get_snapshot", {"analysis": analysis})
        return result

    @server.tool(name="logsense_get_findings")
    def get_findings(analysis: dict[str, Any]) -> dict[str, Any]:
        """Read bounded gaps, contradictions, cause evaluations, and evidence frontiers."""
        result: dict[str, Any] = dispatcher.invoke("logsense_get_findings", {"analysis": analysis})
        return result

    @server.tool(name="logsense_prepare_verification")
    def prepare_verification(request: dict[str, Any]) -> dict[str, Any]:
        """Analyze verification evidence into a new immutable snapshot without closing a frontier."""
        result: dict[str, Any] = dispatcher.invoke("logsense_prepare_verification", request)
        return result

    @server.tool(name="logsense_finalize_verification")
    def finalize_verification(request: dict[str, Any]) -> dict[str, Any]:
        """Evaluate frontier closure only through the canonical verification contract."""
        result: dict[str, Any] = dispatcher.invoke("logsense_finalize_verification", request)
        return result

    @server.tool(name="logsense_build_report")
    def build_report(analysis: dict[str, Any], rendered_at: str | None = None) -> dict[str, Any]:
        """Build the canonical deterministic report projection from an analysis result."""
        result: dict[str, Any] = dispatcher.invoke(
            "logsense_build_report",
            {"analysis": analysis, "renderedAt": rendered_at},
        )
        return result

    @server.tool(name="logsense_export_report_json")
    def export_report_json(analysis: dict[str, Any]) -> str:
        """Export the canonical report as stable JSON text."""
        result: str = dispatcher.invoke("logsense_export_report_json", {"analysis": analysis})
        return result

    @server.tool(name="logsense_investigator_tool")
    def investigator_tool(
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        analysis: dict[str, Any] | None = None,
        report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke one existing read-only investigator tool with its provenance boundary intact."""
        result: dict[str, Any] = dispatcher.invoke(
            "logsense_investigator_tool",
            {
                "toolName": tool_name,
                "arguments": arguments,
                "analysis": analysis,
                "report": report,
            },
        )
        return result

    return cast(MCPServerLike, server)


def run() -> None:
    """Run MCP over stdio by default or loopback Streamable HTTP when configured."""
    server = create_mcp_server()
    transport = os.getenv("LOGSENSE_MCP_TRANSPORT", "stdio").strip().lower()
    if transport == "stdio":
        server.run("stdio")
        return
    if transport == "streamable-http":
        server.run(
            "streamable-http",
            host=os.getenv("LOGSENSE_MCP_HOST", "127.0.0.1"),
            port=int(os.getenv("LOGSENSE_MCP_PORT", "8766")),
            streamable_http_path=os.getenv("LOGSENSE_MCP_PATH", "/mcp"),
            json_response=True,
        )
        return
    raise ValueError("LOGSENSE_MCP_TRANSPORT must be 'stdio' or 'streamable-http'")
