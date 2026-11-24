"""Der Feed einer Anzeige: alles, was der Bildschirm zum Zeichnen braucht, in einem Abruf.

Gebaut aus den Sichten der Module `starts` (Startliste, „am Stand“) und `ergebnisse`
(Ranglisten). Deren Namensregeln gelten: nie der volle Name, wenn die Person ihn nicht freigibt,
bei `hidden` nur die Startnummer (hier auch ohne Verein). Die Anzeige verschärft sie bei Bedarf
(`name_mode=short`, `show_club=false`), lockert sie aber nie.

Leere Szenen erscheinen nicht, sondern unter `skipped` mit Grund. Bleibt nichts übrig, kommt eine
Ruhe-Szene mit dem Turniernamen, damit der Bildschirm nie leer ist.

Uhrzeiten stehen als UTC-Zeitpunkt und zusätzlich in Ortszeit des Turniers (`*_local`,
`settings.timezone`). `reload_on` nennt genaue Ereignisnamen: die Muster aus
`defaults.RELOAD_EVENTS`, aufgelöst gegen die bekannten Namen des Servers.
"""

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import match_names
from app.core.localtime import DEFAULT_TIMEZONE, local_iso, zone, zone_of
from app.modules.anzeige import defaults
from app.modules.anzeige.models import Display
from app.modules.anzeige.procedure import build_procedure
from app.modules.anzeige.schemas import (
    DisplayConfig,
    FeedHeader,
    FeedIdleScene,
    FeedLane,
    FeedLiveRankingScene,
    FeedNextHeat,
    FeedNoticeScene,
    FeedOut,
    FeedPerson,
    FeedProcedure,
    FeedProcedureCurrent,
    FeedRange,
    FeedRangeScene,
    FeedRankGroup,
    FeedRanking,
    FeedRankRow,
    FeedScene,
    FeedSkipped,
    FeedStartlist,
    FeedStartlistScene,
    FeedUpcoming,
    FeedUpcomingQueue,
    FeedUpcomingQueued,
    FeedUpcomingSchedule,
    FeedUpcomingScheduled,
    FeedWarning,
    FeedWinnersScene,
    LiveRankingScene,
    NoticeScene,
    RangeScene,
    SceneKind,
    StartlistScene,
    WinnersScene,
)
from app.modules.anzeige.service import config_of
from app.modules.ergebnisse import begriffe
from app.modules.ergebnisse.ranking import competition_ranking
from app.modules.ergebnisse.schemas import RankingOut, RankingRow
from app.modules.ergebnisse.service import server_now
from app.modules.starts.schemas import LaneOut, RangeNowOut, StationStartOut
from app.modules.starts.views import queue_view, range_now, startlist
from app.modules.teilnehmer.names import abbreviate_name
from app.modules.turnier.models import Competition, Range, Tournament

OPEN_STATUSES = frozenset({"registered", "called"})
# Titel ohne eigenen Szenentitel. Die Ergebnisliste heißt nach dem Begriffssatz des Verbands
# ihres Wettbewerbs (`RankingOut.result_list_title`), die Startliste nach dem gemeinsamen Satz
# der gezeigten Wettbewerbe.
DEFAULT_TITLES: dict[str, str] = {
    "live_ranking": "Live-Wertung",
    "startlist": "Startliste",
    "winners": "Ergebnisliste",
}


@dataclass(frozen=True, slots=True)
class BackupInfo:
    """Was das Modul `backup` gerade meldet (oder nichts, wenn es nicht läuft)."""

    warning_code: str | None = None
    warning_message: str | None = None
    warn_on_display: bool = False


