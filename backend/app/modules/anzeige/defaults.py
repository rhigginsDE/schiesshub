"""Standardwerte des Moduls als Daten: die Szenen einer neuen Anzeige und die „Hauptanzeige“.

Beim ersten Start legt das Modul die Hauptanzeige an (einmalig; gelöscht bleibt sie gelöscht).
Wer eine Anzeige ohne `config` anlegt, bekommt `DEFAULT_CONFIG`.
"""

from typing import Any

DEFAULT_DISPLAY_NAME = "Hauptanzeige"

DEFAULT_CONFIG: dict[str, Any] = {
    "scenes": [
        {"id": "live-wertung", "kind": "live_ranking", "seconds": 20},
        {"id": "startliste", "kind": "startlist", "seconds": 15},
    ],
    "name_mode": "as_person",
    "show_club": "as_person",
    "ticker": None,
    "show_backup_warning": None,
    "show_provisional_note": True,
    "theme": "dark",
}

# Schlüssel in der Tabelle `setting`: merkt sich, dass die Hauptanzeige schon angelegt wurde.
SETTING_KEY = "anzeige"

# Ereignisse, bei denen ein Bildschirm den Feed neu laden soll. `*` am Ende: alle mit diesem
# Anfang. Personen und Vereine wegen Namen und Anzeige-Einstellung.
RELOAD_EVENTS: tuple[str, ...] = (
    "display.changed",
    "tournament.*",
    "competition.*",
    "range.*",
    "class.*",
    "entry.*",
    "start.*",
    "heat.*",
    "result.*",
    "person.*",
    "club.*",
    "backup.status",
)

# Spätestens so oft nachladen, auch ohne Ereignis (Einspruchsfristen laufen ohne Ereignis ab).
POLL_SECONDS = 60

# Texte der Ruhe-Szene.
IDLE_NO_TOURNAMENT = "Zurzeit läuft kein Turnier."
IDLE_MANY_TOURNAMENTS = (
    "Es laufen mehrere Turniere. Bitte an der Anzeige einstellen, welches gezeigt wird."
)
IDLE_NOTHING_YET = "Startliste und Ergebnisse erscheinen hier, sobald es losgeht."
IDLE_NO_SCENES = "Für diese Anzeige sind keine Inhalte eingestellt."
PROVISIONAL_NOTE = "Ergebnisse vorläufig – die Einspruchsfrist läuft noch."
