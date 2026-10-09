from __future__ import annotations

import os
import secrets
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse

from logsense.forensics.verification import VerificationContractError
from logsense.integrations.service import IntegrationRequestError, IntegrationService
from logsense.pipeline.intake import EvidenceIntakeError
from logsense.workspace.cases import CaseWorkspaceError


def _auth_dependency(expected_token: str | None) -> Callable[..., None]:
    def authorize(authorization: str | None = Header(default=None)) -> None:
        if not expected_token:
            return
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(token, expected_token):
            raise HTTPException(status_code=401, detail="invalid local API bearer token")

    return authorize


def create_app(
    *, service: IntegrationService | None = None, api_token: str | None = None
) -> FastAPI:
    """Create the canonical local API adapter.

    The adapter validates transport shape only. All forensic work is delegated
    to IntegrationService and the deterministic owners beneath it.
    """
    service = service or IntegrationService()
    token = api_token if api_token is not None else os.getenv("LOGSENSE_API_TOKEN")
    authorize = _auth_dependency(token)
    app = FastAPI(
        title="LogSense Local Integration API",
        version="1.0.0",
        description="Thin local transport over deterministic LogSense application services.",
    )

    @app.exception_handler(IntegrationRequestError)
    async def integration_error(_request: Any, exc: IntegrationRequestError) -> PlainTextResponse:
        return PlainTextResponse(str(exc), status_code=422)

    @app.exception_handler(EvidenceIntakeError)
    async def intake_error(_request: Any, exc: EvidenceIntakeError) -> PlainTextResponse:
        return PlainTextResponse(str(exc), status_code=422)

    @app.exception_handler(VerificationContractError)
    async def verification_error(_request: Any, exc: VerificationContractError) -> PlainTextResponse:
        return PlainTextResponse(str(exc), status_code=422)

    @app.exception_handler(CaseWorkspaceError)
    async def workspace_error(_request: Any, exc: CaseWorkspaceError) -> PlainTextResponse:
        return PlainTextResponse(str(exc), status_code=409)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "truthOwner": "DETERMINISTIC_LOGSENSE_CORE"}

    @app.get("/v1/capabilities", dependencies=[Depends(authorize)])
    def capabilities() -> dict[str, Any]:
        return service.capabilities()

    @app.get("/v1/cases", dependencies=[Depends(authorize)])
    def cases() -> list[dict[str, Any]]:
        return service.list_cases()

    @app.post("/v1/cases", dependencies=[Depends(authorize)])
    def create_case(payload: dict[str, Any]) -> dict[str, Any]:
        return service.create_case(
            case_id=str(payload.get("caseId") or ""),
            title=str(payload["title"]) if payload.get("title") is not None else None,
            created_at=str(payload["createdAt"]) if payload.get("createdAt") is not None else None,
        )

    @app.post("/v1/cases/{case_id}/evidence", dependencies=[Depends(authorize)])
    def import_evidence(case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = dict(payload)
        if request.get("caseId") not in (None, "", case_id):
            raise IntegrationRequestError("path case_id does not match payload caseId")
        request["caseId"] = case_id
        return service.import_evidence(request)

    @app.post("/v1/analysis", dependencies=[Depends(authorize)])
    def analyze(payload: dict[str, Any]) -> dict[str, Any]:
        return service.analyze(payload)

    @app.post("/v1/snapshots/from-analysis", dependencies=[Depends(authorize)])
    def snapshot(payload: dict[str, Any]) -> dict[str, Any]:
        return service.get_snapshot(payload)

    @app.post("/v1/findings/from-analysis", dependencies=[Depends(authorize)])
    def findings(payload: dict[str, Any]) -> dict[str, Any]:
        return service.get_findings(payload)

    @app.post("/v1/verification/prepare", dependencies=[Depends(authorize)])
    def prepare_verification(payload: dict[str, Any]) -> dict[str, Any]:
        return service.prepare_verification(payload)

    @app.post("/v1/verification/finalize", dependencies=[Depends(authorize)])
    def finalize_verification(payload: dict[str, Any]) -> dict[str, Any]:
        return service.finalize_verification(payload)

    @app.post("/v1/reports/from-analysis", dependencies=[Depends(authorize)])
    def report(payload: dict[str, Any]) -> dict[str, Any]:
        return service.build_report(payload)

    @app.post(
        "/v1/exports/report.json",
        dependencies=[Depends(authorize)],
        response_class=PlainTextResponse,
    )
    def export_report(payload: dict[str, Any]) -> str:
        return service.export_report_json(payload)

    @app.post("/v1/investigator/tools/{tool_name}", dependencies=[Depends(authorize)])
    def investigator_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        analysis = payload.get("analysis")
        report_value = payload.get("report")
        arguments = payload.get("arguments")
        for name, value in (
            ("analysis", analysis),
            ("report", report_value),
            ("arguments", arguments),
        ):
            if value is not None and not isinstance(value, Mapping):
                raise IntegrationRequestError(f"{name} must be an object")
        return service.invoke_investigator_tool(
            tool_name=tool_name,
            arguments=arguments,
            analysis=analysis,
            report=report_value,
        )

    return app


app = create_app()


def run() -> None:
    """Run the standalone API on loopback unless the operator explicitly changes host."""
    import uvicorn

    uvicorn.run(
        "logsense.integrations.api:app",
        host=os.getenv("LOGSENSE_API_HOST", "127.0.0.1"),
        port=int(os.getenv("LOGSENSE_API_PORT", "8765")),
        reload=False,
    )