@dataclass(slots=True)
class Context:
    session: AsyncSession
    config: DisplayConfig
    tournament: Tournament | None
    # Grund, warum kein Turnier gezeigt wird.
    no_tournament: str | None
    competitions: list[Competition] = field(default_factory=list)
    ranges: dict[uuid.UUID, Range] = field(default_factory=dict)
    provisional: bool = False
    tz: ZoneInfo = field(default_factory=lambda: zone(DEFAULT_TIMEZONE))
    _startlist: list[StationStartOut] | None = None

    # --- Namen ---------------------------------------------------------------

    def name(self, display_name: str | None) -> str | None:
        if display_name is not None and self.config.name_mode == "short":
            return abbreviate_name(display_name)
        return display_name

    def club(self, display_name: str | None, club: str | None) -> str | None:
        """Ohne Namen (`hidden`) auch kein Verein: dann steht nur die Startnummer da."""
        if display_name is None or self.config.show_club is False:
            return None
        return club

    def code(self, competition_id: uuid.UUID) -> str | None:
        for competition in self.competitions:
            if competition.id == competition_id:
                return competition.catalog_code
        return None

    def federation(self, competition_id: uuid.UUID) -> str | None:
        for competition in self.competitions:
            if competition.id == competition_id:
                return begriffe.federation_of(competition)
        return None

    def person(self, start: StationStartOut) -> FeedPerson:
        terms = begriffe.terms_for(self.federation(start.competition_id))
        return FeedPerson(
            abort_label=begriffe.abort_label(start.abort_reason, terms)
            if start.status == "aborted"
            else None,
            start_id=start.start_id,
            start_number=start.start_number,
            display_name=self.name(start.display_name),
            club=self.club(start.display_name, start.club),
            class_short=start.class_short,
            competition_id=start.competition_id,
            competition_name=start.competition_name,
            competition_code=start.competition_code or self.code(start.competition_id),
            attempt=start.attempt,
            status=start.status,
            abort_reason=start.abort_reason,
            lane=start.lane,
            heat_number=start.heat_number,
            heat_starts_at=start.heat_starts_at,
            heat_starts_at_local=local_iso(start.heat_starts_at, self.tz),
        )

    async def all_starts(self) -> list[StationStartOut]:
        assert self.tournament is not None
        if self._startlist is None:
            self._startlist = await startlist(self.session, self.tournament.id, None, None)
        return self._startlist


@dataclass(slots=True)
class Pages:
    scenes: list[FeedScene] = field(default_factory=list)
    skipped: list[FeedSkipped] = field(default_factory=list)

    def skip(
        self, scene_id: str, kind: SceneKind, reason: str, competition_id: uuid.UUID | None = None
    ) -> None:
        self.skipped.append(
            FeedSkipped(scene_id=scene_id, kind=kind, reason=reason, competition_id=competition_id)
        )


# --- Turnier -----------------------------------------------------------------


async def _resolve_tournament(
    session: AsyncSession, tournament_id: uuid.UUID | None
) -> tuple[Tournament | None, str | None]:
    if tournament_id is not None:
        tournament = await session.get(Tournament, tournament_id)
        if tournament is not None:
            return tournament, None
    active = list(
        await session.scalars(select(Tournament).where(Tournament.status == "active").limit(2))
    )
    if len(active) == 1:
        return active[0], None
    if not active:
        return None, defaults.IDLE_NO_TOURNAMENT
    return None, defaults.IDLE_MANY_TOURNAMENTS


def _header(
    display: Display, tournament_id: uuid.UUID | None, tournament: Tournament | None
) -> FeedHeader:
    mode = "fixed" if tournament_id is not None else "auto"
    if tournament is None:
        return FeedHeader(
            tournament_id=None,
            title=display.name,
            organizer=None,
            date_from=None,
            date_to=None,
            tournament_status=None,
            tournament_mode=mode,
            timezone=DEFAULT_TIMEZONE,
        )
    return FeedHeader(
        tournament_id=tournament.id,
        title=tournament.name,
        organizer=tournament.organizer,
        date_from=tournament.date_from,
        date_to=tournament.date_to,
        tournament_status=tournament.status,  # type: ignore[arg-type]
        tournament_mode=mode,
        timezone=str(zone_of(tournament.settings)),
        is_practice=bool(tournament.is_practice),
    )


def _selected(
    context: Context, ids: Sequence[uuid.UUID], pages: Pages, scene_id: str, kind: SceneKind
) -> list[Competition]:
    """Gewählte Wettbewerbe in der Reihenfolge des Turniers; leer gewählt heißt alle."""
    if not ids:
        return context.competitions
    known = {competition.id for competition in context.competitions}
    for missing in [item for item in ids if item not in known]:
        pages.skip(scene_id, kind, "Der Wettbewerb gehört nicht zum gezeigten Turnier.", missing)
    wanted = set(ids)
    return [competition for competition in context.competitions if competition.id in wanted]


