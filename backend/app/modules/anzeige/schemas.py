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
from app.modules.starts.schemas import LaneProgressOut
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
    # Abgebrochene Starts (ohne Platz, mit Grund) am Ende jeder Klasse aufführen.
    show_aborted: bool = False

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
        _unique(self.range_ids, "Ein Schießstand")
        return self


class WinnersScene(SceneBase):
    """Ergebnisliste: nur abgeschlossene Ergebnisse (und Abbrüche mit Platz), die ersten `top`
    Plätze je Klasse. Der Schlüssel `winners` bleibt."""

    kind: Literal["winners"]
    competition_ids: IdList = Field(default_factory=list)
    class_ids: IdList = Field(default_factory=list)
    top: Annotated[int, Field(ge=1, le=20)] = 3
    # Ergebnisse in der Einspruchsfrist mitzeigen (gekennzeichnet als vorläufig).
    include_provisional: bool = True
    # Abgebrochene Starts (ohne Platz, mit Grund) nach den Plätzen aufführen.
    show_aborted: bool = False

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
    # Szenen und Einstellungen (ersetzt sie vollständig, wie `PUT …/config`). Zusammen mit
    # `tournament_id` werden die Szenen gegen das neue Turnier geprüft.
    config: DisplayConfig | None = None


class FeedPreviewRequest(StrictModel):
    """Feed für eine nicht gespeicherte Konfiguration (Vorschau in der Verwaltung)."""

    config: DisplayConfig
    # Ohne Angabe das Turnier der Anzeige; null: automatisch das aktive Turnier.
    tournament_id: Id | None = None


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
    # Ortszeit des Turniers (IANA-Name); die `*_local`-Felder im Feed stehen in dieser Zone.
    timezone: str
    # Übungsturnier (Kennzeichen „Übung“); false ohne Turnier.
    is_practice: bool = False


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
    # Kennziffer aus dem Katalog („4401“); null bei eigenen Wettbewerben.
    competition_code: str | None = None
    attempt: int
    status: StartStatus
    # Bei `status: aborted`: nicht angetreten (dns), aufgegeben (dnf), disqualifiziert (dsq).
    abort_reason: AbortReason | None = None
    # Fertiger Text zum Abbruchgrund nach dem Verband des Wettbewerbs („Abbruch (AB)“, „nicht
    # angetreten“, „disqualifiziert“); null, wenn der Start nicht abgebrochen ist.
    abort_label: str | None = None
    lane: int | None
    heat_number: int | None
    heat_starts_at: datetime | None
    # Dieselbe Uhrzeit in Ortszeit des Turniers, ISO 8601 mit Versatz („…T10:00:00+01:00“).
    heat_starts_at_local: str | None


class FeedRankRow(BaseModel):
    place: int | None
    tied: bool
    # ranked: regulär (auch ein Abbruch nach „Feuer“ mit Platz, Sporthandbuch K 1.14 / L 1.12);
    # last: unvollständig (live, hinten); unranked: ohne Platz (abgebrochen – dann mit
    # `abort_reason` – stehen sie in `FeedRankGroup.unplaced`).
    group: Literal["ranked", "last", "unranked"]
    start_id: UUID
    start_number: int
    attempt: int
    display_name: str | None
    club: str | None
    class_short: str
    # Ergebnis als Text. Abbruch mit Platz: das gewertete Ergebnis (nicht geschossene Serien
    # nach der Regel der Wertung). Ohne Platz: bei nicht angetreten (dns) immer null, bei
    # Abbruch oder disqualifiziert nur, wenn alle Rohwerte erfasst sind.
    score_text: str | None
    complete: bool
    series: list[SeriesPart]
    status: RowStatus
    # Laufender Zwischenstand (noch nicht abgeschlossen).
    running: bool
    provisional: bool
    abort_reason: AbortReason | None
    # Geteilter Platz, den ein Stechen entscheidet (`stechen_bis_platz`), und der Hinweis
    # zu einem offenen geteilten Platz („Ringgleichheit auf Platz 2: Stechen“), sonst null.
    needs_shootoff: bool = False
    # Warum ein Platz geteilt ist (wie `RankingRow.tie_reason`): missing_data, manual, shootoff,
    # max_score (Höchstergebnis, gleicher Platz nach Regel), resolved (im Ergebnis gleich, durch
    # die Gleichstandskette entschieden, nicht geteilt); null ohne gleiches Ergebnis bzw. wenn
    # alle Kriterien gerechnet und gleich sind.
    tie_reason: Literal["missing_data", "manual", "shootoff", "max_score", "resolved"] | None = None
    # ID des Kriteriums zu `tie_reason` (wie `RankingRow.tie_criterion`; Klartext in `tie_note`).
    tie_criterion: str | None = None
    # Geteilt und nicht entschieden (manual, missing_data, shootoff); false bei max_score
    # (gleicher Platz nach Regel) und ohne geteilten Platz.
    tie_unresolved: bool = False
    # Kurzfassung für den Bildschirm („Ringgleichheit, entschieden nach: letzte Zehnerserie“);
    # `tie_note_long` mit dem vollen Wortlaut des Kriteriums (wie `RankingRow`).
    tie_note: str | None = None
    tie_note_long: str | None = None
    # Fertiger Text zum Abbruchgrund für die Anzeige: „Abbruch (AB)“, „nicht angetreten“,
    # „disqualifiziert“; null ohne Abbruch.
    abort_label: str | None = None
    # Warum ein Abbruch mit erfassten Werten ohne Platz bleibt („Ergebnis nicht vergleichbar:
    # Regel für nicht geschossene Serien fehlt“); sonst null.
    abort_note: str | None = None


