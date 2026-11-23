"""Mitschrift einspielen: Ergebnis-Ereignisse, die nach dem Abzug entstanden, nachtragen.

Die Mitschrift (`.shbj` auf dem Stick, `.ndjson` auf dem Server) enthält jedes Ergebnis-Ereignis
mit seiner Kennung, Start, Anmeldung, Wettbewerb, laufender Nummer, Art, Rohwerten, Grund,
Person/Gerät und Zeitpunkt (`app.modules.ergebnisse.journal.event_record`). Nicht darin stehen
Personen, Anmeldungen, Starts, Durchgänge, Bahnen, Aufrufe und Änderungen an Turnier oder
Wertung. Daraus folgt, was sich sicher nachtragen lässt:

- Ereignisse zu Starts, die es in der wiederhergestellten Datenbank gibt, in lückenloser Folge
  hinter dem letzten vorhandenen Ereignis. Die Kennung bleibt dieselbe; ein zweiter Lauf erkennt
  sie und trägt nichts doppelt ein.
- Starts, die erst nach dem Abzug gebucht wurden, fehlen in der Datenbank: Ihre Ereignisse werden
  übersprungen und am Ende mit Startnummer aufgelistet.
- Passt die Mitschrift nicht zur Datenbank (Lücke, gleiche Nummer mit anderem Inhalt, anderer
  Wettbewerb, Statuswechsel nicht erlaubt), bleibt dieser Start unverändert und wird gemeldet.

`result_event` bekommt nur neue Zeilen (der Trigger der Datenbank verbietet Ändern und Löschen).
Den Status des Starts zieht `starts.lifecycle.transition` nach wie beim Erfassen;
`result_current` baut `ergebnisse.recompute.recompute_competition` aus allen Ereignissen neu auf.
Alles läuft in einer Transaktion: entweder ist das Nachtragen vollständig bestätigt oder gar nicht.
"""

import json
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.db import SessionFactory
from app.core.errors import ConflictError
from app.core.security import Actor
from app.modules.backup import journal
from app.modules.ergebnisse.journal import RECORD_KIND
from app.modules.ergebnisse.models import ResultEvent
from app.modules.ergebnisse.recompute import recompute_competition
from app.modules.starts.lifecycle import transition
from app.modules.starts.models import Start
from app.modules.starts.rules import StartStatus
from app.modules.turnier.models import Competition

TRIGGER = "journal"
LIST_LIMIT = 20
_REQUIRED = (
    "event_id",
    "start_id",
    "entry_id",
    "competition_id",
    "seq",
    "type",
    "payload",
    "created_at",
)
_TYPES = frozenset({"raw_set", "finalized", "corrected", "reopened", "aborted"})


class JournalFormatError(Exception):
    """Ein Eintrag der Mitschrift ist unvollständig. Die Meldung ist für Anwender gedacht."""


# --- Lesen --------------------------------------------------------------------------


def journal_files(path: Path) -> list[Path]:
    """Eine Datei oder alle Mitschriften eines Verzeichnisses (`.shbj`, `.ndjson`), sortiert."""
    if not path.is_dir():
        return [path]
    return sorted(
        file
        for pattern in (f"*{journal.USB_ENCRYPTED_SUFFIX}", f"*{journal.SEGMENT_SUFFIX}")
        for file in path.glob(pattern)
        if file.is_file()
    )


def load_journal(path: Path, passphrase: str | None) -> list[journal.JournalEntry]:
    return journal.read_journal_file(path, passphrase)


def _record(entry: journal.JournalEntry) -> dict[str, Any]:
    record = json.loads(entry.line)["record"]
    assert isinstance(record, dict)  # parse_line hat das geprüft
    return record