# --- Ranglisten --------------------------------------------------------------


def _aborted_score(row: RankingRow) -> tuple[str | None, list[Any]]:
    """Ergebnistext und Serien eines Starts für den Bildschirm.

    Abbruch mit Platz (Sporthandbuch K 1.14 / L 1.12): das gewertete Ergebnis wie bei allen.
    Nicht angetreten (dns): kein Wert, keine Serien – „0,00“ sähe aus wie ein Ergebnis.
    Sonst ohne Platz (Abbruch, disqualifiziert): die erfassten Serien bleiben, ein Gesamtwert
    nur, wenn alle Rohwerte erfasst sind; ein Teilergebnis wäre irreführend (bei „niedrigster
    Wert gewinnt“ sogar scheinbar das beste).
    """
    if row.abort_reason is None or row.place is not None:
        return row.score_text, list(row.series)
    if row.abort_reason == "dns":
        return None, []
    return (row.score_text if row.complete else None), list(row.series)


def _rank_row(context: Context, row: RankingRow) -> FeedRankRow:
    provisional = row.status == "provisional"
    if provisional:
        context.provisional = True
    score_text, series = _aborted_score(row)
    return FeedRankRow(
        place=row.place,
        tied=row.tied,
        group=row.group,
        start_id=row.start_id,
        start_number=row.start_number,
        attempt=row.attempt,
        display_name=context.name(row.display_name),
        club=context.club(row.display_name, row.club),
        class_short=row.class_short,
        score_text=score_text,
        complete=row.complete,
        series=series,
        status=row.status,
        running=row.status == "running",
        provisional=provisional,
        abort_reason=row.abort_reason,
        needs_shootoff=row.needs_shootoff,
        tie_reason=row.tie_reason,
        tie_criterion=row.tie_criterion,
        tie_unresolved=row.tie_unresolved,
        tie_note=row.tie_note,
        abort_label=row.abort_label,
        abort_note=row.abort_note,
    )


def _ranking(
    context: Context,
    ranking: RankingOut,
    class_ids: Sequence[uuid.UUID],
    limit: int,
    *,
    winners: bool = False,
    show_aborted: bool = False,
) -> FeedRanking:
    """Zeilen der Rangliste (`ergebnisse.ranking.competition_ranking`) für den Bildschirm.

    Plätze und Abbrüche entscheidet allein die Rangliste; hier wird nur gekürzt: Ergebnisliste
    bis Platz `limit`, Live-Wertung höchstens `limit` Zeilen. Ein Abbruch mit Platz steht wie
    jedes Ergebnis in `rows`. Abgebrochene ohne Platz kommen nur mit `show_aborted` aus der
    Rangliste, stehen in einer eigenen Liste `unplaced` (nie unter den Plätzen) und zählen nicht
    zu `limit`; andere Zeilen ohne Platz (prüfen) erscheinen nie.
    """
    wanted = set(class_ids)
    groups = []
    for group in ranking.groups:
        rows = group.rows
        if wanted:
            if group.class_id is None:
                rows = [row for row in rows if row.class_id in wanted]
            elif not wanted & set(group.class_ids):
                continue
        aborted = (
            [row for row in rows if row.abort_reason is not None and row.place is None]
            if show_aborted
            else []
        )
        if winners:
            shown = [
                row
                for row in rows
                if row.place is not None
                and row.place <= limit
                and (row.status in ("final", "provisional") or row.abort_reason is not None)
            ]
            more = 0
        else:
            # Ohne Platz und ohne Abbruchgrund (zu prüfen) gehört nicht auf die Anzeige.
            listed = [row for row in rows if row.group != "unranked"]
            shown = listed[:limit]
            more = max(len(listed) - limit, 0)
        if not shown and not aborted:
            continue
        groups.append(
            FeedRankGroup(
                class_id=group.class_id,
                class_name=group.class_name,
                class_short=group.class_short,
                rows=[_rank_row(context, row) for row in shown],
                more=more,
                unplaced=[_rank_row(context, row) for row in aborted],
            )
        )
    return FeedRanking(
        competition_id=ranking.competition_id,
        competition_name=ranking.competition_name,
        competition_code=ranking.competition_code,
        direction=ranking.direction,
        unit=ranking.unit,
        combined=ranking.combined,
        groups=groups,
        tie_word=ranking.tie_word,
        federation=ranking.federation,
    )


