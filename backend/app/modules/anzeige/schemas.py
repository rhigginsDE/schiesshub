"""Ein- und Ausgabeformate des Moduls `anzeige`. Feldnamen englisch.

`DisplayConfig` ist der Inhalt der Spalte `display.config`: geordnete Szenen und globale
Einstellungen. Eingaben sind streng: unbekannte Szenenarten und Optionen sind Fehler.

Der Feed (`FeedOut`) enthält alles, was ein Bildschirm zum Zeichnen braucht. Texte, die aus dem
Server kommen und auf dem Bildschirm erscheinen, sind deutsch.
"""

from datetime import date, datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.ergebnisse.schemas import RowStatus, SeriesPart
from app.modules.starts.rules import AbortReason, StartStatus
from app.modules.turnier.schemas import Id, StrictModel

DisplayName = Annotated[str, Field(min_length=1, max_length=80)]
SceneId = Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", min_length=1, max_length=60)]
# Anzeigedauer einer Szene, bevor die nächste kommt.
Seconds = Annotated[int, Field(ge=5, le=600)]
Title = Annotated[str, Field(min_length=1, max_length=120)]
IdList = Annotated[list[Id], Field(max_length=100)]
Sort = Annotated[int, Field(ge=0)]

SceneKind = Literal["live_ranking", "startlist", "winners", "range", "notice"]
NameMode = Literal["as_person", "short"]
Theme = Literal["dark", "light"]

MIN_SECONDS = 5
MAX_SECONDS = 600


