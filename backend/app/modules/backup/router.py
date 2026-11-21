"""HTTP-Schnittstelle der Sicherung."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.core.db import SessionDep
from app.core.security import require
from app.modules.backup import service
from app.modules.backup.schemas import (
    BackupSettings,
    BackupStatusOut,
    InitializeUsbIn,
    PassphraseIn,
    PassphraseOut,
    RunOut,
    VerifyIn,
    VerifyOut,
)

router = APIRouter(prefix="/backup", tags=["backup"])

READ = [Depends(require("backup.read"))]
MANAGE = [Depends(require("backup.manage"))]
ERRORS = {
    status.HTTP_400_BAD_REQUEST: {"description": "Ungültige Eingabe"},
    status.HTTP_404_NOT_FOUND: {"description": "Nicht gefunden"},
    status.HTTP_409_CONFLICT: {"description": "Im aktuellen Zustand nicht möglich"},
}


def _service(request: Request) -> service.BackupService:
    return request.app.state.backup


ServiceDep = Annotated[service.BackupService, Depends(_service)]


def _http(exc: service.BackupError) -> HTTPException:
    code = status.HTTP_400_BAD_REQUEST
    if isinstance(exc, service.NotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, service.ConflictError):
        code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=str(exc))


@router.get("/settings", summary="Einstellungen der Sicherung", dependencies=READ)
async def get_settings(backup: ServiceDep) -> BackupSettings:
    return backup.config


@router.put("/settings", summary="Einstellungen der Sicherung ändern", dependencies=MANAGE)
async def put_settings(backup: ServiceDep, body: BackupSettings) -> BackupSettings:
    return await backup.update_config(body)


@router.put(
    "/passphrase",
    summary="Sicherungspasswort setzen oder ändern",
    dependencies=MANAGE,
    responses=ERRORS,
)
async def put_passphrase(backup: ServiceDep, body: PassphraseIn) -> PassphraseOut:
    try:
        return await backup.set_passphrase(body.passphrase, body.current_passphrase)
    except service.BackupError as exc:
        raise _http(exc) from exc


@router.get("/status", summary="Zustand von Sicherung und Stick", dependencies=READ)
async def get_status(backup: ServiceDep) -> BackupStatusOut:
    return backup.status()


@router.post("/run", summary="Jetzt sichern", dependencies=MANAGE)
async def run_now(backup: ServiceDep) -> list[RunOut]:
    return await backup.run_snapshot()


@router.get("/runs", summary="Sicherungsläufe, neueste zuerst", dependencies=READ)
async def list_runs(
    backup: ServiceDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    kind: Literal["snapshot", "journal"] | None = None,
    target: Literal["local", "usb"] | None = None,
) -> list[RunOut]:
    return await backup.list_runs(session, limit, kind, target)


@router.post("/usb/recheck", summary="Stick erneut prüfen", dependencies=MANAGE)
async def recheck_usb(backup: ServiceDep) -> BackupStatusOut:
    return await backup.recheck_usb()


@router.post(
    "/usb/initialize",
    summary="Neuen Stick als Sicherungs-Stick einrichten (legt die Marker-Datei an)",
    dependencies=MANAGE,
    responses=ERRORS,
)
async def initialize_usb(backup: ServiceDep, body: InitializeUsbIn) -> BackupStatusOut:
    try:
        return await backup.initialize_usb()
    except service.BackupError as exc:
        raise _http(exc) from exc


@router.get(
    "/runs/{run_id}/download",
    summary="Lokalen Abzug verschlüsselt herunterladen",
    dependencies=MANAGE,
    responses=ERRORS,
    response_class=FileResponse,
)
async def download_run(backup: ServiceDep, session: SessionDep, run_id: UUID) -> FileResponse:
    try:
        path, file_name = await backup.build_download(session, run_id)
    except service.BackupError as exc:
        raise _http(exc) from exc
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=file_name,
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


@router.post(
    "/runs/{run_id}/verify",
    summary="Sicherung prüfen (entschlüsseln, Prüfsumme, Inhalt) – ohne Zurückspielen",
    dependencies=MANAGE,
    responses=ERRORS,
)
async def verify_run(
    backup: ServiceDep, session: SessionDep, run_id: UUID, body: VerifyIn
) -> VerifyOut:
    try:
        return await backup.verify(session, run_id, body.passphrase)
    except service.BackupError as exc:
        raise _http(exc) from exc