async def _live_ranking(context: Context, scene: LiveRankingScene, pages: Pages) -> None:
    assert context.tournament is not None
    found = False
    for competition in _selected(context, scene.competition_ids, pages, scene.id, scene.kind):
        ranking = await competition_ranking(
            context.session,
            context.tournament.id,
            competition.id,
            scope="live" if scene.show_running else "final",
            include_aborted=scene.show_aborted,
        )
        data = _ranking(
            context, ranking, scene.class_ids, scene.rows, show_aborted=scene.show_aborted
        )
        if not data.groups:
            if scene.competition_ids:
                pages.skip(
                    scene.id,
                    scene.kind,
                    f"Noch keine Ergebnisse in „{competition.name}“.",
                    competition.id,
                )
            continue
        found = True
        pages.scenes.append(
            FeedLiveRankingScene(
                kind="live_ranking",
                scene_id=scene.id,
                seconds=scene.seconds,
                title=scene.title or DEFAULT_TITLES[scene.kind],
                part=0,
                parts=0,
                ranking=data,
            )
        )
    if not found and not scene.competition_ids:
        pages.skip(scene.id, scene.kind, "Noch keine Ergebnisse.")


async def _winners(context: Context, scene: WinnersScene, pages: Pages) -> None:
    assert context.tournament is not None
    found = False
    for competition in _selected(context, scene.competition_ids, pages, scene.id, scene.kind):
        ranking = await competition_ranking(
            context.session,
            context.tournament.id,
            competition.id,
            scope="final",
            include_provisional=scene.include_provisional,
            include_aborted=scene.show_aborted,
        )
        data = _ranking(
            context,
            ranking,
            scene.class_ids,
            scene.top,
            winners=True,
            show_aborted=scene.show_aborted,
        )
        if not data.groups:
            if scene.competition_ids:
                pages.skip(
                    scene.id,
                    scene.kind,
                    f"Noch keine abgeschlossenen Ergebnisse in „{competition.name}“.",
                    competition.id,
                )
            continue
        found = True
        pages.scenes.append(
            FeedWinnersScene(
                kind="winners",
                scene_id=scene.id,
                seconds=scene.seconds,
                title=scene.title or ranking.result_list_title,
                part=0,
                parts=0,
                ranking=data,
            )
        )
    if not found and not scene.competition_ids:
        pages.skip(scene.id, scene.kind, "Noch keine abgeschlossenen Ergebnisse.")


# --- Startliste --------------------------------------------------------------


async def _startlist(context: Context, scene: StartlistScene, pages: Pages) -> None:
    competitions = _selected(context, scene.competition_ids, pages, scene.id, scene.kind)
    if scene.range_ids:
        if any(item not in context.ranges for item in scene.range_ids):
            pages.skip(scene.id, scene.kind, "Ein Schießstand gehört nicht zum gezeigten Turnier.")
        ranges = set(scene.range_ids)
        competitions = [c for c in competitions if c.range_id in ranges]
    by_competition: dict[uuid.UUID, list[StationStartOut]] = {}
    for start in await context.all_starts():
        if scene.include_finished or start.status in OPEN_STATUSES:
            by_competition.setdefault(start.competition_id, []).append(start)
    found = False
    for competition in competitions:
        starts = by_competition.get(competition.id, [])
        if not starts:
            if scene.competition_ids:
                pages.skip(
                    scene.id,
                    scene.kind,
                    f"In „{competition.name}“ sind keine Starts offen.",
                    competition.id,
                )
            continue
        found = True
        range_ = context.ranges.get(competition.range_id) if competition.range_id else None
        pages.scenes.append(
            FeedStartlistScene(
                kind="startlist",
                scene_id=scene.id,
                seconds=scene.seconds,
                title=scene.title or begriffe.terms_for(competition.catalog_federation).startliste,
                part=0,
                parts=0,
                startlist=FeedStartlist(
                    competition_id=competition.id,
                    competition_name=competition.name,
                    competition_code=competition.catalog_code,
                    range_id=competition.range_id,
                    range_name=range_.name if range_ else None,
                    starts=[context.person(start) for start in starts[: scene.rows]],
                    more=max(len(starts) - scene.rows, 0),
                    federation=begriffe.federation_of(competition),
                ),
            )
        )
    if not found and not scene.competition_ids:
        pages.skip(scene.id, scene.kind, "Keine offenen Starts.")