class FeedRankGroup(BaseModel):
    class_id: UUID | None
    # null bei gemeinsamer Wertung.
    class_name: str | None
    class_short: str | None
    # Plätze (Ergebnisliste: bis `top`; Live-Wertung: auch unvollständige, höchstens `rows`).
    rows: list[FeedRankRow]
    # Zeilen, die wegen der Zeilenzahl nicht gezeigt werden.
    more: int
    # Starts ohne Platz (nur mit `show_aborted`), nie unter den Plätzen: nicht angetreten,
    # disqualifiziert, Abbruch ohne Wertungswert (AB) oder ohne vergleichbares Ergebnis – mit
    # `abort_reason`, `abort_label` und dem anzeigbaren Namen wie bei Platzierten. Ein Abbruch
    # nach „Feuer“ mit Platz steht in `rows`.
    unplaced: list[FeedRankRow] = []


class FeedRanking(BaseModel):
    competition_id: UUID
    competition_name: str
    competition_code: str | None = None
    # Richtung und Einheit der Wertung (aus der Rangliste), null ohne Ergebnis.
    direction: str | None
    unit: str | None
    combined: bool
    groups: list[FeedRankGroup]
    # Wort für gleiche Ergebnisse dieses Wettbewerbs (wie `RankingOut.tie_word`).
    tie_word: str = "gleiches Ergebnis"
    # Verband des Katalogs (`catalog_federation`, klein); null bei eigener Disziplin. Wählt den
    # Begriffssatz (`GET /system/terms`).
    federation: str | None = None


class FeedStartlist(BaseModel):
    """Starts eines Wettbewerbs, sortiert: Durchgang (Uhrzeit, darin Bahn) bzw. Platz in der
    Reihenfolge, dann Startnummer, dann Versuch – der 1. Versuch einer Person steht vor ihrem
    2. (Regel der Startliste in `starts.views.startlist`)."""

    competition_id: UUID
    competition_name: str
    competition_code: str | None = None
    range_id: UUID | None
    range_name: str | None
    starts: list[FeedPerson]
    more: int
    # Verband des Katalogs (klein); null bei eigener Disziplin.
    federation: str | None = None


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
    series: list[FeedSeriesStep]


class FeedProcedureCurrent(BaseModel):
    """Laufende Position einer Bahn in diesem Ablauf (zum Hervorheben auf dem Bildschirm)."""

    lane: int
    start_id: UUID
    section_id: str
    # Serie, die gerade geschossen wird (ab 1): die erste noch nicht vollständig erfasste.
    series_number: int


