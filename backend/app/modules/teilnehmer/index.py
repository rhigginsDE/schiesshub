"""Suchindex der Personen im Arbeitsspeicher.

Namen und Mitgliedsnummern sind in der Datenbank verschlüsselt und dort nicht durchsuchbar. Der
Index hält deshalb ihre Vergleichsform (`names.fold`) im Speicher des Servers. Er wird beim Start
aus der Datenbank gefüllt und vom Service nach jeder erfolgreichen Änderung nachgeführt. In der
Datenbank gibt es kein Klartext-Suchfeld.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from app.modules.teilnehmer.names import fold

_WORD_SPLIT = re.compile(r"[\s\-]+")


@dataclass(frozen=True, slots=True)
class _Entry:
    id: UUID
    club_id: UUID | None
    name: str
    member_no: str

    def words(self) -> list[str]:
        return [word for word in _WORD_SPLIT.split(f"{self.name} {self.member_no}") if word]


class PersonIndex:
    def __init__(self) -> None:
        self._persons: dict[UUID, _Entry] = {}
        self._clubs: dict[UUID, str] = {}

    def __len__(self) -> int:
        return len(self._persons)

    def load(
        self,
        persons: Iterable[tuple[UUID, str, str | None, UUID | None]],
        clubs: Iterable[tuple[UUID, str]],
    ) -> None:
        """Ersetzt den gesamten Inhalt (Start der Anwendung)."""
        self._persons.clear()
        self._clubs.clear()
        for club_id, club_name in clubs:
            self.put_club(club_id, club_name)
        for person_id, name, member_no, club_id in persons:
            self.put_person(person_id, name, member_no, club_id)

    # --- Pflege -----------------------------------------------------------------

    def put_person(
        self, person_id: UUID, name: str, member_no: str | None, club_id: UUID | None
    ) -> None:
        self._persons[person_id] = _Entry(person_id, club_id, fold(name), fold(member_no or ""))

    def remove_person(self, person_id: UUID) -> None:
        self._persons.pop(person_id, None)

    def put_club(self, club_id: UUID, name: str) -> None:
        self._clubs[club_id] = fold(name)

    def remove_club(self, club_id: UUID) -> None:
        self._clubs.pop(club_id, None)

    def move_club_members(self, from_id: UUID, to_id: UUID) -> None:
        for person_id, entry in list(self._persons.items()):
            if entry.club_id == from_id:
                self._persons[person_id] = _Entry(person_id, to_id, entry.name, entry.member_no)

    # --- Abfragen ---------------------------------------------------------------

    def _sort_key(self, entry: _Entry) -> tuple[str, str]:
        return entry.name, str(entry.id)

    def all_sorted(self) -> list[UUID]:
        """Alle Personen, sortiert nach Name."""
        return [entry.id for entry in sorted(self._persons.values(), key=self._sort_key)]

    def search(self, query: str) -> list[UUID]:
        """Treffer in Name, Mitgliedsnummer und Vereinsname.

        Mehrere Wörter müssen alle vorkommen. Reihenfolge: Ein Feld beginnt mit dem Suchbegriff,
        dann jedes Wort ist Anfang eines Worts, dann Teiltreffer; innerhalb gleich nach Name.
        """
        folded = fold(query)
        if not folded:
            return self.all_sorted()
        tokens = folded.split(" ")
        ranked: list[tuple[int, tuple[str, str], UUID]] = []
        for entry in self._persons.values():
            club = self._clubs.get(entry.club_id, "") if entry.club_id else ""
            fields = (entry.name, entry.member_no, club)
            if not all(any(token in field for field in fields) for token in tokens):
                continue
            if any(field.startswith(folded) for field in fields):
                rank = 0
            else:
                words = [*entry.words(), *(word for word in _WORD_SPLIT.split(club) if word)]
                rank = 1 if all(any(w.startswith(t) for w in words) for t in tokens) else 2
            ranked.append((rank, self._sort_key(entry), entry.id))
        ranked.sort()
        return [person_id for _, _, person_id in ranked]

    def duplicates(
        self, name: str, club_id: UUID | None, exclude: UUID | None = None
    ) -> list[UUID]:
        """Personen mit gleicher Vergleichsform des Namens im selben Verein (oder ohne Verein)."""
        folded = fold(name)
        return [
            entry.id
            for entry in sorted(self._persons.values(), key=self._sort_key)
            if entry.name == folded and entry.club_id == club_id and entry.id != exclude
        ]
