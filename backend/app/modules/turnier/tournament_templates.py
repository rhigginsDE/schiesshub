"""Fertige Turnier-Vorlagen: YAML-Dateien in `templates/`, eine Datei je Vorlage.

Eine Vorlage nennt Schießstände, den Verband für die Klassen und die Wettbewerbe nur über Verband
und Kennziffer. Regeln (Ablauf, Wertung) stehen ausschließlich im Katalog: Beim Anlegen entsteht
jeder Wettbewerb frisch aus dem aktuellen Katalog, genau wie `POST …/competitions`. Startgeld,
Mehrfachstart und Planung kommen aus den Einstellungen der Vorlage, sofern ein Wettbewerb sie
nicht selbst setzt.

Neue Vorlage: Datei in `templates/` anlegen, `id` = Dateiname ohne `.yaml`. Der Test
`tests/turnier/test_templates.py` prüft jede Vorlage gegen den echten Katalog.
"""

import functools
from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.begriffe import begriffe_fuer
from app.core.errors import InputError, summarize, translate_errors
from app.core.events import EventHub
from app.core.security import Actor
from app.modules.katalog import service as katalog_service
from app.modules.turnier import service
from app.modules.turnier.models import Competition, Range, Tournament
from app.modules.turnier.schemas import (
    CaptureMode,
    CompetitionCreate,
    MultiStartRule,
    Name,
    NonNegativeInt,
    Planning,
    PositiveInt,
    RangeCreate,
    Template,
    TemplateCompetitionOut,
    TemplateGapOut,
    TemplateRangeOut,
    TemplateUnavailableOut,
    TournamentCreate,
    TournamentFromTemplate,
    TournamentSettingsUpdate,
    TournamentTemplateOut,
)

TEMPLATE_DIR = Path(__file__).parent / "templates"
Key = Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", min_length=1, max_length=80)]


class _FileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TemplateRange(_FileModel):
    # Kurzname, über den Wettbewerbe auf den Schießstand verweisen.
    key: Key
    name: Name
    lane_count: PositiveInt


class TemplateClasses(_FileModel):
    # Alle Klassen dieses Verbands aus dem Katalog übernehmen.
    federation: Annotated[str, Field(min_length=1, max_length=80)]


class TemplateCompetition(_FileModel):
    """Verweis auf eine Katalog-Disziplin; alle übrigen Felder sind freiwillig."""

    # Kurzname innerhalb der Datei (Übungsturnier: Verweis der Starts).
    key: Key | None = None
    catalog_federation: Annotated[str, Field(min_length=1, max_length=80)]
    catalog_code: Annotated[str, Field(min_length=1, max_length=40)]
    variant_id: Annotated[str, Field(min_length=1)] | None = None
    name: Name | None = None
    # `key` eines Schießstands der Vorlage.
    range: Key | None = None
    capture_mode: CaptureMode | None = None
    multi_start: bool | None = None
    max_starts: PositiveInt | None = None
    multi_start_rule: MultiStartRule | None = None
    fee_first_cents: NonNegativeInt | None = None
    fee_repeat_cents: NonNegativeInt | None = None
    planning: Planning | None = None
    heat_minutes: PositiveInt | None = None
    changeover_minutes: NonNegativeInt | None = None

    def create_data(self, range_id: object) -> CompetitionCreate:
        fields = self.model_dump(exclude_none=True, exclude={"key", "range"})
        return CompetitionCreate.model_validate(
            {**fields, "range_id": range_id} if range_id is not None else fields, strict=False
        )


class TournamentTemplate(_FileModel):
    schema_version: Literal[1] = Field(alias="schema")
    id: Key
    name: Name
    description: Annotated[str, Field(min_length=1, max_length=300)]
    # Grundeinstellungen (`open`, `club_championship`, `custom`), siehe `TournamentCreate`.
    template: Template = "custom"
    settings: TournamentSettingsUpdate | None = None
    classes: TemplateClasses | None = None
    ranges: list[TemplateRange] = Field(default_factory=list)
    competitions: Annotated[list[TemplateCompetition], Field(min_length=1)]

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        range_keys = [item.key for item in self.ranges]
        if len(range_keys) != len(set(range_keys)):
            raise ValueError("Ein Schießstand-Kurzname (key) ist mehrfach vergeben.")
        keys = [item.key for item in self.competitions if item.key is not None]
        if len(keys) != len(set(keys)):
            raise ValueError("Ein Wettbewerbs-Kurzname (key) ist mehrfach vergeben.")
        for item in self.competitions:
            if item.range is not None and item.range not in range_keys:
                raise ValueError(
                    f"Der Schießstand „{item.range}“ ist in der Vorlage nicht angelegt."
                )
        return self


class TemplateFileError(Exception):
    """Eine Vorlagendatei ist ungültig (Fehler im Repository, nicht in der Anfrage)."""


def read_template_file[T: TournamentTemplate](path: Path, model: type[T]) -> T:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return model.model_validate(data, strict=False)
    except ValidationError as exc:
        raise TemplateFileError(
            f"{path.name}: {summarize(translate_errors(exc.errors()))}"
        ) from exc
    except yaml.YAMLError as exc:
        raise TemplateFileError(f"{path.name}: kein gültiges YAML ({exc}).") from exc


@functools.cache
def load_templates(directory: Path = TEMPLATE_DIR) -> dict[str, TournamentTemplate]:
    """Alle Vorlagen nach `id`, in der Reihenfolge der Dateinamen."""
    templates: dict[str, TournamentTemplate] = {}
    for path in sorted(directory.glob("*.yaml")):
        template = read_template_file(path, TournamentTemplate)
        if template.id != path.stem:
            raise TemplateFileError(
                f"{path.name}: Die id „{template.id}“ muss dem Dateinamen entsprechen."
            )
        templates[template.id] = template
    return templates