class FeedProcedure(BaseModel):
    competition_id: UUID
    competition_name: str
    # Veraltet: gleich `competition_code` (einheitlicher Name in allen Szenen).
    catalog_code: str | None
    # Kennziffer aus dem Katalog („1201“); null bei eigenen Wettbewerben.
    competition_code: str | None = None
    variant_name: str
    description: str | None
    # Wertung in Worten, z. B. „Ringe, höher ist besser“.
    scoring: str
    # Zusätzliche Regeln in Worten, z. B. „−1 Ring je volle Sekunde über der Sollzeit“.
    notes: list[str]
    sections: list[FeedSection]
    # Verband des Katalogs (klein); null bei eigener Disziplin.
    federation: str | None = None
    # Je belegter Bahn dieses Wettbewerbs die laufende Serie (aus dem Erfassungsfortschritt;
    # aufgerufen ohne Eingabe: erste Serie). Fertig erfasste Bahnen fehlen.
    current: list[FeedProcedureCurrent] = []


class FeedLane(BaseModel):
    lane: int
    # Start auf der Bahn (aufgerufen oder erfasst, noch nicht freigegeben), null wenn frei.
    start: FeedPerson | None
    # Erfassungsfortschritt des Starts; null ohne Start oder solange nichts erfasst ist.
    progress: LaneProgressOut | None = None


class FeedNextHeat(BaseModel):
    number: int
    starts_at: datetime
    ends_at: datetime
    # Dieselben Zeitpunkte in Ortszeit des Turniers (ISO 8601 mit Versatz).
    starts_at_local: str
    ends_at_local: str


class FeedUpcomingBase(BaseModel):
    """Ein Start unter „Als Nächstes“."""

    start_id: UUID
    start_number: int
    display_name: str | None
    club: str | None
    class_short: str
    attempt: int
    # Steht die Person gerade auf einer Bahn (hier oder an einem anderen Stand)? Sie bleibt
    # sichtbar, wird aber gekennzeichnet („steht gerade auf 15-m-Stand, Bahn 2“).
    busy: bool = False
    busy_range_id: UUID | None = None
    busy_range_name: str | None = None
    busy_lane: int | None = None


class FeedUpcomingScheduled(FeedUpcomingBase):
    # Durchgang, Uhrzeit und gebuchte Bahn dieses Starts.
    heat_number: int
    starts_at: datetime
    starts_at_local: str
    lane: int


class FeedUpcomingQueued(FeedUpcomingBase):
    # Platz in der Reihenfolge des Stands (ab 1, über alle Wettbewerbe des Stands).
    position: int


class FeedUpcomingBlock(BaseModel):
    competition_id: UUID
    competition_name: str
    competition_code: str | None
    # Starts, die wegen `next_count` nicht gezeigt werden.
    more: int


class FeedUpcomingSchedule(FeedUpcomingBlock):
    """Nächster Durchgang des Stands: nur dessen wartende Starts dieses Wettbewerbs."""

    kind: Literal["schedule"]
    heat_number: int
    starts_at: datetime
    ends_at: datetime
    starts_at_local: str
    ends_at_local: str
    entries: list[FeedUpcomingScheduled]


class FeedUpcomingQueue(FeedUpcomingBlock):
    """Die nächsten Wartenden dieses Wettbewerbs in der Reihenfolge des Stands."""

    kind: Literal["queue"]
    entries: list[FeedUpcomingQueued]


FeedUpcoming = Annotated[FeedUpcomingSchedule | FeedUpcomingQueue, Field(discriminator="kind")]


class FeedRange(BaseModel):
    range_id: UUID
    range_name: str
    lane_count: int
    # Laufende Disziplin(en): aus den Starts am Stand, sonst aus den nächsten Starts.
    procedures: list[FeedProcedure]
    lanes: list[FeedLane]
    # „Als Nächstes“ je Wettbewerb: zuerst der nächste Durchgang (Zeitplan), dann die
    # Reihenfolge; je Block höchstens `next_count` Starts.
    upcoming: list[FeedUpcoming] = []
    # Veraltet (durch `upcoming` ersetzt): nächster Durchgang und eine gemischte Liste aus
    # Durchgang und Reihenfolge.
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
    # Bei diesen Server-Ereignissen neu laden: genaue Namen (aus den bekannten Ereignissen des
    # Servers, `GET /events/names`), direkt für `EventSource.addEventListener` geeignet.
    reload_on: list[str]
    # Zusätzlich spätestens nach so vielen Sekunden neu laden (z. B. Ablauf der Einspruchsfrist).
    poll_seconds: int
