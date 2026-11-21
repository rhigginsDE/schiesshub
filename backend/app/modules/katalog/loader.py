"""Liest das Katalog-Verzeichnis und prüft es, ohne die Datenbank zu berühren.

Aufbau des Verzeichnisses (siehe catalog/README.md):

    <verband>/katalog.yaml
    <verband>/klassen.yaml        (optional)
    <verband>/gruppen/<gruppe>.yaml

Jeder Verband wird für sich geprüft. Hat ein Verband auch nur einen Fehler, wird er als Ganzes
nicht übernommen; die Fehler nennen Datei und Pfad innerhalb der Datei.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from app.modules.katalog.fileformat import GruppenDatei, KatalogDatei, KlassenDatei

HEAD_FILE = "katalog.yaml"
CLASSES_FILE = "klassen.yaml"
GROUPS_DIR = "gruppen"

_MESSAGES = {
    "extra_forbidden": "unbekanntes Feld",
    "missing": "Pflichtfeld fehlt",
    "string_type": "muss Text sein (in Anführungszeichen setzen)",
    "int_type": "muss eine ganze Zahl sein",
    "bool_type": "muss true oder false sein",
    "list_type": "muss eine Liste sein",
    "dict_type": "muss eine Zuordnung (Schlüssel: Wert) sein",
    "model_type": "muss eine Zuordnung (Schlüssel: Wert) sein",
    "string_too_short": "darf nicht leer sein",
}


@dataclass(frozen=True, slots=True)
class CatalogError:
    """Ein Fehler im Katalog. `datei` ist relativ zum Katalog-Verzeichnis."""

    verband: str | None
    datei: str | None
    pfad: str | None
    meldung: str

    def __str__(self) -> str:
        location = ": ".join(part for part in (self.datei, self.pfad) if part)
        return f"{location}: {self.meldung}" if location else self.meldung

    def as_dict(self) -> dict[str, str | None]:
        return {
            "verband": self.verband,
            "datei": self.datei,
            "pfad": self.pfad,
            "meldung": self.meldung,
        }


@dataclass(frozen=True, slots=True)
class GroupSource:
    file: str
    content: GruppenDatei


@dataclass(frozen=True, slots=True)
class FederationCatalog:
    """Vollständig geprüfter Katalog eines Verbands."""

    key: str
    head: KatalogDatei
    classes: KlassenDatei | None
    groups: list[GroupSource]

    @property
    def discipline_count(self) -> int:
        return sum(len(group.content.disziplinen) for group in self.groups)


@dataclass(slots=True)
class LoadResult:
    federations: list[FederationCatalog] = field(default_factory=list)
    errors: list[CatalogError] = field(default_factory=list)
    # Alle Verbandsverzeichnisse, auch fehlerhafte. None: das Verzeichnis war nicht lesbar.
    present_keys: set[str] | None = None


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader, der doppelte Schlüssel ablehnt (PyYAML überschreibt sie sonst still)."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None,
                    None,
                    f"Schlüssel '{key}' kommt doppelt vor",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep)


def _format_path(loc: tuple[int | str, ...]) -> str:
    path = ""
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else str(part)
    return path


def _message(error: dict[str, Any]) -> str:
    if error["type"] == "value_error":
        return str(error["ctx"]["error"]) if "ctx" in error else error["msg"]
    return _MESSAGES.get(error["type"], error["msg"])


class _FederationReader:
    """Liest und prüft das Verzeichnis eines Verbands und sammelt dabei alle Fehler."""

    def __init__(self, root: Path, directory: Path) -> None:
        self.root = root
        self.directory = directory
        self.key = directory.name
        self.errors: list[CatalogError] = []

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def _error(self, path: Path, pfad: str | None, meldung: str) -> None:
        self.errors.append(CatalogError(self.key, self._relative(path), pfad, meldung))

    def _parse[T: BaseModel](self, path: Path, model: type[T]) -> T | None:
        try:
            # Der eigene Loader ist von SafeLoader abgeleitet und baut keine beliebigen Objekte.
            raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            where = f"Zeile {mark.line + 1}" if mark is not None else None
            problem = getattr(exc, "problem", None) or str(exc)
            self._error(path, where, f"kein gültiges YAML: {problem}")
            return None
        except (OSError, UnicodeDecodeError) as exc:
            self._error(path, None, f"Datei nicht lesbar: {exc}")
            return None
        try:
            return model.model_validate(raw)
        except ValidationError as exc:
            for error in exc.errors():
                self._error(path, _format_path(error["loc"]) or None, _message(error))
            return None

    def read(self) -> FederationCatalog | None:
        head = self._read_head()
        classes = self._read_classes()
        groups = self._read_groups()
        self._report_unknown_files()
        if self.errors or head is None:
            return None
        return FederationCatalog(key=self.key, head=head, classes=classes, groups=groups)

    def _read_head(self) -> KatalogDatei | None:
        path = self.directory / HEAD_FILE
        if not path.is_file():
            self._error(path, None, "Datei fehlt")
            return None
        head = self._parse(path, KatalogDatei)
        if head is not None and head.id != self.key:
            self._error(path, "id", f"'{head.id}' passt nicht zum Verzeichnis '{self.key}'")
        return head

    def _read_classes(self) -> KlassenDatei | None:
        path = self.directory / CLASSES_FILE
        if not path.is_file():
            return None
        classes = self._parse(path, KlassenDatei)
        if classes is None:
            return None
        if classes.verband != self.key:
            self._error(
                path, "verband", f"'{classes.verband}' passt nicht zum Verzeichnis '{self.key}'"
            )
        known: set[str] = set()
        for index, klasse in enumerate(classes.klassen):
            if klasse.id in known:
                self._error(path, f"klassen[{index}].id", f"Klasse '{klasse.id}' mehrfach vergeben")
            known.add(klasse.id)
        for index, klasse in enumerate(classes.klassen):
            for position, target in enumerate(klasse.zusammenlegen_in):
                pfad = f"klassen[{index}].zusammenlegen_in[{position}]"
                if target not in known:
                    self._error(path, pfad, f"verweist auf unbekannte Klasse '{target}'")
                elif target == klasse.id:
                    self._error(path, pfad, "verweist auf die Klasse selbst")
        return classes

    def _read_groups(self) -> list[GroupSource]:
        groups_dir = self.directory / GROUPS_DIR
        if not groups_dir.is_dir():
            self._error(groups_dir, None, "Verzeichnis fehlt")
            return []
        groups: list[GroupSource] = []
        # Kennziffer -> Datei, in der sie zuerst vorkam (eindeutig je Verband).
        codes: dict[str, str] = {}
        for path in sorted(groups_dir.glob("*.yaml")):
            content = self._parse(path, GruppenDatei)
            if content is None:
                continue
            self._check_group(path, content, codes)
            groups.append(GroupSource(file=self._relative(path), content=content))
        return groups

    def _check_group(self, path: Path, content: GruppenDatei, codes: dict[str, str]) -> None:
        if content.verband != self.key:
            self._error(
                path, "verband", f"'{content.verband}' passt nicht zum Verzeichnis '{self.key}'"
            )
        if content.gruppe.id != path.stem:
            self._error(
                path, "gruppe.id", f"'{content.gruppe.id}' passt nicht zum Dateinamen '{path.name}'"
            )
        relative = self._relative(path)
        for index, disziplin in enumerate(content.disziplinen):
            if disziplin.ablauf not in content.ablaeufe:
                self._error(
                    path,
                    f"disziplinen[{index}].ablauf",
                    f"verweist auf unbekannten Ablauf '{disziplin.ablauf}'",
                )
            first_seen = codes.get(disziplin.kennziffer)
            if first_seen is None:
                codes[disziplin.kennziffer] = relative
                continue
            where = "in dieser Datei" if first_seen == relative else f"in {first_seen}"
            self._error(
                path,
                f"disziplinen[{index}].kennziffer",
                f"Kennziffer '{disziplin.kennziffer}' ist doppelt vergeben (bereits {where})",
            )

    def _report_unknown_files(self) -> None:
        for path in sorted(self.directory.iterdir()):
            is_yaml = path.is_file() and path.suffix in {".yaml", ".yml"}
            if is_yaml and path.name not in {HEAD_FILE, CLASSES_FILE}:
                self._error(path, None, "unbekannte Datei im Verbandsverzeichnis")
        groups_dir = self.directory / GROUPS_DIR
        if groups_dir.is_dir():
            for path in sorted(groups_dir.glob("*.yml")):
                self._error(path, None, "Gruppendateien müssen auf .yaml enden")


def load_catalog(root: Path) -> LoadResult:
    """Liest alle Verbände unter `root`. Wirft keine Ausnahme; Fehler stehen im Ergebnis."""
    result = LoadResult()
    try:
        directories = sorted(
            entry for entry in root.iterdir() if entry.is_dir() and not entry.name.startswith(".")
        )
    except OSError as exc:
        result.errors.append(
            CatalogError(None, None, None, f"Katalog-Verzeichnis '{root}' ist nicht lesbar: {exc}")
        )
        return result

    result.present_keys = {directory.name for directory in directories}
    for directory in directories:
        reader = _FederationReader(root, directory)
        federation = reader.read()
        result.errors.extend(reader.errors)
        if federation is not None:
            result.federations.append(federation)
    return result