# --- Gegen den Katalog prüfen ----------------------------------------------------


async def _competition_out(
    session: AsyncSession, item: TemplateCompetition
) -> TemplateCompetitionOut:
    name: str | None = None
    available = False
    try:
        discipline = await katalog_service.get_discipline(
            session, item.catalog_federation, item.catalog_code
        )
    except katalog_service.NotFoundError:
        pass
    else:
        name = discipline.name
        variants = [variant.id for variant in discipline.ablauf.varianten]
        available = item.variant_id is None or item.variant_id in variants
    return TemplateCompetitionOut(
        catalog_federation=item.catalog_federation,
        catalog_code=item.catalog_code,
        name=name,
        available=available,
    )


async def template_out(
    session: AsyncSession, template: TournamentTemplate
) -> TournamentTemplateOut:
    return TournamentTemplateOut(
        id=template.id,
        name=template.name,
        description=template.description,
        template=template.template,
        classes_federation=template.classes.federation if template.classes else None,
        ranges=[
            TemplateRangeOut(name=item.name, lane_count=item.lane_count) for item in template.ranges
        ],
        competitions=[await _competition_out(session, item) for item in template.competitions],
    )


async def list_templates(session: AsyncSession) -> list[TournamentTemplateOut]:
    return [await template_out(session, template) for template in load_templates().values()]


async def missing_in_catalog(
    session: AsyncSession, template: TournamentTemplate
) -> list[TemplateGapOut]:
    """Was die Vorlage braucht und der aktuelle Katalog nicht hat (Kennziffern, Klassen)."""
    missing = []
    for item in template.competitions:
        if not (await _competition_out(session, item)).available:
            federation = item.catalog_federation
            word = begriffe_fuer(federation).kennziffer
            variant = f", Variante „{item.variant_id}“" if item.variant_id else ""
            missing.append(
                TemplateGapOut(
                    kind="competition",
                    federation=federation,
                    code=item.catalog_code,
                    variant_id=item.variant_id,
                    message_de=f"{word} {item.catalog_code} ({federation.upper()}){variant}",
                )
            )
    if template.classes is not None:
        federation = template.classes.federation
        try:
            await katalog_service.list_classes(session, federation)
        except katalog_service.NotFoundError:
            missing.append(
                TemplateGapOut(
                    kind="classes",
                    federation=federation,
                    message_de=f"Klassen des Verbands {federation.upper()}",
                )
            )
    return missing


class TemplateUnavailableError(Exception):
    """HTTP 409 `template_unavailable`: Die Vorlage passt nicht zum aktuellen Katalog."""

    def __init__(self, template: TournamentTemplate, missing: list[TemplateGapOut]) -> None:
        super().__init__(
            f"Die Vorlage „{template.name}“ passt nicht zum aktuellen Katalog: "
            f"{', '.join(item.message_de for item in missing)} gibt es dort nicht."
        )
        self.template_id = template.id
        self.missing = missing

    def out(self) -> TemplateUnavailableOut:
        return TemplateUnavailableOut(
            detail=str(self), template_id=self.template_id, missing=self.missing
        )


# --- Anlegen ------------------------------------------------------------------------


async def build_from_template(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    template: TournamentTemplate,
    data: TournamentCreate,
    *,
    is_practice: bool = False,
) -> tuple[Tournament, dict[str, Range], dict[str, Competition]]:
    """Legt Turnier, Schießstände, Klassen und Wettbewerbe an; die Wettbewerbe frisch aus dem
    Katalog.

    Liefert Schießstände und Wettbewerbe nach ihrem `key`. Scheitert ein Schritt, wird das halb
    angelegte Turnier wieder gelöscht.
    """
    if missing := await missing_in_catalog(session, template):
        raise TemplateUnavailableError(template, missing)
    tournament = await service.create_tournament(session, events, data, is_practice=is_practice)
    try:
        ranges: dict[str, Range] = {}
        for item in template.ranges:
            ranges[item.key] = await service.create_range(
                session,
                events,
                tournament.id,
                RangeCreate(name=item.name, lane_count=item.lane_count),
            )
        if template.classes is not None:
            await service.import_classes(
                session, events, tournament.id, template.classes.federation
            )
        competitions: dict[str, Competition] = {}
        for index, item in enumerate(template.competitions):
            range_id = ranges[item.range].id if item.range is not None else None
            competition = await service.create_competition(
                session, events, tournament.id, item.create_data(range_id), actor
            )
            competitions[item.key or str(index)] = competition
    except Exception:
        await session.rollback()
        await service.delete_tournament(session, events, tournament.id)
        raise
    return tournament, ranges, competitions


async def create_from_template(
    session: AsyncSession, events: EventHub, actor: Actor, data: TournamentFromTemplate
) -> Tournament:
    template = load_templates().get(data.template_id)
    if template is None:
        known = ", ".join(f"„{key}“" for key in load_templates())
        raise InputError.single(
            "template_id", f"Die Vorlage „{data.template_id}“ gibt es nicht. Vorhanden: {known}."
        )
    create = TournamentCreate(
        name=data.name,
        organizer=data.organizer,
        date_from=data.date_from,
        date_to=data.date_to,
        template=template.template,
        settings=template.settings,
    )
    tournament, _, _ = await build_from_template(session, events, actor, template, create)
    return tournament