def result_records(entries: Iterable[journal.JournalEntry]) -> list[dict[str, Any]]:
    """Die Ergebnis-Ereignisse der Mitschrift, jede Kennung einmal (Reihenfolge der Mitschrift)."""
    seen: set[str] = set()
    records = []
    for entry in entries:
        record = _record(entry)
        if record.get("kind") != RECORD_KIND:
            continue
        missing = [name for name in _REQUIRED if record.get(name) is None]
        if missing or record["type"] not in _TYPES:
            raise JournalFormatError(
                f"Eintrag {entry.seq} der Mitschrift ist unvollständig "
                f"({', '.join(missing) or 'unbekannte Art'})."
            )
        if record["event_id"] in seen:
            continue
        seen.add(record["event_id"])
        records.append(record)
    return records


def other_kinds(entries: Iterable[journal.JournalEntry]) -> int:
    """Einträge, die keine Ergebnis-Ereignisse sind (werden nicht eingespielt)."""
    return sum(1 for entry in entries if _record(entry).get("kind") != RECORD_KIND)


# --- Bericht ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MissingStart:
    start_id: str
    competition_id: str
    start_number: int | None
    attempt: int | None
    events: int
    # Kennziffer und Name, wenn der Wettbewerb in der Sicherung steht; sonst None.
    competition: str | None = None

    def label(self) -> str:
        number = f"Startnummer {self.start_number}" if self.start_number else "ohne Startnummer"
        attempt = f"{self.attempt}. Start, " if self.attempt else ""
        unit = "Ereignis" if self.events == 1 else "Ereignisse"
        return f"{number} ({attempt}{self.events} {unit})"

    def where(self) -> str:
        if self.competition is not None:
            return self.competition
        return f"Wettbewerb, der in der Sicherung fehlt ({self.competition_id[:8]})"


@dataclass(slots=True)
class ApplyReport:
    applied: int = 0
    present: int = 0
    missing_starts: list[MissingStart] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    status_changes: int = 0
    recomputed_competitions: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def missing_events(self) -> int:
        return sum(item.events for item in self.missing_starts)

    @property
    def complete(self) -> bool:
        return not self.missing_starts and not self.conflicts

    def summary(self) -> list[str]:
        first = (
            f"{self.applied} Ereignisse nachgetragen, {self.present} waren schon in der "
            f"Sicherung, {self.missing_events} übersprungen, weil der Start in der Sicherung fehlt"
        )
        lines = [first + (":" if self.missing_starts else ".")]
        groups: dict[str, list[MissingStart]] = defaultdict(list)
        for item in self.missing_starts:
            groups[item.where()].append(item)
        for where, items in list(groups.items())[:LIST_LIMIT]:
            labels = [item.label() for item in items[:LIST_LIMIT]]
            if len(items) > LIST_LIMIT:
                labels.append(f"und {len(items) - LIST_LIMIT} weitere")
            lines.append(f"  - {where}: " + ", ".join(labels))
        if len(groups) > LIST_LIMIT:
            lines.append(f"  - und {len(groups) - LIST_LIMIT} weitere Wettbewerbe")
        if self.conflicts:
            lines.append(
                f"{len(self.conflicts)} Start(s) nicht nachgetragen, weil die Mitschrift nicht zur "
                "Datenbank passt:"
            )
            lines.extend(f"  - {text}" for text in self.conflicts)
        lines.append(
            f"Start-Status nachgezogen: {self.status_changes}; Ergebnisse neu berechnet in "
            f"{self.recomputed_competitions} Wettbewerb(en)."
        )
        lines.extend(self.notes)
        if self.missing_starts:
            lines.append(
                "Diese Starts wurden nach der Sicherung gebucht. Die Mitschrift enthält weder "
                "Person noch Anmeldung; bitte Person und Start neu anlegen und das Ergebnis vom "
                "Startzettel erfassen."
            )
        return lines


# --- Vorab rechnen (ohne Datenbank) ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BackupStart:
    """Was die Planung von einem Start der Sicherung braucht."""

    entry_id: str
    competition_id: str
    # Ereignis-Kennung -> laufende Nummer, wie sie in der Sicherung stehen.
    events: dict[str, int]