# --- Standanzeige ------------------------------------------------------------


def _current_positions(
    procedure: FeedProcedure, lanes: Sequence[LaneOut]
) -> list[FeedProcedureCurrent]:
    """Laufende Serie je belegter Bahn dieses Wettbewerbs.

    Aus dem Erfassungsfortschritt: erste noch nicht vollständige Serie des laufenden Abschnitts.
    Ohne Eingabe (gerade aufgerufen): erste Serie des ersten Abschnitts. Fertig erfasste Bahnen
    und Abschnitte, die der Ablauf nicht kennt, fehlen.
    """
    sections = {section.id: section for section in procedure.sections}
    current = []
    for lane in lanes:
        start = lane.start
        if start is None or start.competition_id != procedure.competition_id:
            continue
        progress = lane.progress
        if progress is None:
            if not procedure.sections:
                continue
            section_id, number = procedure.sections[0].id, 1
        else:
            if progress.complete or progress.section_id not in sections:
                continue
            section = sections[progress.section_id]
            section_id = section.id
            number = min(progress.series_done + 1, max(section.series_count, 1))
        current.append(
            FeedProcedureCurrent(
                lane=lane.lane, start_id=start.start_id, section_id=section_id, series_number=number
            )
        )
    return current


async def _busy(context: Context) -> dict[uuid.UUID, StationStartOut]:
    """Wer im Turnier gerade auf einer Bahn steht: Anmeldung → Start auf der Bahn."""
    return {start.entry_id: start for start in await context.all_starts() if start.on_lane}


def _upcoming_base(
    context: Context, start: StationStartOut, busy: dict[uuid.UUID, StationStartOut]
) -> dict[str, Any]:
    on_lane = busy.get(start.entry_id)
    busy_range = context.ranges.get(on_lane.range_id) if on_lane and on_lane.range_id else None
    return {
        "start_id": start.start_id,
        "start_number": start.start_number,
        "display_name": context.name(start.display_name),
        "club": context.club(start.display_name, start.club),
        "class_short": start.class_short,
        "attempt": start.attempt,
        "busy": on_lane is not None,
        "busy_range_id": on_lane.range_id if on_lane else None,
        "busy_range_name": busy_range.name if busy_range else None,
        "busy_lane": on_lane.lane if on_lane else None,
    }


def _by_competition(
    context: Context, starts: Sequence[StationStartOut]
) -> list[tuple[Competition, list[StationStartOut]]]:
    """Starts je Wettbewerb, Wettbewerbe in der Reihenfolge des Turniers."""
    grouped: dict[uuid.UUID, list[StationStartOut]] = {}
    for start in starts:
        grouped.setdefault(start.competition_id, []).append(start)
    return [
        (competition, grouped[competition.id])
        for competition in context.competitions
        if competition.id in grouped
    ]


