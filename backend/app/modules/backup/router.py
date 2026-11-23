"""HTTP-Schnittstelle der Sicherung."""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.core.db import SessionDep
from app.core.security import Actor, require, require_paired
from app.modules.backup import service
from app.modules.backup.schemas import (
    BackupSettings,
    BackupStatusOut,
    BackupWarningOut,
    InitializeUsbIn,
    MaintenanceOut,
    PassphraseIn,
    PassphraseOut,
    RestoreExecuteIn,
    RestorePreviewIn,
    RestorePreviewOut,
    RestoreSourcesOut,
    RestoreStatusOut,
    RunOut,
    VerifyIn,
    VerifyOut,
)

if TYPE_CHECKING:
    from app.modules.backup.guided import RestoreManager

router = APIRouter(prefix="/backup", tags=["backup"])

RESTORE_PERMISSION = "backup.restore"


def _run_or_manage() -> Callable[[Request], Awaitable[Actor]]:
    """`backup.run`; `backup.manage` schließt es ein (Rollen, die nur das führen)."""
    run = require("backup.run")
    manage = require("backup.manage")

    async def dependency(request: Request) -> Actor:
        try:
            return await run(request)
        except HTTPException as exc:
            if exc.status_code != status.HTTP_403_FORBIDDEN:
                raise
            try:
                return await manage(request)
            except HTTPException:
                raise exc from None

    return dependency


async def _restore_actor(
    actor: Annotated[Actor, Depends(require(RESTORE_PERMISSION))],
) -> Actor:
    """`backup.restore`, und es muss eine Person angemeldet sein.

    Mit Berechtigungsprüfung trägt der Handelnde das geprüfte Recht; dann zählt nur eine
    Anmeldung mit PIN, nie die Standardrolle eines Geräts. Ohne Prüfung ist alles offen.
    """
    if RESTORE_PERMISSION in actor.permissions and actor.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Wiederherstellen darf nur ein angemeldeter Administrator (mit PIN).",
        )
    return actor


PAIRED = [Depends(require_paired())]
READ = [Depends(require("backup.read"))]
RUN = [Depends(_run_or_manage())]
MANAGE = [Depends(require("backup.manage"))]
RestoreActor = Annotated[Actor, Depends(_restore_actor)]
ERRORS = {
    status.HTTP_400_BAD_REQUEST: {"description": "Ungültige Eingabe"},
    status.HTTP_404_NOT_FOUND: {"description": "Nicht gefunden"},
    status.HTTP_409_CONFLICT: {"description": "Im aktuellen Zustand nicht möglich"},
}


def _service(request: Request) -> service.BackupService:
    return request.app.state.backup


def _restore(request: Request) -> RestoreManager:
    return request.app.state.backup_restore


ServiceDep = Annotated[service.BackupService, Depends(_service)]
# `guided` lädt die Ergebnis-Module; erst zur Laufzeit holen (zyklischer Import).
RestoreDep = Annotated[Any, Depends(_restore)]


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


@router.get(
    "/warning",
    summary="Warnung der Sicherung für alle Stationen",
    description=(
        "Für jedes gekoppelte Gerät lesbar, ohne bestimmtes Recht (auch die Standardrolle eines "
        "Geräts ohne angemeldete Person). Liefert nur die aktuelle Warnung in allgemeiner "
        "Fassung – ohne Pfade, Dateinamen oder Größen – und die Schalter, wo sie erscheinen "
        "soll. Neu laden beim Ereignis `backup.status` (das dieselben Daten mitbringt)."
    ),
    dependencies=PAIRED,
)
async def get_warning(backup: ServiceDep) -> BackupWarningOut:
    return backup.public_warning()


@router.post("/run", summary="Jetzt sichern", dependencies=RUN)
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


@router.post("/usb/recheck", summary="Stick erneut prüfen", dependencies=RUN)
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


# --- Geführte Wiederherstellung (nur Administrator mit PIN) ---------------------------


@router.get(
    "/maintenance",
    summary="Wartungszustand (während einer Wiederherstellung)",
    description=(
        "Für jedes gekoppelte Gerät. Während der Wartung beantwortet der Server schreibende "
        "Anfragen mit 503 und `code: maintenance`; während des Tauschs der Datenbank (wenige "
        "Sekunden, `exclusive`) auch lesende. Änderungen meldet das Ereignis `backup.maintenance`."
    ),
    dependencies=PAIRED,
)
async def get_maintenance(request: Request) -> MaintenanceOut:
    return MaintenanceOut.model_validate(request.app.state.maintenance.snapshot())


@router.get(
    "/restore/sources",
    summary="Wiederherstellbare Sicherungen auf Server und Stick, neueste zuerst",
    responses=ERRORS,
)
async def restore_sources(restore: RestoreDep, _actor: RestoreActor) -> RestoreSourcesOut:
    return await restore.list_sources()


@router.post(
    "/restore/preview",
    summary="Sicherung prüfen und Vorschau der Wiederherstellung (ändert nichts)",
    description=(
        "Prüft Prüfsumme und Passwort, liest den Abzug und vergleicht ihn mit dem jetzigen "
        "Stand. `restorable` ist false, wenn `problems` etwas nennt. `confirm` gehört in "
        "`POST /backup/restore/execute`."
    ),
    responses=ERRORS,
)
async def restore_preview(
    restore: RestoreDep, actor: RestoreActor, body: RestorePreviewIn
) -> RestorePreviewOut:
    try:
        return await restore.preview(body, actor)
    except service.BackupError as exc:
        raise _http(exc) from exc


@router.post(
    "/restore/execute",
    summary="Wiederherstellung starten (Hintergrundauftrag)",
    description=(
        "Startet die Wiederherstellung und antwortet sofort mit dem Status (202). Fortschritt "
        "unter `GET /backup/restore/status` und als Ereignis `backup.restore`. Es läuft immer "
        "nur eine Wiederherstellung."
    ),
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERRORS,
)
async def restore_execute(
    restore: RestoreDep, actor: RestoreActor, body: RestoreExecuteIn
) -> RestoreStatusOut:
    try:
        return await restore.execute(body, actor)
    except service.BackupError as exc:
        raise _http(exc) from exc


@router.get("/restore/status", summary="Fortschritt und Ergebnis der Wiederherstellung")
async def restore_status(restore: RestoreDep, _actor: RestoreActor) -> RestoreStatusOut:
    return restore.status()