def _unique(values: list[Any], what: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{what} ist mehrfach angegeben.")


# --- Szenen ------------------------------------------------------------------


class SceneBase(StrictModel):
    id: SceneId
    seconds: Seconds = 20
    # Eigene Überschrift; ohne Angabe nennt der Feed eine passende (z. B. den Wettbewerb).
    title: Title | None = None


class LiveRankingScene(SceneBase):
    """Live-Wertung. Ohne `competition_ids`: alle Wettbewerbe mit Ergebnissen, nacheinander."""

    kind: Literal["live_ranking"]
    competition_ids: IdList = Field(default_factory=list)
    # Nur diese Klassen; leer = alle.
    class_ids: IdList = Field(default_factory=list)
    # Höchstens so viele Zeilen je Wertungsgruppe (Klasse).
    rows: Annotated[int, Field(ge=1, le=50)] = 10
    # Laufende Zwischenstände (aufgerufen/erfasst, noch nicht abgeschlossen) zeigen.
    show_running: bool = True

    @model_validator(mode="after")
    def _check(self) -> Self:
        _unique(self.competition_ids, "Ein Wettbewerb")
        _unique(self.class_ids, "Eine Klasse")
        return self


class StartlistScene(SceneBase):
    """Startliste je Wettbewerb. Ohne Filter: alle Wettbewerbe mit offenen Starts."""

    kind: Literal["startlist"]
    competition_ids: IdList = Field(default_factory=list)
    range_ids: IdList = Field(default_factory=list)
    # Höchstens so viele Starts je Wettbewerb; der Rest wird als Anzahl gemeldet.
    rows: Annotated[int, Field(ge=1, le=50)] = 12
    # Auch erfasste, abgeschlossene und abgebrochene Starts zeigen (Standard: nur offene).
    include_finished: bool = False

    @model_validator(mode="after")
    def _check(self) -> Self:
        _unique(self.competition_ids, "Ein Wettbewerb")
        _unique(self.range_ids, "Ein Stand")
        return self


class WinnersScene(SceneBase):
    """Siegerliste: nur abgeschlossene Ergebnisse, die ersten `top` Plätze je Klasse."""

    kind: Literal["winners"]
    competition_ids: IdList = Field(default_factory=list)
    class_ids: IdList = Field(default_factory=list)
    top: Annotated[int, Field(ge=1, le=20)] = 3
    # Ergebnisse in der Einspruchsfrist mitzeigen (gekennzeichnet als vorläufig).
    include_provisional: bool = True

    @model_validator(mode="after")
    def _check(self) -> Self:
        _unique(self.competition_ids, "Ein Wettbewerb")
        _unique(self.class_ids, "Eine Klasse")
        return self


class RangeScene(SceneBase):
    """Standanzeige für einen Stand: laufende Disziplin mit Ablauf, „Am Stand“, „Als Nächstes“."""

    kind: Literal["range"]
    range_id: Id
    # So viele Starter unter „Als Nächstes“.
    next_count: Annotated[int, Field(ge=0, le=30)] = 4
    # Ablauf (Abschnitte, Serien, Positionen) der laufenden Disziplin zeigen.
    show_procedure: bool = True


class NoticeScene(SceneBase):
    """Freier Hinweis, z. B. „Siegerehrung um 15:30 Uhr“."""

    kind: Literal["notice"]
    heading: Title
    text: Annotated[str, Field(max_length=2000)] = ""


Scene = Annotated[
    LiveRankingScene | StartlistScene | WinnersScene | RangeScene | NoticeScene,
    Field(discriminator="kind"),
]


class DisplayConfig(StrictModel):
    """Alles, was eine Anzeige zeigt und wie. Standardwerte: `defaults.DEFAULT_CONFIG`."""

    # Nacheinander gezeigt; eine einzelne Szene steht still.
    scenes: Annotated[list[Scene], Field(max_length=30)] = Field(default_factory=list)
    # as_person: Einstellung der Person; short: alle abgekürzt. Nie voller als die Person will.
    name_mode: NameMode = "as_person"
    # false: nie; true/as_person: nur bei Personen, die `show_club` gewählt haben.
    show_club: bool | Literal["as_person"] = "as_person"
    # Laufzeile am unteren Rand; leer = keine.
    ticker: Annotated[str, Field(max_length=500)] | None = None
    # Warnung „Sicherungs-Stick fehlt“ auf dieser Anzeige; null = Einstellung der Sicherung
    # (`warn_on_display`, Standard aus).
    show_backup_warning: bool | None = None
    # Hinweis „Ergebnisse vorläufig“, solange gezeigte Ergebnisse in der Einspruchsfrist sind.
    show_provisional_note: bool = True
    theme: Theme = "dark"

    @model_validator(mode="after")
    def _check(self) -> Self:
        ids = [scene.id for scene in self.scenes]
        duplicates = sorted({scene_id for scene_id in ids if ids.count(scene_id) > 1})
        if duplicates:
            raise ValueError(f"Szenen-ID mehrfach vergeben: {', '.join(duplicates)}.")
        return self


# --- Verwaltung --------------------------------------------------------------


class DisplayCreate(StrictModel):
    name: DisplayName
    # Ohne Angabe: automatisch das aktive Turnier.
    tournament_id: Id | None = None
    # Ohne Angabe: die Standardszenen (Live-Wertung und Startliste).
    config: DisplayConfig | None = None
    # Ohne Angabe: ans Ende.
    sort: Sort | None = None


class DisplayUpdate(StrictModel):
    name: DisplayName | None = None
    # null: automatisch das aktive Turnier.
    tournament_id: Id | None = None
    sort: Sort | None = None


class DeviceAssign(StrictModel):
    device_id: Id


class SceneOrder(StrictModel):
    # Alle Szenen-IDs in der neuen Reihenfolge.
    ids: list[SceneId]


class DisplayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    tournament_id: UUID | None
    device_id: UUID | None
    config: DisplayConfig
    sort: int
    created_at: datetime
    updated_at: datetime


# --- Feed: Bausteine ---------------------------------------------------------


class FeedHeader(BaseModel):
    tournament_id: UUID | None
    # Turniername; ohne Turnier der Name der Anzeige.
    title: str
    organizer: str | None
    date_from: date | None
    date_to: date | None
    tournament_status: Literal["draft", "active", "closed"] | None
    # fixed: an der Anzeige gewählt; auto: das einzige aktive Turnier.
    tournament_mode: Literal["fixed", "auto"]


class FeedWarning(BaseModel):
    # backup_<code der Sicherung> oder provisional.
    code: str
    message: str


class FeedPerson(BaseModel):
    """Eine Person, wie sie auf dieser Anzeige erscheint. Ohne Namen: nur die Startnummer."""

    start_id: UUID
    start_number: int
    display_name: str | None
    club: str | None
    class_short: str
    competition_id: UUID
    competition_name: str
    attempt: int
    status: StartStatus
    lane: int | None
    heat_number: int | None
    heat_starts_at: datetime | None


class FeedRankRow(BaseModel):
    place: int | None
    tied: bool
    # ranked: regulär; last: unvollständig oder aufgegeben; unranked: ohne Platz.
    group: Literal["ranked", "last", "unranked"]
    start_id: UUID
    start_number: int
    attempt: int
    display_name: str | None
    club: str | None
    class_short: str
    score_text: str | None
    complete: bool
    series: list[SeriesPart]
    status: RowStatus
    # Laufender Zwischenstand (noch nicht abgeschlossen).
    running: bool
    provisional: bool
    abort_reason: AbortReason | None


class FeedRankGroup(BaseModel):
    class_id: UUID | None
    # null bei gemeinsamer Wertung.
    class_name: str | None
    class_short: str | None
    rows: list[FeedRankRow]
    # Zeilen, die wegen der Zeilenzahl nicht gezeigt werden.
    more: int


class FeedRanking(BaseModel):
    competition_id: UUID
    competition_name: str
    # Richtung und Einheit der Wertung (aus der Rangliste), null ohne Ergebnis.
    direction: str | None
    unit: str | None
    combined: bool
    groups: list[FeedRankGroup]


class FeedStartlist(BaseModel):
    competition_id: UUID
    competition_name: str
    range_id: UUID | None
    range_name: str | None
    starts: list[FeedPerson]
    more: int


class FeedStance(BaseModel):
    haltung: Literal["stehend", "kniend", "liegend"]
    hand: Literal["beidhaendig", "einhaendig", "starke_hand", "schwache_hand"] | None
    # „kniend, beidhändig“
    text: str


class FeedPosition(BaseModel):
    nr: int
    distance_m: float | None
    # Erlaubte Alternativen (oder).
    stances: list[FeedStance]
    # n-te Scheibe von links.
    target: int | None
    # „kniend, beidhändig oder stehend, nur schwache Hand“
    text: str


class FeedSeriesStep(BaseModel):
    number: int
    # false: gestrichen (über `serien_gewertet` hinaus), wird geschossen, zählt aber nicht.
    counted: bool
    shots: int | None
    time_s: float | None
    distance_m: float | None
    position: FeedPosition | None
    # Nach dieser Serie ist Trefferaufnahme.
    hit_review_after: bool


class FeedSection(BaseModel):
    id: str
    name: str
    series_count: int
    # null: alle Serien zählen.
    counted_series: int | None
    shots_per_series: int | None
    time_per_series_s: float | None
    target_time_s: float | None
    time_measured: bool
    # Kurzbeschreibung, z. B. „2 Serien · je 5 Schuss · je 150 s“.
    summary: str
    # Abweichungen vom Sporthandbuch in diesem Abschnitt (Texte).
    deviations: list[str]
    series: list[FeedSeriesStep]


class FeedProcedure(BaseModel):
    competition_id: UUID
    competition_name: str
    catalog_code: str | None
    variant_name: str
    description: str | None
    # Wertung in Worten, z. B. „Ringe, höher ist besser“.
    scoring: str
    # Zusätzliche Regeln in Worten, z. B. „−1 Ring je volle Sekunde über der Sollzeit“.
    notes: list[str]
    # Kennzeichen „abweichend vom Sporthandbuch“ und alle Abweichungen als Text.
    deviates: bool
    deviations: list[str]
    sections: list[FeedSection]


class FeedLane(BaseModel):
    lane: int
    start: FeedPerson | None


class FeedNextHeat(BaseModel):
    number: int
    starts_at: datetime
    ends_at: datetime


class FeedRange(BaseModel):
    range_id: UUID
    range_name: str
    lane_count: int
    # Laufende Disziplin(en): aus den Starts am Stand, sonst aus den nächsten Starts.
    procedures: list[FeedProcedure]
    lanes: list[FeedLane]
    next_heat: FeedNextHeat | None
    next: list[FeedPerson]


# --- Feed: Szenen ------------------------------------------------------------


class FeedSceneBase(BaseModel):
    scene_id: str
    seconds: int
    title: str
    # Eine Szene kann mehrere Seiten ergeben (z. B. ein Wettbewerb je Seite): 1 … parts.
    part: int
    parts: int


class FeedLiveRankingScene(FeedSceneBase):
    kind: Literal["live_ranking"]
    ranking: FeedRanking


class FeedStartlistScene(FeedSceneBase):
    kind: Literal["startlist"]
    startlist: FeedStartlist


class FeedWinnersScene(FeedSceneBase):
    kind: Literal["winners"]
    ranking: FeedRanking


class FeedRangeScene(FeedSceneBase):
    kind: Literal["range"]
    range: FeedRange


class FeedNoticeScene(FeedSceneBase):
    kind: Literal["notice"]
    heading: str
    text: str


class FeedIdleScene(FeedSceneBase):
    """Ruhe-Szene, wenn keine Szene etwas zu zeigen hat."""

    kind: Literal["idle"]
    heading: str
    text: str


FeedScene = Annotated[
    FeedLiveRankingScene
    | FeedStartlistScene
    | FeedWinnersScene
    | FeedRangeScene
    | FeedNoticeScene
    | FeedIdleScene,
    Field(discriminator="kind"),
]


class FeedSkipped(BaseModel):
    scene_id: str
    kind: SceneKind
    # Warum nichts gezeigt wird, z. B. „Noch keine Ergebnisse“.
    reason: str
    # Betroffener Wettbewerb, wenn nur ein Teil der Szene leer ist.
    competition_id: UUID | None = None


class FeedOut(BaseModel):
    display_id: UUID
    display_name: str
    # Ändert sich nur, wenn sich der Inhalt ändert (ohne `server_time`); auch als ETag.
    version: str
    server_time: datetime
    theme: Theme
    header: FeedHeader
    # In dieser Reihenfolge zeigen, jede Seite `seconds` lang; nie leer.
    scenes: list[FeedScene]
    skipped: list[FeedSkipped]
    ticker: str | None
    warnings: list[FeedWarning]
    # Bei diesen Server-Ereignissen neu laden (`*` am Ende: alle mit diesem Anfang).
    reload_on: list[str]
    # Zusätzlich spätestens nach so vielen Sekunden neu laden (z. B. Ablauf der Einspruchsfrist).
    poll_seconds: int