async def _upcoming(
    context: Context,
    now: RangeNowOut,
    waiting: Sequence[StationStartOut],
    count: int,
) -> list[FeedUpcoming]:
    """„Als Nächstes“ je Wettbewerb: der nächste Durchgang (nur dessen Starts), dann die
    Reihenfolge. Wer gerade auf einer Bahn steht, bleibt sichtbar und ist gekennzeichnet."""
    if count <= 0:
        return []
    busy = await _busy(context)
    blocks: list[FeedUpcoming] = []
    heat = now.next_heat
    if heat is not None:
        for competition, starts in _by_competition(context, now.next_heat_starts):
            blocks.append(
                FeedUpcomingSchedule(
                    kind="schedule",
                    competition_id=competition.id,
                    competition_name=competition.name,
                    competition_code=competition.catalog_code,
                    more=max(len(starts) - count, 0),
                    heat_number=heat.number,
                    starts_at=heat.starts_at,
                    ends_at=heat.ends_at,
                    starts_at_local=local_iso(heat.starts_at, context.tz) or "",
                    ends_at_local=local_iso(heat.ends_at, context.tz) or "",
                    entries=[
                        FeedUpcomingScheduled(
                            **_upcoming_base(context, start, busy),
                            heat_number=heat.number,
                            starts_at=heat.starts_at,
                            starts_at_local=local_iso(heat.starts_at, context.tz) or "",
                            lane=start.lane or 0,
                        )
                        for start in starts[:count]
                    ],
                )
            )
    for competition, starts in _by_competition(context, waiting):
        blocks.append(
            FeedUpcomingQueue(
                kind="queue",
                competition_id=competition.id,
                competition_name=competition.name,
                competition_code=competition.catalog_code,
                more=max(len(starts) - count, 0),
                entries=[
                    FeedUpcomingQueued(
                        **_upcoming_base(context, start, busy),
                        position=start.queue_position or 0,
                    )
                    for start in starts[:count]
                ],
            )
        )
    return blocks


async def _range(context: Context, scene: RangeScene, pages: Pages) -> None:
    assert context.tournament is not None
    range_ = context.ranges.get(scene.range_id)
    if range_ is None:
        pages.skip(scene.id, scene.kind, "Der Schießstand gehört nicht zum gezeigten Turnier.")
        return
    now = await range_now(context.session, context.tournament.id, range_.id)
    upcoming = list(now.next_heat_starts)
    all_waiting = (await queue_view(context.session, context.tournament.id, range_.id)).waiting
    waiting = now.next_queue
    if scene.next_count > len(upcoming) + len(waiting):
        waiting = all_waiting
    candidates = upcoming + list(waiting)
    upcoming = candidates[: scene.next_count]
    on_lanes = [lane.start for lane in now.lanes if lane.start is not None]
    if not on_lanes and not candidates:
        pages.skip(scene.id, scene.kind, f"Auf „{range_.name}“ ist gerade nichts los.")
        return

    procedures = []
    if scene.show_procedure:
        by_id = {competition.id: competition for competition in context.competitions}
        running: list[uuid.UUID] = []
        for start in on_lanes or candidates[:1]:
            if start.competition_id not in running:
                running.append(start.competition_id)
        for competition_id in running:
            competition = by_id.get(competition_id)
            if competition is not None:
                procedure = build_procedure(competition)
                procedure.current = _current_positions(procedure, now.lanes)
                procedures.append(procedure)

    pages.scenes.append(
        FeedRangeScene(
            kind="range",
            scene_id=scene.id,
            seconds=scene.seconds,
            title=scene.title or range_.name,
            part=0,
            parts=0,
            range=FeedRange(
                range_id=range_.id,
                range_name=range_.name,
                lane_count=range_.lane_count,
                procedures=procedures,
                lanes=[
                    FeedLane(
                        lane=lane.lane,
                        start=context.person(lane.start) if lane.start is not None else None,
                        progress=lane.progress,
                    )
                    for lane in now.lanes
                ],
                upcoming=await _upcoming(context, now, all_waiting, scene.next_count),
                next_heat=(
                    FeedNextHeat(
                        number=now.next_heat.number,
                        starts_at=now.next_heat.starts_at,
                        ends_at=now.next_heat.ends_at,
                        starts_at_local=local_iso(now.next_heat.starts_at, context.tz) or "",
                        ends_at_local=local_iso(now.next_heat.ends_at, context.tz) or "",
                    )
                    if now.next_heat is not None
                    else None
                ),
                next=[context.person(start) for start in upcoming],
            ),
        )
    )


# --- Zusammenbau -------------------------------------------------------------


def _notice(scene: NoticeScene, pages: Pages) -> None:
    pages.scenes.append(
        FeedNoticeScene(
            kind="notice",
            scene_id=scene.id,
            seconds=scene.seconds,
            title=scene.title or scene.heading,
            part=0,
            parts=0,
            heading=scene.heading,
            text=scene.text,
        )
    )