@dataclass(slots=True)
class ApplyPlan:
    """Was `apply_records` mit diesen Ereignissen voraussichtlich tun würde.

    Dieselben Regeln wie beim Einspielen: Zuordnung zu Anmeldung und Wettbewerb, lückenlose
    Nummern, gleiche Nummer bei gleicher Kennung. Nicht vorab erkennbar ist nur, ob sich der
    Status eines Starts nachziehen lässt; das meldet erst das Einspielen.
    """

    applied: set[str] = field(default_factory=set)
    present: int = 0
    missing_start_events: set[str] = field(default_factory=set)
    conflict_events: set[str] = field(default_factory=set)


def plan_records(records: list[dict[str, Any]], starts: dict[str, BackupStart]) -> ApplyPlan:
    plan = ApplyPlan()
    by_start: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_start[record["start_id"]].append(record)
    for start_id, items in by_start.items():
        items.sort(key=lambda record: record["seq"])
        ids = {str(record["event_id"]) for record in items}
        start = starts.get(start_id)
        if start is None:
            plan.missing_start_events |= ids
            continue
        first = items[0]
        if start.entry_id != first["entry_id"] or start.competition_id != first["competition_id"]:
            plan.conflict_events |= ids - set(start.events)
            continue
        last = max(start.events.values(), default=0)
        new: set[str] = set()
        present = 0
        ok = True
        for record in items:
            event_id = str(record["event_id"])
            if event_id in start.events:
                if start.events[event_id] != record["seq"]:
                    ok = False
                    break
                present += 1
                continue
            if record["seq"] != last + 1:
                ok = False
                break
            new.add(event_id)
            last = record["seq"]
        plan.present += present
        if ok:
            plan.applied |= new
        else:
            plan.conflict_events |= ids - set(start.events)
    return plan


# --- Einspielen -----------------------------------------------------------------------


class _Skip(Exception):
    """Dieser Start passt nicht; seine Änderungen werden zurückgenommen."""


def _uuid(value: Any) -> uuid.UUID | None:
    return uuid.UUID(str(value)) if value else None


def _who(record: dict[str, Any]) -> str:
    number = record.get("start_number")
    attempt = record.get("attempt")
    text = f"Startnummer {number}" if number else f"Start {record['start_id']}"
    return f"{text} ({attempt}. Start)" if attempt else text


def _competition_label(competition: Competition | None) -> str | None:
    if competition is None:
        return None
    code = f"{competition.catalog_code} " if competition.catalog_code else ""
    return f"„{code}{competition.name}“"


def _target(status: str, record: dict[str, Any]) -> StartStatus | None:
    """Statuswechsel, den das Ereignis beim Erfassen ausgelöst hat (wie `ergebnisse.service`)."""
    kind = record["type"]
    if kind == "raw_set":
        return "captured" if status in ("registered", "called") else None
    if kind == "finalized":
        return "final"
    if kind == "reopened":
        return "captured"
    if kind == "aborted":
        return "aborted"
    return None  # corrected: bleibt abgeschlossen


