"""Rohwerte eines Starts lesen und prüfen (Format: docs/DATENMODELL.md, „Rohwerte“).

```
{"sections": {"<abschnitt>": {"series": [<serie> | null, …], "time_cs": 6543}}}
<serie> = {"shots": [10, 9, "X", …]}  oder  {"sum": 92, "tens": 3, "inner_tens": 1}
          plus "time_cs" (Zeit je Serie) und "standing" (stehende Scheiben), wo es sie gibt,
          und optional "status" (Ablauf der Serie, siehe status.py; Standard "normal")
```

- `time_cs` auf Abschnittsebene gibt es nur bei Abschnitten mit Gesamtzeit (`sollzeit_s` oder
  `max_gesamtzeit_s`, Mehrdistanz-Parcours); sonst steht die Zeit an der Serie.
- Einzelschuss und Seriensumme dürfen in einem Start gemischt vorkommen (z. B. nach einem
  Wechsel der Erfassungsart); innerhalb einer Serie gilt entweder-oder.
- `null` in `series` ist eine noch nicht erfasste Serie (nur im Zwischenstand erlaubt).
- Fehlende Schüsse werden nie als 0 gewertet: Eine 0 zählt nur, wenn sie erfasst wurde.
- `tens` zählt alle Zehner einschließlich der Innenzehner, `inner_tens` nur die Innenzehner.
- Mit `ringwerte` im Abschnitt sind nur diese Ringwerte erlaubt (auch über 10, Bogen 3D: 11;
  „X“ nur, wenn es in `ringwerte` steht). Ohne `schuss_je_serie`, aber mit `ziele_je_serie`
  steht in `shots` ein Wert je Ziel (Wurfscheibe: 1 Treffer, 0 Fehler).
- **Zehntelwertung** (`scoring.zehntelwertung`): je Schuss 0 oder 1,0 bis 10,9 mit höchstens
  einer Nachkommastelle, als Zahl (`10.5`) oder Text mit Komma oder Punkt (`"10,5"`). Die
  Rohwerte werden gespeichert, wie sie kommen; gerechnet wird mit `Decimal`. Seriensumme
  ebenso (höchstens 10,9 × Schusszahl, 0 oder ab 1,0); `tens` zählt Schüsse ab 10,0;
  `inner_tens` gibt es nicht (kein „X“).
- Gestrichene Serien (`serien_gewertet`) dürfen erfasst werden und werden geprüft, sind aber
  nie Pflicht.
- Zeiten sind ganze Hundertstel größer 0. Braucht der Status der Serie keine gemessene Zeit
  (Zeitlimit, Abbruch, Störung), stört eine 0 nicht (sie wird ignoriert).
- Kein Schlüssel, den die Maske für die Serie kennt, wird wegen des Status abgelehnt; was der
  Status nicht wertet, bleibt in den Rohwerten stehen (`status.field_role`). Eine nicht
  beendete Serie geht auch als Seriensumme (die bis dahin erzielten Ringe).
- **Plausibilität:** Eine gemessene Zeit, die zählt (Serie regulär oder nicht beendet,
  Gesamtzeit eines Abschnitts), darf höchstens `PLAUSIBLE_FACTOR` (3) × Zeitlimit betragen
  (`max_zeit_je_serie_s` bzw. `max_gesamtzeit_s`), ohne Limit höchstens `PLAUSIBLE_MAX_S`
  (1 Stunde). Je Abschnitt überschreibbar: `zeit_plausibel_faktor`, `zeit_plausibel_max_s`.
  Darüber ist es ein Fehler (Tippfehler wie 9.999 s); zwischen Limit und Grenze nur eine
  Warnung der Wertung (`compute`).
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from app.scoring.definition import Definition, check_capture_mode, load_definition
from app.scoring.errors import Issue
from app.scoring.numbers import (
    decimal_places,
    format_cs,
    format_number,
    format_seconds_value,
    parse_decimal_input,
    to_tenths,
)
from app.scoring.plan import (
    DEFAULT_RING_VALUES,
    INNER_TEN,
    MAX_RING,
    MAX_TENTHS,
    MAX_TENTHS_BELOW_TEN,
    MIN_TENTHS,
    SectionPlan,
    SeriesPlan,
    Shot,
)
from app.scoring.status import NORMAL, STATUS_LABELS, UNFINISHED, SeriesStatus, field_role

RING_KEYS = ("shots", "sum", "tens", "inner_tens")
PLAUSIBLE_FACTOR = Decimal(3)
PLAUSIBLE_MAX_S = Decimal(3600)
TENTHS_RANGE = "Bei Zehntelwertung sind Werte von 1,0 bis 10,9 oder 0 erlaubt."


@dataclass(frozen=True)
class RawSeries:
    shots: tuple[Shot, ...] | None = None
    total: int | Decimal | None = None
    tens: int | None = None
    inner_tens: int | None = None
    time_cs: int | None = None
    standing: int | None = None
    status: SeriesStatus = NORMAL


@dataclass(frozen=True)
class RawSection:
    series: tuple[RawSeries | None, ...]
    time_cs: int | None = None


def validate_raw(
    definition: Mapping[str, Any] | Definition,
    capture_mode: str,
    raw: object,
    *,
    partial: bool = True,
) -> list[Issue]:
    """Alle Fehler der Rohwerte mit Pfad und Meldung; leer heißt in Ordnung.

    `partial=True` erlaubt fehlende Serien, Schüsse und Zeiten (Zwischenstand),
    `partial=False` verlangt ein vollständiges Ergebnis.
    """
    check_capture_mode(capture_mode)
    _, issues = read_raw(load_definition(definition), raw, partial=partial)
    return issues


def read_raw(
    definition: Definition, raw: object, *, partial: bool
) -> tuple[dict[str, RawSection], list[Issue]]:
    reader = _Reader(definition, partial)
    return reader.read(raw), reader.issues


def series_label(definition: Definition, section: SectionPlan, series: SeriesPlan) -> str:
    prefix = f"{section.name}, " if definition.multi_section else ""
    return f"{prefix}Serie {series.number}"


def plausible_max_s(plan: SectionPlan, limit_s: Decimal | None) -> Decimal:
    """Höchste plausible gemessene Zeit in Sekunden (siehe Modulbeschreibung)."""
    spec = plan.spec
    if spec.zeit_plausibel_max_s is not None:
        return spec.zeit_plausibel_max_s
    if limit_s is not None:
        return (spec.zeit_plausibel_faktor or PLAUSIBLE_FACTOR) * limit_s
    return PLAUSIBLE_MAX_S


def _as_int(value: object) -> int | None:
    """Die Zahl, wenn `value` eine echte ganze Zahl ist (kein Wahrheitswert, keine Kommazahl)."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class _Reader:
    def __init__(self, definition: Definition, partial: bool) -> None:
        self.definition = definition
        self.partial = partial
        self.issues: list[Issue] = []

    def add(self, path: str, message: str) -> None:
        self.issues.append(Issue(path=path, message=message))

    def read(self, raw: object) -> dict[str, RawSection]:
        if not isinstance(raw, Mapping):
            self.add("", "Rohwerte müssen ein Objekt sein")
            return {}
        for key in raw:
            if key != "sections":
                self.add(str(key), "unbekanntes Feld")
        sections = raw.get("sections", {})
        if not isinstance(sections, Mapping):
            self.add("sections", "muss ein Objekt mit einem Eintrag je Abschnitt sein")
            return {}
        for key in sections:
            if self.definition.section(str(key)) is None:
                known = ", ".join(s.id for s in self.definition.sections)
                self.add(f"sections.{key}", f"unbekannter Abschnitt „{key}“ (bekannt: {known})")
        return {
            plan.id: self.section(plan, sections.get(plan.id), f"sections.{plan.id}")
            for plan in self.definition.sections
        }

    def section(self, plan: SectionPlan, data: object, path: str) -> RawSection:
        empty = RawSection(series=(None,) * len(plan.series))
        if data is None:
            if not self.partial:
                self.add(path, f"{plan.name}: Abschnitt fehlt")
            return empty
        if not isinstance(data, Mapping):
            self.add(path, f"{plan.name}: muss ein Objekt sein")
            return empty
        allowed = {"series", "time_cs"} if plan.section_time else {"series"}
        for key in data:
            if key not in allowed:
                message = (
                    f"{plan.name}: Gesamtzeit gibt es nur bei Abschnitten mit Sollzeit"
                    if key == "time_cs"
                    else "unbekanntes Feld"
                )
                self.add(f"{path}.{key}", message)

        time_cs = None
        if plan.section_time:
            label = f"{plan.name}: Gesamtzeit"
            time_cs = self.time(data.get("time_cs"), f"{path}.time_cs", label)
            time_cs = self.plausible(
                plan, time_cs, plan.spec.max_gesamtzeit_s, f"{path}.time_cs", f"{label} "
            )

        items = data.get("series", [])
        if not isinstance(items, list):
            self.add(f"{path}.series", f"{plan.name}: Serien müssen eine Liste sein")
            items = []
        if len(items) > len(plan.series):
            self.add(
                f"{path}.series",
                f"{plan.name}: höchstens {len(plan.series)} Serien, erfasst {len(items)}",
            )
        series = tuple(
            self.series(
                plan,
                series_plan,
                items[series_plan.index] if series_plan.index < len(items) else None,
                f"{path}.series[{series_plan.index}]",
            )
            for series_plan in plan.series
        )
        return RawSection(series=series, time_cs=time_cs)

    def series(
        self, plan: SectionPlan, series_plan: SeriesPlan, data: object, path: str
    ) -> RawSeries | None:
        if not series_plan.struck:
            return self.series_values(plan, series_plan, data, path)
        # Gestrichene Serien: Eingaben werden geprüft, sind aber nie Pflicht.
        saved_partial = self.partial
        self.partial = True
        try:
            return self.series_values(plan, series_plan, data, path)
        finally:
            self.partial = saved_partial

    def series_values(
        self, plan: SectionPlan, series_plan: SeriesPlan, data: object, path: str
    ) -> RawSeries | None:
        label = series_label(self.definition, plan, series_plan)
        if data is None:
            if not self.partial:
                self.add(path, f"{label} fehlt")
            return None
        if not isinstance(data, Mapping):
            self.add(path, f"{label}: muss ein Objekt sein")
            return None

        allowed = {"status"}
        if plan.rings:
            allowed.update(RING_KEYS)
        if plan.series_time:
            allowed.add("time_cs")
        if plan.standing:
            allowed.add("standing")
        for key in data:
            if key not in allowed:
                self.add(f"{path}.{key}", f"{label}: {self.foreign_key_message(plan, str(key))}")

        status = self.status(plan, data.get("status"), f"{path}.status", label)
        result = RawSeries(status=status)
        if plan.rings:
            result = replace(result, **self.rings(plan, series_plan, data, path, label, status))
        # Jeder Schlüssel der Maske wird bei jedem Status angenommen und geprüft (Typ, Bereich);
        # was nicht zählt (`field_role` = „unscored“), ist nie Pflicht und bleibt erhalten.
        if plan.series_time:
            scored = field_role(status, "time_cs") == "required"
            time_cs = self.time(
                data.get("time_cs"), f"{path}.time_cs", f"{label}: Zeit", required=scored
            )
            if scored:
                time_cs = self.plausible(
                    plan, time_cs, plan.spec.max_zeit_je_serie_s, f"{path}.time_cs", f"{label}: "
                )
            result = replace(result, time_cs=time_cs)
        if plan.standing:
            standing = self.standing(
                plan,
                data.get("standing"),
                f"{path}.standing",
                label,
                required=field_role(status, "standing") == "required",
            )
            result = replace(result, standing=standing)
        return result

    def status(self, plan: SectionPlan, value: object, path: str, label: str) -> SeriesStatus:
        if value is None:
            return NORMAL
        allowed = self.definition.series_statuses(plan)
        for status in allowed:
            if value == status:
                return status
        names = ", ".join(f"„{s}“ ({STATUS_LABELS[s]})" for s in allowed)
        kind = "für diese Disziplin nicht vorgesehener" if value in STATUS_LABELS else "unbekannter"
        self.add(path, f"{label}: {kind} Status {value!r}; erlaubt: {names}")
        return NORMAL

    def foreign_key_message(self, plan: SectionPlan, key: str) -> str:
        if key in RING_KEYS:
            return "dieser Abschnitt wertet keine Ringe"
        if key == "time_cs":
            if plan.section_time:
                return "die Zeit wird für den ganzen Abschnitt erfasst, nicht je Serie"
            return "dieser Abschnitt misst keine Zeit"
        if key == "standing":
            return "dieser Abschnitt hat keine Zuschläge für stehende Scheiben"
        return f"unbekanntes Feld „{key}“"

    def rings(
        self,
        plan: SectionPlan,
        series_plan: SeriesPlan,
        data: Mapping[str, Any],
        path: str,
        label: str,
        status: SeriesStatus,
    ) -> dict[str, Any]:
        count = series_plan.shots or 0
        shots_data = data.get("shots")
        has_sum_fields = any(key in data for key in ("sum", "tens", "inner_tens"))
        if shots_data is not None and has_sum_fields:
            self.add(path, f"{label}: entweder Einzelschüsse oder Seriensumme, nicht beides")
            return {}
        if shots_data is not None:
            return {"shots": self.shots(plan, shots_data, count, f"{path}.shots", label, status)}
        if has_sum_fields:
            return self.series_sum(plan, data, count, path, label)
        if not self.partial:
            self.add(path, f"{label}: Ringe fehlen")
        return {}

    def shots(
        self,
        plan: SectionPlan,
        data: object,
        count: int,
        path: str,
        label: str,
        status: SeriesStatus,
    ) -> tuple[Shot, ...]:
        unit = "Ziele" if plan.per_target else "Schuss"
        if not isinstance(data, list):
            self.add(
                path, f"{label}: {'Werte' if plan.per_target else 'Schüsse'} müssen eine Liste sein"
            )
            return ()
        if len(data) > count:
            self.add(path, f"{label}: höchstens {count} {unit}, erfasst {len(data)}")
        elif status == UNFINISHED and len(data) == count:
            self.add(path, f"{label}: als nicht beendet erfasst, aber alle {count} Schuss erfasst")
        elif len(data) < count and not self.partial and status != UNFINISHED:
            self.add(path, f"{label}: {len(data)} von {count} {unit} erfasst")
        if plan.tenths:
            return self.tenths_shots(data[:count], path, label)
        allowed = plan.ring_values
        valid: list[Shot] = []
        for index, value in enumerate(data[:count]):
            shot = INNER_TEN if value == INNER_TEN else _as_int(value)
            if shot is not None and shot in allowed:
                valid.append(shot)
            elif plan.per_target:
                self.add(
                    f"{path}[{index}]",
                    f"{label}, Ziel {index + 1}: Wert {_allowed_text(allowed)}, nicht {value!r}",
                )
            else:
                self.add(
                    f"{path}[{index}]",
                    f"{label}, Schuss {index + 1}: Ringwert {_allowed_text(allowed)}, "
                    f"nicht {value!r}",
                )
        return tuple(valid)

    def tenths_shots(self, data: list[Any], path: str, label: str) -> tuple[Shot, ...]:
        valid: list[Shot] = []
        for index, value in enumerate(data):
            number = parse_decimal_input(value)
            where = f"{label}, Schuss {index + 1}"
            if number is not None and decimal_places(number) > 1:
                self.add(
                    f"{path}[{index}]",
                    f"{where}: höchstens eine Nachkommastelle. {TENTHS_RANGE} (erfasst: {value!r})",
                )
            elif number is None or not (number == 0 or MIN_TENTHS <= number <= MAX_TENTHS):
                self.add(f"{path}[{index}]", f"{where}: {TENTHS_RANGE} (erfasst: {value!r})")
            else:
                valid.append(to_tenths(number))
        return tuple(valid)

    def series_sum(
        self, plan: SectionPlan, data: Mapping[str, Any], count: int, path: str, label: str
    ) -> dict[str, Any]:
        if plan.tenths:
            return self.tenths_sum(data, count, path, label)
        total = self.integer(
            data.get("sum"), f"{path}.sum", f"{label}: Seriensumme", count * plan.max_ring
        )
        tens = self.integer(data.get("tens"), f"{path}.tens", f"{label}: Zehner", count)
        inner = self.integer(
            data.get("inner_tens"), f"{path}.inner_tens", f"{label}: Innenzehner", count
        )
        if total is None and not self.partial:
            self.add(f"{path}.sum", f"{label}: Seriensumme fehlt")
        if tens is not None and inner is not None and inner > tens:
            self.add(
                f"{path}.inner_tens",
                f"{label}: {inner} Innenzehner, aber nur {tens} Zehner (Innenzehner zählen mit)",
            )
        best_tens = tens if tens is not None else inner
        if total is not None and best_tens is not None:
            if total < best_tens * 10:
                self.add(
                    f"{path}.sum",
                    f"{label}: {best_tens} Zehner ergeben mindestens {best_tens * 10}",
                )
            # Höchster Wert eines Schusses, der kein Zehner ist (sonst 9; Bogen 3D: 11).
            others = [v for v in plan.ring_values if v != INNER_TEN and v != MAX_RING]
            other_max = max((int(v) for v in others), default=0)
            most = tens * MAX_RING + (count - tens) * other_max if tens is not None else None
            if most is not None and total > most:
                self.add(
                    f"{path}.sum",
                    f"{label}: mit {tens} Zehnern sind höchstens {most} Ringe möglich",
                )
        return {"total": total, "tens": tens, "inner_tens": inner}

    def tenths_sum(
        self, data: Mapping[str, Any], count: int, path: str, label: str
    ) -> dict[str, Any]:
        """Seriensumme bei Zehntelwertung: Kommazahl, Zehner = Schüsse ab 10,0."""
        maximum = count * MAX_TENTHS
        total: Decimal | None = None
        value = data.get("sum")
        if value is not None:
            number = parse_decimal_input(value)
            if number is None or decimal_places(number) > 1 or number > maximum:
                self.add(
                    f"{path}.sum",
                    f"{label}: Seriensumme mit höchstens einer Nachkommastelle von 0 bis "
                    f"{format_number(maximum)}",
                )
            elif 0 < number < MIN_TENTHS:
                self.add(
                    f"{path}.sum", f"{label}: Seriensumme 0 oder mindestens 1,0. {TENTHS_RANGE}"
                )
            else:
                total = to_tenths(number)
        elif not self.partial:
            self.add(f"{path}.sum", f"{label}: Seriensumme fehlt")
        tens = self.integer(data.get("tens"), f"{path}.tens", f"{label}: Zehner", count)
        if "inner_tens" in data:
            self.add(
                f"{path}.inner_tens",
                f"{label}: Bei Zehntelwertung gibt es keine Innenzehner (Zehner sind alle "
                "Schüsse ab 10,0)",
            )
        if total is not None and tens is not None:
            least = to_tenths(Decimal(tens * MAX_RING))
            most = tens * MAX_TENTHS + (count - tens) * MAX_TENTHS_BELOW_TEN
            if total < least:
                self.add(
                    f"{path}.sum",
                    f"{label}: {tens} Zehner ergeben mindestens {format_number(least)}",
                )
            elif total > most:
                self.add(
                    f"{path}.sum",
                    f"{label}: mit {tens} Zehnern sind höchstens {format_number(most)} Ringe "
                    "möglich",
                )
        return {"total": total, "tens": tens, "inner_tens": None}

    def integer(self, value: object, path: str, label: str, maximum: int) -> int | None:
        if value is None:
            return None
        number = _as_int(value)
        if number is None or not 0 <= number <= maximum:
            self.add(path, f"{label}: ganze Zahl von 0 bis {maximum}")
            return None
        return number

    def time(self, value: object, path: str, label: str, *, required: bool = True) -> int | None:
        if value is None:
            if required and not self.partial:
                self.add(path, f"{label} fehlt")
            return None
        number = _as_int(value)
        if number == 0 and not required:
            # Der Status braucht keine gemessene Zeit: eine 0 ist „keine Zeit“.
            return None
        if number is None or number <= 0:
            self.add(path, f"{label}: in Hundertstelsekunden als ganze Zahl größer 0")
            return None
        return number

    def plausible(
        self,
        plan: SectionPlan,
        time_cs: int | None,
        limit_s: Decimal | None,
        path: str,
        prefix: str,
    ) -> int | None:
        """Fehler bei einer gemessenen Zeit über der Plausibilitätsgrenze (siehe oben)."""
        if time_cs is None:
            return None
        maximum = plausible_max_s(plan, limit_s)
        if time_cs <= maximum * 100:
            return time_cs
        hint = (
            "bei überschrittenem Zeitlimit den Status „Zeitlimit erreicht“ wählen"
            if "time_limit" in self.definition.series_statuses(plan) and not plan.section_time
            else "bitte die Zeit prüfen"
        )
        self.add(
            path,
            f"{prefix}{format_cs(time_cs)} ist unplausibel – höchstens "
            f"{format_seconds_value(maximum)} s; {hint}",
        )
        return None

    def standing(
        self, plan: SectionPlan, value: object, path: str, label: str, *, required: bool
    ) -> int | None:
        maximum = plan.targets or 0
        if value is None:
            if required and not self.partial:
                self.add(path, f"{label}: Anzahl stehender Scheiben fehlt")
            return None
        number = _as_int(value)
        if number is None or number < 0:
            self.add(path, f"{label}: stehende Scheiben als ganze Zahl ab 0")
            return None
        if number > maximum:
            self.add(path, f"{label}: höchstens {maximum} stehende Scheiben")
            return None
        return number


def _allowed_text(values: tuple[int | str, ...]) -> str:
    if values == DEFAULT_RING_VALUES:
        return "0 bis 10 oder „X“ (Innenzehner)"
    texts = [f"„{v}“" if v == INNER_TEN else str(v) for v in values]
    return f"{', '.join(texts[:-1])} oder {texts[-1]}" if len(texts) > 1 else texts[0]