def _number_parts(scenes: list[FeedScene]) -> None:
    totals: dict[str, int] = {}
    for scene in scenes:
        totals[scene.scene_id] = totals.get(scene.scene_id, 0) + 1
    seen: dict[str, int] = {}
    for scene in scenes:
        seen[scene.scene_id] = seen.get(scene.scene_id, 0) + 1
        scene.part = seen[scene.scene_id]
        scene.parts = totals[scene.scene_id]


def _idle(context: Context, header: FeedHeader) -> FeedIdleScene:
    if context.no_tournament is not None:
        text = context.no_tournament
    elif not context.config.scenes:
        text = defaults.IDLE_NO_SCENES
    else:
        text = defaults.IDLE_NOTHING_YET
    return FeedIdleScene(
        kind="idle",
        scene_id="ruhe",
        seconds=60,
        title=header.title,
        part=1,
        parts=1,
        heading=header.title,
        text=text,
    )


def _version(feed: FeedOut) -> str:
    content = feed.model_dump(mode="json", exclude={"version", "server_time"})
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]


_UNSET: Any = object()


async def build_feed(
    session: AsyncSession,
    display: Display,
    backup: BackupInfo,
    known_events: Sequence[str] = (),
    *,
    config: DisplayConfig | None = None,
    tournament_id: uuid.UUID | None = _UNSET,
) -> FeedOut:
    """Feed einer Anzeige. `config` und `tournament_id` ersetzen die gespeicherten Werte (für
    die Vorschau ungespeicherter Änderungen); `known_events` sind die bekannten Ereignisnamen
    des Servers, gegen die `reload_on` aufgelöst wird."""
    config = config if config is not None else config_of(display)
    if tournament_id is _UNSET:
        tournament_id = display.tournament_id
    tournament, no_tournament = await _resolve_tournament(session, tournament_id)
    context = Context(session, config, tournament, no_tournament)
    if tournament is not None:
        context.tz = zone_of(tournament.settings)
        context.competitions = list(
            await session.scalars(
                select(Competition)
                .where(Competition.tournament_id == tournament.id)
                .order_by(Competition.sort, Competition.name)
            )
        )
        context.ranges = {
            item.id: item
            for item in await session.scalars(
                select(Range).where(Range.tournament_id == tournament.id)
            )
        }
    header = _header(display, tournament_id, tournament)

    pages = Pages()
    for scene in config.scenes:
        if isinstance(scene, NoticeScene):
            _notice(scene, pages)
            continue
        if tournament is None:
            pages.skip(scene.id, scene.kind, no_tournament or defaults.IDLE_NO_TOURNAMENT)
            continue
        match scene:
            case LiveRankingScene():
                await _live_ranking(context, scene, pages)
            case WinnersScene():
                await _winners(context, scene, pages)
            case StartlistScene():
                await _startlist(context, scene, pages)
            case RangeScene():
                await _range(context, scene, pages)
    if not pages.scenes:
        pages.scenes.append(_idle(context, header))
    _number_parts(pages.scenes)

    warnings = []
    show_backup = (
        config.show_backup_warning
        if config.show_backup_warning is not None
        else backup.warn_on_display
    )
    if show_backup and backup.warning_code is not None:
        warnings.append(
            FeedWarning(code=f"backup_{backup.warning_code}", message=backup.warning_message or "")
        )
    if config.show_provisional_note and context.provisional:
        warnings.append(FeedWarning(code="provisional", message=defaults.PROVISIONAL_NOTE))

    now: datetime = await server_now(session)
    feed = FeedOut(
        display_id=display.id,
        display_name=display.name,
        version="",
        server_time=now,
        theme=config.theme,
        header=header,
        scenes=pages.scenes,
        skipped=pages.skipped,
        ticker=config.ticker or None,
        warnings=warnings,
        reload_on=match_names(defaults.RELOAD_EVENTS, known_events),
        poll_seconds=defaults.POLL_SECONDS,
    )
    feed.version = _version(feed)
    return feed