async def _apply_start(
    session: Any, start: Start, records: list[dict[str, Any]], report: ApplyReport
) -> bool:
    """Trägt die fehlenden Ereignisse eines Starts nach. True, wenn etwas neu ist."""
    first = records[0]
    if (
        str(start.entry_id) != first["entry_id"]
        or str(start.competition_id) != (first["competition_id"])
    ):
        raise _Skip(
            f"{_who(first)}: gehört in der Datenbank zu einer anderen Anmeldung oder einem anderen "
            "Wettbewerb; nichts nachgetragen."
        )
    rows = (
        await session.execute(
            select(ResultEvent.id, ResultEvent.seq).where(ResultEvent.start_id == start.id)
        )
    ).all()
    existing = {row.id: row.seq for row in rows}
    last = max(existing.values(), default=0)
    new: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        event_id = uuid.UUID(record["event_id"])
        if event_id in existing:
            if existing[event_id] != record["seq"]:
                raise _Skip(
                    f"{_who(record)}: Ereignis {event_id} hat in der Datenbank eine andere Nummer; "
                    "nichts nachgetragen."
                )
            # Zählt auch, wenn der Start danach nicht passt: Diese Ereignisse sind ja da.
            report.present += 1
            continue
        remaining = len(records) - index
        if record["seq"] <= last:
            raise _Skip(
                f"{_who(record)}: Ereignis Nr. {record['seq']} gibt es in der Datenbank schon mit "
                f"anderem Inhalt; {remaining} Ereignis(se) nicht nachgetragen."
            )
        if record["seq"] != last + 1:
            raise _Skip(
                f"{_who(record)}: Lücke in der Mitschrift, Ereignis Nr. {last + 1} fehlt; "
                f"{remaining} Ereignis(se) nicht nachgetragen."
            )
        new.append(record)
        last = record["seq"]

    changes = 0
    for record in new:
        session.add(
            ResultEvent(
                id=uuid.UUID(record["event_id"]),
                start_id=start.id,
                seq=record["seq"],
                type=record["type"],
                payload=record["payload"],
                reason=record.get("reason"),
                user_id=_uuid(record.get("user_id")),
                device_id=_uuid(record.get("device_id")),
                created_at=datetime.fromisoformat(record["created_at"]),
            )
        )
        to = _target(start.status, record)
        if to is not None and to != start.status:
            actor = Actor(
                user_id=_uuid(record.get("user_id")), device_id=_uuid(record.get("device_id"))
            )
            abort_reason = record["payload"].get("abort_reason") if to == "aborted" else None
            try:
                await transition(
                    session,
                    start,
                    to,
                    actor,
                    reason=record.get("reason") if record["type"] == "reopened" else None,
                    abort_reason=abort_reason,
                )
            except ConflictError as exc:
                raise _Skip(
                    f"{_who(record)}: Status lässt sich nicht nachziehen ({exc.detail}); nichts "
                    "nachgetragen."
                ) from None
            changes += 1
    await session.flush()
    report.applied += len(new)
    report.status_changes += changes
    return bool(new)


async def apply_records(
    session_factory: SessionFactory, records: list[dict[str, Any]]
) -> ApplyReport:
    """Trägt die Ereignisse nach (idempotent) und bestätigt alles in einer Transaktion."""
    report = ApplyReport()
    by_start: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_start[record["start_id"]].append(record)
    ordered = sorted(by_start.values(), key=lambda items: min(r["created_at"] for r in items))

    touched: dict[uuid.UUID, int] = {}
    async with session_factory() as session, session.begin():
        for items in ordered:
            items.sort(key=lambda record: record["seq"])
            first = items[0]
            start = await session.scalar(
                select(Start).where(Start.id == uuid.UUID(first["start_id"])).with_for_update()
            )
            if start is None:
                competition = await session.get(Competition, uuid.UUID(first["competition_id"]))
                report.missing_starts.append(
                    MissingStart(
                        start_id=first["start_id"],
                        competition_id=first["competition_id"],
                        start_number=first.get("start_number"),
                        attempt=first.get("attempt"),
                        events=len(items),
                        competition=_competition_label(competition),
                    )
                )
                continue
            try:
                async with session.begin_nested():
                    changed = await _apply_start(session, start, items, report)
            except _Skip as skip:
                report.conflicts.append(str(skip))
                await session.refresh(start)
                continue
            if changed:
                revision = max(int(record.get("definition_revision") or 0) for record in items)
                touched[start.competition_id] = max(touched.get(start.competition_id, 0), revision)

        for competition_id, revision in touched.items():
            competition = await session.get(Competition, competition_id)
            assert competition is not None  # Fremdschlüssel des Starts
            await recompute_competition(session, competition_id, Actor(), trigger=TRIGGER)
            if revision > competition.definition_revision:
                report.notes.append(
                    f"Achtung: Die Wertung von „{competition.name}“ wurde nach der Sicherung "
                    f"geändert (Fassung {revision}, in der Sicherung "
                    f"{competition.definition_revision}). "
                    "Diese Änderung steht nicht in der Mitschrift; bitte im Turnier wiederholen, "
                    "die Ergebnisse werden dann neu berechnet."
                )
        report.recomputed_competitions = len(touched)
    report.missing_starts.sort(
        key=lambda item: (item.where(), item.start_number or 0, item.attempt or 0)
    )
    return report
