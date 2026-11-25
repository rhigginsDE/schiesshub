"""Startrecht laut Meisterschaftstabelle des Verbands: reine Auswertung, ohne Datenbank.

Grundlage ist `<verband>/startrecht.yaml` (bisher nur DSB, Kopfkommentar der Datei erklärt die
Felder). Die Tabelle gilt für die Deutsche Meisterschaft; was sie sagt, ist für ein anderes Turnier
ein Hinweis, keine Sperre. Ein Start wird deshalb nie wegen des Startrechts abgelehnt, die
Anmeldung zeigt nur Warnung oder Hinweis mit Fundstelle.

Eine Klasse passt zu einem Eintrag über ihre Klassennummer und ihren Klassensatz. Nennt ein
Eintrag mehrere Sätze, gehört eine Nummer zum ersten Satz, der sie kennt (DSB Blasrohr: Schüler
20–25 nach Satz `blasrohr`, übrige nach `sportschiessen`; siehe `StartrechtEintrag.satz`).

Gewertet wird die Einzel-Spalte; Mannschaft und Mix-Team zählen als ausgeschrieben, weil ein
Start nicht sagt, ob er für eine Mannschaft geschossen wird. Was die Datei nicht hergibt (Klasse
ohne Nummer, Wettbewerb ohne Eintrag, Verband ohne Tabelle), ergibt keine Angabe und keine Meldung.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from app.modules.katalog.fileformat import StartrechtEintrag

StartRightStatus = Literal[
    # In der Tabelle ausgeschrieben (Einzel, Mannschaft oder Mix-Team).
    "startberechtigt",
    # Einzel-Zelle „b NN“: startet bei einer anderen Klasse (Hinweis).
    "startet_bei",
    # Grüne Zelle: Startmöglichkeit nach SpO 0.7.1.1 (Hinweis, kein Verstoß).
    "startmoeglichkeit_0711",
    # Rote Zelle (Warnung).
    "kein_startrecht",
    # Klasse gehört zu den Sätzen des Eintrags, steht aber in keiner Spalte (Warnung).
    "nicht_ausgeschrieben",
    # Kein Eintrag, keine Tabelle oder Klasse ohne Nummer: nichts zu sagen.
    "keine_angabe",
]
NoticeCode = Literal[
    "startet_bei", "startmoeglichkeit_0711", "kein_startrecht", "nicht_ausgeschrieben"
]
Severity = Literal["warning", "hint"]


@dataclass(frozen=True, slots=True)
class CatalogClass:
    """Klasse aus dem Katalog, soweit das Startrecht sie braucht."""

    nummer: str
    satz: str
    name: str

    @property
    def label(self) -> str:
        return f"{self.name} ({self.nummer})"


@dataclass(frozen=True, slots=True)
class StartRightsTable:
    """Startrecht-Tabelle eines Verbands mit den Klassen, auf die ihre Nummern verweisen."""

    # Kürzel des Verbands für den Text („DSB“).
    federation: str
    # `stand_tabelle` der Datei, z. B. „DM 2025–2028 (Sportschießen), DM 2026–2028 (Bogen)“.
    stand: str | None
    entries: Mapping[str, StartrechtEintrag]
    # (Satz, Nummer) -> Klasse.
    classes: Mapping[tuple[str, str], CatalogClass]


@dataclass(frozen=True, slots=True)
class StartRightNotice:
    code: NoticeCode
    severity: Severity
    message_de: str
    source: str


@dataclass(frozen=True, slots=True)
class StartRightResult:
    status: StartRightStatus
    notices: tuple[StartRightNotice, ...] = field(default=())


NO_STATEMENT = StartRightResult("keine_angabe")
ELIGIBLE = StartRightResult("startberechtigt")


def _sets(eintrag: StartrechtEintrag) -> list[str]:
    return [eintrag.satz] if isinstance(eintrag.satz, str) else list(eintrag.satz)


def _owner(sets: list[str], nummer: str, table: StartRightsTable) -> str | None:
    """Satz, zu dem eine Nummer im Eintrag gehört: der erste, der sie kennt."""
    for name in sets:
        if (name, nummer) in table.classes:
            return name
    return None


def _code(key: str, eintrag: StartrechtEintrag) -> str:
    return eintrag.kennziffer or key


def _competition_label(key: str, eintrag: StartrechtEintrag) -> str:
    extra = f", {eintrag.meisterschaft}" if eintrag.meisterschaft else ""
    return f"{eintrag.wettbewerb} ({_code(key, eintrag)}{extra})"


def _source(key: str, eintrag: StartrechtEintrag, table: StartRightsTable) -> str:
    stand = f", Stand: {table.stand}" if table.stand else ""
    return (
        f"Startrecht-Tabelle {table.federation} zur Deutschen Meisterschaft{stand}; "
        f"Eintrag {key} „{eintrag.wettbewerb}“"
    )


def _prefix(table: StartRightsTable) -> str:
    stand = f" (Stand: {table.stand})" if table.stand else ""
    return f"Laut DM-Tabelle des {table.federation}{stand}"


def assess_entry(
    key: str, eintrag: StartrechtEintrag, klasse: CatalogClass, table: StartRightsTable
) -> StartRightResult:
    """Startrecht einer Klasse in einem Eintrag der Tabelle (Schlüssel `key`, z. B. „1.10“)."""
    sets = _sets(eintrag)
    nummer = klasse.nummer
    prefix = _prefix(table)
    what = f"Klasse {klasse.label}"
    where = _competition_label(key, eintrag)
    source = _source(key, eintrag, table)

    # Gehört die Nummer im Eintrag zu einem anderen Satz, ist diese Klasse nicht gemeint.
    same_set = klasse.satz in sets and _owner(sets, nummer, table) == klasse.satz

    def notice(code: NoticeCode, severity: Severity, text: str) -> StartRightResult:
        if severity == "warning" and same_set:
            text += _schoolchildren_note(eintrag, nummer)
        status: StartRightStatus = code
        return StartRightResult(status, (StartRightNotice(code, severity, text, source),))

    if not same_set:
        return notice(
            "nicht_ausgeschrieben",
            "warning",
            f"{prefix} ist {what} in {where} nicht ausgeschrieben.",
        )

    mix = {number for team in eintrag.mix_team for number in team.klassen}
    if nummer in eintrag.einzel or nummer in eintrag.mannschaft or nummer in mix:
        return ELIGIBLE
    if nummer in eintrag.startet_bei:
        target = eintrag.startet_bei[nummer]
        owner = _owner(sets, target, table)
        target_class = table.classes.get((owner, target)) if owner else None
        target_label = target_class.label if target_class else target
        return notice(
            "startet_bei",
            "hint",
            f"{prefix} startet {what} in {where} bei Klasse {target_label}.",
        )
    if nummer in eintrag.startmoeglichkeit_0711:
        return notice(
            "startmoeglichkeit_0711",
            "hint",
            f"{prefix} ist {what} in {where} nicht eigens ausgeschrieben; Startmöglichkeit nach "
            "SpO 0.7.1.1 in der nächsthöheren bzw. leistungsstärkeren ausgeschriebenen Klasse.",
        )
    if nummer in eintrag.kein_startrecht:
        return notice(
            "kein_startrecht", "warning", f"{prefix} hat {what} in {where} kein Startrecht."
        )
    return notice(
        "nicht_ausgeschrieben", "warning", f"{prefix} ist {what} in {where} nicht ausgeschrieben."
    )


def _schoolchildren_note(eintrag: StartrechtEintrag, nummer: str) -> str:
    """Bogen: Die Tabelle nennt für Schüler eine eigene Deutsche Schülermeisterschaft."""
    dsm = eintrag.deutsche_schuelermeisterschaft
    if dsm is None or (nummer not in dsm.einzel and nummer not in dsm.mannschaft):
        return ""
    return " Bei der Deutschen Schülermeisterschaft ist die Klasse laut Tabelle ausgeschrieben."


def assess(
    table: StartRightsTable | None, competition_code: str | None, klasse: CatalogClass | None
) -> StartRightResult:
    """Startrecht einer Klasse in einem Wettbewerb (Kennziffer aus dem Katalog).

    Ein Wettbewerb kann mehrere Einträge haben (DSB „1.10“ und „para-1.10“, beide Kennziffer
    1.10); maßgeblich ist der, dessen Klassensätze die Klasse enthalten. Gehört die Klasse zu
    keinem davon, ist sie für diesen Wettbewerb in der Tabelle nicht ausgeschrieben.
    """
    if table is None or competition_code is None or klasse is None:
        return NO_STATEMENT
    candidates = [
        (key, eintrag)
        for key, eintrag in table.entries.items()
        if _code(key, eintrag) == competition_code
    ]
    if not candidates:
        return NO_STATEMENT
    # Der Eintrag ohne Präfix zuerst, falls die Klasse zu keinem passt.
    candidates.sort(key=lambda item: item[0] != competition_code)
    for key, eintrag in candidates:
        if klasse.satz in _sets(eintrag):
            return assess_entry(key, eintrag, klasse, table)
    key, eintrag = candidates[0]
    return assess_entry(key, eintrag, klasse, table)
